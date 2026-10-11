import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('project_wrangler', Path(__file__).resolve().parents[1] / 'scripts/wrangler.py')
wrangler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wrangler)


class WranglerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root/'mock').mkdir()
        (self.root/'private').mkdir()
        self.config = self.root/'mock/wrangler.jsonc'
        self.config.write_text(json.dumps({'name': 'test-worker', 'main': 'src/index.js'}))
        self.root_patch = patch.object(wrangler, 'ROOT', self.root); self.root_patch.start()
        # Do not inspect the user's global authentication directories or run Node.
        self.home_patch = patch.object(wrangler.Path, 'home', return_value=self.root/'empty-home'); self.home_patch.start()
        self.call_patch = patch.object(wrangler.subprocess, 'call', return_value=0)
        self.call = self.call_patch.start()

    def tearDown(self):
        self.call_patch.stop(); self.home_patch.stop(); self.root_patch.stop(); self.tmp.cleanup()

    def record_account(self):
        (self.root/'private/cloudflare-account.json').write_text(json.dumps({'account_id': 'a'*32}))

    def test_all_remote_mutations_require_the_recorded_account(self):
        for args in (['deploy'], ['secret', 'put', 'KEY'], ['versions', 'upload'],
                     ['versions', 'deploy'], ['--log-level', 'info', 'deploy']):
            with self.subTest(args=args), self.assertRaisesRegex(SystemExit, 'personal Cloudflare account'):
                wrangler.main(args)
        self.call.assert_not_called()

    def test_identity_and_local_commands_can_run_before_account_selection(self):
        for args in (['login'], ['whoami'], ['--version'], ['deploy', '--dry-run'], ['dev', '--local']):
            with self.subTest(args=args): self.assertEqual(wrangler.main(args), 0)

    def test_false_or_negated_dry_run_is_not_a_guard_bypass(self):
        for args in (['deploy', '--dry-run=false'], ['deploy', '--dry-run', 'false'],
                     ['deploy', '--dry-run', '--no-dry-run'], ['deploy', '--dry-run', '--dry-run=false']):
            with self.subTest(args=args), self.assertRaisesRegex(SystemExit, 'personal Cloudflare account'):
                wrangler.main(args)
        self.call.assert_not_called()

    def test_auth_config_and_directory_overrides_are_blocked(self):
        self.record_account()
        for args in (['--config', 'other.json', 'deploy'], ['deploy', '--config=other.json'],
                     ['deploy', '-cother.json'], ['deploy', '--cwd', '/another-project'],
                     ['deploy', '--env-file=secrets.env'], ['deploy', '--profile', 'employer'],
                     ['deploy', '--temporary']):
            with self.subTest(args=args), self.assertRaisesRegex(SystemExit, 'overrides are disabled'):
                wrangler.main(args)
        self.call.assert_not_called()

    def test_config_account_cannot_override_the_recorded_account(self):
        self.record_account()
        for config in ({'account_id': 'b'*32}, {'env': {'production': {'account_id': 'b'*32}}}):
            self.config.write_text(json.dumps(config))
            with self.assertRaisesRegex(SystemExit, 'must match'):
                wrangler.main(['deploy'])
        self.call.assert_not_called()

    def test_environment_is_filtered_and_implicit_dotenv_loading_is_disabled(self):
        self.record_account()
        with patch.dict(os.environ, {'CLOUDFLARE_API_TOKEN': 'unrelated', 'CF_ACCOUNT_ID': 'other',
                                     'WRANGLER_API_TOKEN': 'other', 'WRANGLER_SEND_METRICS': 'true'}, clear=True):
            wrangler.main(['deploy'])
        args, kwargs = self.call.call_args
        self.assertEqual(args[0][-4:], ['--config', str(self.config), '--env-file', os.devnull])
        self.assertEqual(kwargs['cwd'], self.root/'mock')
        self.assertEqual(kwargs['env']['CLOUDFLARE_ACCOUNT_ID'], 'a'*32)
        self.assertEqual(kwargs['env']['XDG_CONFIG_HOME'], str(self.root/'private/cloudflare'))
        self.assertNotIn('CLOUDFLARE_API_TOKEN', kwargs['env'])
        self.assertNotIn('CF_ACCOUNT_ID', kwargs['env'])
        self.assertNotIn('WRANGLER_API_TOKEN', kwargs['env'])

    def test_local_dev_refuses_remote_bindings(self):
        self.config.write_text(json.dumps({'kv_namespaces': [{'binding': 'DATA', 'remote': True}]}))
        with self.assertRaisesRegex(SystemExit, 'without remote bindings'):
            wrangler.main(['dev', '--local'])
        self.call.assert_not_called()

    def test_legacy_global_credential_directory_blocks_launch(self):
        (self.root/'empty-home/.wrangler').mkdir(parents=True)
        with self.assertRaisesRegex(SystemExit, 'Legacy global Wrangler'):
            wrangler.main(['whoami'])
        self.call.assert_not_called()
