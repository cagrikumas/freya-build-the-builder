import json
from pathlib import Path
import runpy
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


SCRIPT = Path(__file__).resolve().parents[1] / 'builder/practice.py'


class PracticeRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'tools').mkdir()
        self.out = self.root / 'results.json'
        self.session = self.root / 'results.session.json'
        self.client = SimpleNamespace(api=Mock())
        self.bank = SimpleNamespace(http=Mock())
        self.modules = {
            'build': SimpleNamespace(load_env=Mock(), ROOT=self.root, KIT=self.root),
            'freya': self.client, 'score': self.bank,
            'freya_client': SimpleNamespace(bind_workspace=Mock()),
            'http_transport': SimpleNamespace(install_curl_transport=Mock()),
        }

    def tearDown(self):
        self.tmp.cleanup()

    def run_wrapper(self, arguments, runner):
        (self.root / 'tools/run_cases.py').write_text(runner)
        with patch.dict(sys.modules, self.modules), patch.object(sys, 'argv', [str(SCRIPT), *arguments]), patch.object(sys, 'path', sys.path.copy()):
            runpy.run_path(str(SCRIPT), run_name='__main__')

    def test_journals_original_sessions_before_simulation(self):
        self.bank.http.return_value = {'variables': {'customer_id': 'original-customer'}}
        self.client.api.return_value = {'simulation': {'id': 'original-simulation'}}
        self.run_wrapper(['agent', '--out', str(self.out)], '''
import score, freya
score.http('/v1/practice/sessions', {'case': 'PUB-01'})
freya.api('POST', '/api/v2/simulations', {})
''')
        state = json.loads(self.session.read_text())
        self.assertEqual(state['sessions']['PUB-01']['customer_id'], 'original-customer')
        self.assertEqual(state['simulation_id'], 'original-simulation')

    def test_recovery_reuses_calls_without_creating_sessions_or_simulations(self):
        self.session.write_text(json.dumps({
            'arguments': ['agent', '--out', str(self.out)],
            'sessions': {'PUB-01': {'customer_id': 'original-customer'}},
            'simulation_id': 'original-simulation',
        }))
        original_bank = self.bank.http
        original_api = self.client.api
        original_api.side_effect = [
            {'simulation': {'status': 'completed'}}, {'iterations': [{'id': 'original-iteration'}]},
        ]
        self.run_wrapper(['--resume-session', str(self.session)], '''
import score, freya
assert score.http('/v1/practice/sessions', {'case': 'PUB-01'})['variables']['customer_id'] == 'original-customer'
assert freya.run_simulation('agent', 'name', {}) == ('original-simulation', 'original-iteration', 'completed')
''')
        original_bank.assert_not_called()
        self.assertTrue(all(call.args[0] == 'GET' for call in original_api.call_args_list))

    def test_rejects_duplicate_repetition_and_missing_simulation_before_network(self):
        for arguments, simulation in [(['--reps=3'], 'sim'), (['--rerun-if-slow=1'], 'sim'), ([], None)]:
            with self.subTest(arguments=arguments, simulation=simulation):
                self.session.write_text(json.dumps({'arguments': ['agent', *arguments], 'sessions': {}, 'simulation_id': simulation}))
                with self.assertRaises(SystemExit):
                    self.run_wrapper(['--resume-session', str(self.session)], 'raise AssertionError("must not run")')
                self.modules['freya_client'].bind_workspace.assert_not_called()
                self.client.api.assert_not_called()
