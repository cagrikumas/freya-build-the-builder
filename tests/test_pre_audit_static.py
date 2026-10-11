import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'builder'))
import build


class PreAuditStaticTests(unittest.TestCase):
    def api(self):
        return {'openapi': '3.0.3', 'servers': [{'url': 'https://original.example'}],
                'paths': {'/probe': {'post': {'operationId': 'probe'}}}}

    def artifact(self, code=None):
        node = {'name': 'start', 'node_type': 'conversation',
                'task_message': 'Follow the supplied documents.', 'transitions': []}
        if code is not None:
            node.update(node_type='code', code=code, on_enter={'type': 'silent'})
        return {'workflow': {'initial_node': 'start', 'nodes': {'start': node}}, 'checks': []}

    def test_invalid_python_is_reported_without_running_checks(self):
        draft = self.artifact('def inner():\n    nonlocal missing\n')
        original = copy.deepcopy(draft)
        with patch.object(build, 'check_examples') as execute:
            errors = build.pre_audit_static_errors(draft, self.api())
        execute.assert_not_called()
        self.assertEqual(draft, original)
        self.assertTrue(any('no binding for nonlocal' in error for error in errors), errors)

    def test_derived_api_uses_deployed_server_without_mutating_input(self):
        draft = self.artifact()
        draft['workflow']['nodes']['start']['tools'] = ['probe']
        draft['openapi'] = self.api()
        # The final folder contract replaces even an absent or stale server.
        draft['openapi'].pop('servers')
        original = copy.deepcopy(draft)
        with patch.object(build, 'assemble', wraps=build.assemble) as expand, \
             patch.object(build, 'check_examples') as execute:
            errors = build.pre_audit_static_errors(draft, mock_url='https://deployed.example')
        self.assertEqual(errors, [])
        self.assertEqual(expand.call_args.args[1]['servers'], [{'url': 'https://deployed.example'}])
        self.assertEqual(draft, original)
        execute.assert_not_called()

    def test_malformed_drafts_become_audit_diagnostics(self):
        for draft in (None, {}, {'openapi': []}, {'openapi': {'openapi': '3.0.3', 'paths': {}}}):
            errors = build.pre_audit_static_errors(draft)
            self.assertEqual(len(errors), 1)
            self.assertIn('Malformed draft artifact', errors[0])

    def test_audit_receives_syntax_error_before_any_execution_and_trace_records_it(self):
        draft = self.artifact('def inner():\n    nonlocal missing\n')
        draft['openapi'] = self.api()
        repaired = self.artifact()
        repaired['openapi'] = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case = root / 'case'; case.mkdir()
            (case / 'BRIEF.md').write_text('Synthetic service contract.')
            code_dir = root / 'builder'; code_dir.mkdir()
            for name in ('compile_prompt.md', 'audit_prompt.md'):
                (code_dir / name).write_text('Generic compiler instruction.')
            kit = root / 'kit'; (kit / 'docs').mkdir(parents=True)
            for name in ('workflow-format.md', 'tools-and-code.md'):
                (kit / 'docs' / name).write_text('Synthetic platform reference.')
            def model(prompt, purpose, *args, **kwargs):
                if purpose.startswith('Compile'):
                    return draft
                self.assertIn('# PRE-AUDIT STATIC VALIDATION', prompt)
                self.assertIn('no binding for nonlocal', prompt)
                execute.assert_not_called()
                return {'approved': False, 'issues': ['Invalid Python'], 'artifact': repaired}
            with patch.object(build, 'ROOT', root), patch.object(build, 'KIT', kit), \
                 patch.object(build, 'load_env'), \
                 patch.object(build, 'read_folder', return_value=('Synthetic documents.', [], [])), \
                 patch.object(build, 'call', side_effect=model) as generate, \
                 patch.object(build, 'check_examples', return_value=[]) as execute, \
                 patch.dict(sys.modules, {'freya': SimpleNamespace()}), \
                 patch.object(sys, 'argv', ['build.py', str(case), 'https://deployed.example', '--offline']):
                build.main()
            self.assertEqual(generate.call_count, 2)
            self.assertEqual(execute.call_count, 1)  # Only authoritative post-audit checks.
            run = next((root / 'traces').iterdir())
            events = [json.loads(line) for line in (run / 'trace.jsonl').read_text().splitlines()]
            event = next(row for row in events if row['event'] == 'pre_audit_static_validation')
            self.assertFalse(event['code_executed'])
            self.assertTrue(any('no binding for nonlocal' in error for error in event['errors']))
