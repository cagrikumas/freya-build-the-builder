import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'builder'))
import build
from evaluate import compact_feedback, FEEDBACK_MAX_CHARS


class PracticeFeedbackTests(unittest.TestCase):
    def messages(self):
        return [
            {'role': 'assistant', 'message': 'Please provide the requested detail.', 'nodeId': 'start'},
            {'role': 'system', 'message': json.dumps({'event': 'function_call_start',
                'function': 'code_exec', 'args': {'code': 'CODE_SOURCE_MARKER' * 3000}})},
            {'role': 'system', 'message': json.dumps({'event': 'function_call_complete',
                'function': 'code_exec', 'result': {'status': 'success',
                'validation_errors': ["variable 'event' rejected by schema validation"]}})},
        ]

    def failures(self, count=13):
        return [{'case': 'synthetic-%02d' % i, 'failed': ['Missing required next step.'],
                 'tools': ['verify_identity'], 'call_id': 'call-%02d' % i,
                 'messages': self.messages()} for i in range(count)]

    def test_all_thirteen_case_summaries_and_errors_survive_without_source(self):
        failures = self.failures()
        original = json.dumps(failures)
        feedback = build.compact_practice_feedback(failures, {'nodes': {}})
        encoded = json.dumps(feedback)
        self.assertLessEqual(len(encoded), FEEDBACK_MAX_CHARS)
        self.assertEqual(len(feedback['rows']), 13)
        self.assertEqual([row['name'] for row in feedback['rows']], [f['case'] for f in failures])
        for row in feedback['rows']:
            self.assertEqual(row['outcome'], 'fail')
            self.assertEqual(row['reason'], {'failed': ['Missing required next step.'], 'tools': ['verify_identity']})
            self.assertIn('rejected by schema validation', json.dumps(row))
        self.assertNotIn('CODE_SOURCE_MARKER', encoded)
        self.assertEqual(json.dumps(failures), original)

    def test_default_twelve_row_contract_is_unchanged_and_sixteen_stays_bounded(self):
        rows = [{'name': 'case-' + str(i), 'outcome': 'fail', 'reason': '失敗' * 4000,
                 'messages': self.messages()} for i in range(16)]
        with self.assertRaises(ValueError):
            compact_feedback({'rows': rows[:13]})
        feedback = compact_feedback({'rows': rows}, max_rows=16)
        self.assertEqual(len(feedback['rows']), 16)
        self.assertLessEqual(len(json.dumps(feedback)), FEEDBACK_MAX_CHARS)
        for invalid in (0, 17, True):
            with self.assertRaises(ValueError):
                compact_feedback({'rows': []}, max_rows=invalid)

    def test_practice_repair_persists_full_redacted_evidence_but_sends_compact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brief = root / 'brief.md'; brief.write_text('Synthetic practice rules.')
            api = root / 'api.json'; api.write_text(json.dumps({'openapi': '3.0.3',
                'servers': [{'url': 'https://mock.example'}], 'paths': {}}))
            code_dir = root / 'builder'; code_dir.mkdir()
            for name in ('compile_prompt.md', 'audit_prompt.md'):
                (code_dir / name).write_text('Generic instruction.')
            kit = root / 'kit'; (kit / 'docs').mkdir(parents=True)
            for name in ('workflow-format.md', 'tools-and-code.md'):
                (kit / 'docs' / name).write_text('Synthetic reference.')
            artifact = {'workflow': {'initial_node': 'start', 'nodes': {'start': {
                'name': 'start', 'node_type': 'conversation', 'task_message': 'Follow the rules.',
                'transitions': []}}}, 'checks': []}
            rows = [{'id': f['case'], 'pass': False, 'failed': f['failed'],
                     'tools': f['tools'], 'call_id': f['call_id']} for f in self.failures()]
            test_runs = []
            def scorer(command, **kwargs):
                passed = 13 if test_runs else 0
                test_runs.append(command)
                Path(command[command.index('--out') + 1]).write_text(json.dumps({
                    'passed': passed, 'total': 13, 'rows': rows}))
                return SimpleNamespace(returncode=0, stdout='', stderr='')
            client = SimpleNamespace(save_workflow=Mock(return_value={
                'workflow_id': 'w', 'agent_id': 'a', 'version': 1}),
                update_workflow=Mock(return_value=2), validate_workflow=Mock(),
                get_call=Mock(return_value={'transcript': 'SECRET_MARKER', 'messages': self.messages()}),
                export_workflow=lambda wid, path: Path(path).write_text('{}'))
            with patch.object(build, 'ROOT', root), patch.object(build, 'KIT', kit), \
                 patch.object(build, 'load_env'), patch.object(build, 'bind_workspace'), \
                 patch.object(build, 'install_curl_transport'), \
                 patch.object(build, 'call', side_effect=[artifact, {'approved': True}, {'issues': [], 'patches': []}]) as generate, \
                 patch.object(build.subprocess, 'run', side_effect=scorer), \
                 patch.dict(sys.modules, {'freya': client}), \
                 patch.dict(build.os.environ, {'FREYA_API_KEY': 'SECRET_MARKER'}), \
                 patch.object(sys, 'argv', ['build.py', str(brief), str(api), '--practice', 'all']):
                build.main()
            run = next((root / 'traces').iterdir())
            full = (run / 'practice-repair-evidence.json').read_text()
            compact = (run / 'practice-repair-feedback.json').read_text()
            self.assertIn('CODE_SOURCE_MARKER', full)
            self.assertNotIn('SECRET_MARKER', full)
            self.assertIn('[REDACTED]', full)
            self.assertNotIn('CODE_SOURCE_MARKER', compact)
            self.assertEqual(len(json.loads(compact)['rows']), 13)
            repair_prompt = generate.call_args_list[2].args[0]
            self.assertIn(compact, repair_prompt)
            self.assertNotIn('CODE_SOURCE_MARKER', repair_prompt)
            events = [json.loads(line) for line in (run / 'trace.jsonl').read_text().splitlines()]
            event = next(row for row in events if row['event'] == 'practice_repair_feedback')
            self.assertEqual(event['full_evidence'], 'practice-repair-evidence.json')
            self.assertEqual(event['model_feedback'], 'practice-repair-feedback.json')
            self.assertEqual(len(test_runs), 2)
