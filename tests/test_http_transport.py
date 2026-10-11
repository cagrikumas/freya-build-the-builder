from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'builder'))
from http_transport import request, install_curl_transport


class TransportTests(unittest.TestCase):
    def test_credentials_stay_off_command_line(self):
        response = SimpleNamespace(returncode=0, stdout='{"ok":true}\n200', stderr='')
        with patch('http_transport.subprocess.run', return_value=response) as run:
            self.assertEqual(request('POST', 'https://bank.example/test', {'Authorization': 'Bearer fake-secret'}, {'value': 4}), {'ok': True})
        self.assertNotIn('fake-secret', ' '.join(run.call_args.args[0]))
        self.assertIn('fake-secret', run.call_args.kwargs['input'])

    def test_http_error_preserves_status_for_safe_retry(self):
        response = SimpleNamespace(returncode=0, stdout='gateway timeout\n504', stderr='')
        with patch('http_transport.subprocess.run', return_value=response):
            with self.assertRaisesRegex(RuntimeError, 'GET /test -> 504'):
                request('GET', 'https://bank.example/test', {})

    def test_reference_envelope_and_query_are_preserved(self):
        client = SimpleNamespace(URL='https://bank.example', HEADERS={})
        install_curl_transport(client)
        with patch('http_transport.request', return_value={'data': {'result': {'workflow': {'id': 'a'}}}}) as send:
            self.assertEqual(client.api('GET', '/api/v2/workflow/a', workspaceId='test'), {'workflow': {'id': 'a'}})
        self.assertEqual(send.call_args.args[1], 'https://bank.example/api/v2/workflow/a?workspaceId=test')
