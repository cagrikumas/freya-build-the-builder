import json
import copy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'builder'))
import build


class FolderBuildTests(unittest.TestCase):
    def run_online_example_repair(self, repaired_passed, change_tests=False, retest_error=None, phase='examples'):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); case = root / 'case'; case.mkdir()
            (case / 'BRIEF.md').write_text('Follow this synthetic case and its example conversation.')
            schema = {'openapi': '3.0.3', 'servers': [{'url': 'https://mock.example'}],
                      'paths': {'/action': {'post': {'operationId': 'action'}}}}
            (case / 'api.json').write_text(json.dumps(schema))
            code = root / 'builder'; code.mkdir()
            for name in ['compile_prompt.md', 'audit_prompt.md']:
                (code / name).write_text((build.ROOT / 'builder' / name).read_text())
            kit = root / 'kit'; (kit / 'docs').mkdir(parents=True)
            for name in ['workflow-format.md', 'tools-and-code.md']:
                (kit / 'docs' / name).write_text('Platform reference.')
            artifact = {'policy': {}, 'workflow': {'initial_node': 'start', 'nodes': {'start': {
                'name': 'start', 'node_type': 'conversation', 'task_message': 'original', 'transitions': []}}},
                'checks': [], 'scenarios': [{'name': 'example', 'source': 'BRIEF.md', 'variables': {'fixture': 'test'},
                                           'prompt': 'Follow the example.', 'success_criteria': 'Follow the policy.'}]}
            if phase == 'smoke':
                artifact.pop('scenarios')
                artifact['smoke'] = {'message': 'Hello', 'variables': {'fixture': 'test'}, 'expected_fragments': ['required']}
            repair = {'issues': ['observed error'], 'patches': [{'op': 'replace',
                      'path': '/workflow/nodes/start/task_message', 'value': 'repaired'}]}
            if change_tests: repair['patches'].append({'op': 'replace', 'path': '/scenarios/0/success_criteria', 'value': 'Always pass'})
            initial = {'failed': 1, 'passed': 0, 'total': 1, 'conclusive': True,
                       'rows': [{'name': 'example', 'outcome': 'fail'}], 'persona_ids': ['p']}
            retest = {**initial, 'passed': repaired_passed, 'conclusive': repaired_passed is not None and repaired_passed >= 0}
            saved = []
            def save(slot, workflow, **kwargs):
                saved.append(copy.deepcopy(workflow))
                return {'workflow_id': 'w', 'agent_id': 'a', 'version': 1}
            def update(wid, workflow):
                saved.append(copy.deepcopy(workflow)); return len(saved)
            def export(wid, path):
                Path(path).write_text(json.dumps({'workflow_id': 'w', 'workflow': saved[-1]}))
            client = SimpleNamespace(save_workflow=save, update_workflow=update, export_workflow=export,
                                     validate_workflow=Mock())
            with patch.object(build, 'ROOT', root), patch.object(build, 'KIT', kit), patch.object(build, 'load_env'),\
                 patch.object(build, 'install_curl_transport'), patch.object(build, 'bind_workspace'),\
                 patch.object(build, 'call', side_effect=[artifact, {'approved': True}, repair]),\
                 patch.object(build, 'run_examples', side_effect=[initial, retest_error or retest]) as evaluate,\
                 patch.object(build, 'run_smoke', side_effect=[{'passed': False}, retest_error or {'passed': repaired_passed}]),\
                 patch.dict(sys.modules, {'freya': client}),\
                 patch.object(sys, 'argv', ['build.py', str(case), 'https://mock.example']):
                if change_tests:
                    with self.assertRaisesRegex(ValueError, 'preserve the original tests'): build.main()
                    self.assertEqual(len(saved), 1)
                    return
                if retest_error:
                    with self.assertRaises(type(retest_error)): build.main()
                    self.assertEqual(len(saved), 3)
                    self.assertEqual(saved[-1]['nodes']['start']['task_message'], 'original')
                    return
                build.main()
            if phase == 'examples':
                self.assertEqual(evaluate.call_args_list[1].kwargs['persona_ids'], ['p'])
            else:
                evaluate.assert_not_called()
            exported = json.loads((root / 'submission' / 'final.workflow.json').read_text())
            return exported['workflow']['nodes']['start']['task_message']

    def test_example_repair_is_selected_after_conclusive_improvement(self):
        self.assertEqual(self.run_online_example_repair(1), 'repaired')

    def test_inconclusive_retest_restores_the_original_workflow(self):
        self.assertEqual(self.run_online_example_repair(-1), 'original')

    def test_example_repair_cannot_weaken_the_judge_criteria(self):
        self.run_online_example_repair(1, change_tests=True)

    def test_retest_failure_restores_original_before_propagating_error(self):
        self.run_online_example_repair(0, retest_error=RuntimeError('API -> 400: invalid response'))

    def test_smoke_repair_is_selected_only_after_measured_pass(self):
        self.assertEqual(self.run_online_example_repair(True, phase='smoke'), 'repaired')
        self.assertEqual(self.run_online_example_repair(None, phase='smoke'), 'original')

    def test_smoke_retest_exception_restores_original(self):
        self.run_online_example_repair(False, phase='smoke', retest_error=RuntimeError('API -> 401: denied'))

    def test_documents_are_compiled_without_case_rules_in_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); case=root/'case';case.mkdir()
            (case/'BRIEF.md').write_text('Speak in the language of these documents. İptal işlemini açıkla.')
            code=root/'builder';code.mkdir()
            for name in ['compile_prompt.md','audit_prompt.md']:
                (code/name).write_text((build.ROOT/'builder'/name).read_text())
            kit=root/'kit';(kit/'docs').mkdir(parents=True)
            for name in ['workflow-format.md','tools-and-code.md']:(kit/'docs'/name).write_text('Platform reference.')
            artifact={'policy':{},'workflow':{'initial_node':'start','nodes':{'start':{
                'name':'start','node_type':'conversation','task_message':'Follow the supplied policy.','transitions':[]}}},
                'checks':[],'openapi':{'openapi':'3.0.3','servers':[{'url':'https://original.example'}],
                'paths':{'/cancel':{'post':{'operationId':'cancel'}}}}}
            with patch.object(build,'ROOT',root),patch.object(build,'KIT',kit),patch.object(build,'load_env'),\
                 patch.object(build,'call',side_effect=[artifact,{'approved':True,'issues':[],'patches':[]}]) as model,\
                 patch.object(sys,'argv',['build.py',str(case),'https://personal-mock.example','--offline']):
                build.main()
            first=model.call_args_list[0]
            self.assertIn('İptal işlemini açıkla.',first.args[0])
            self.assertIn('https://personal-mock.example',first.args[0])
            run=next((root/'traces').iterdir())
            schema=json.loads((run/'tool-api.json').read_text())
            self.assertEqual(schema['servers'],[{'url':'https://personal-mock.example'}])
            events=[json.loads(line) for line in (run/'trace.jsonl').read_text().splitlines()]
            self.assertTrue(events[-1]['completed'])
            self.assertTrue(events[0]['folder_mode'])
            self.assertEqual(events[0]['mock_url'],'https://personal-mock.example')
            self.assertIn('documents.txt', events[-1]['artifacts'])
            self.assertIn('workflow.json', events[-1]['artifacts'])
            self.assertNotIn('trace.jsonl', events[-1]['artifacts'])
