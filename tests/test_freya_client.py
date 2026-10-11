from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'builder'))
from freya_client import bind_workspace


class WorkspaceTests(unittest.TestCase):
    def test_every_operation_uses_authenticated_workspace(self):
        calls = []
        client = SimpleNamespace(workspace_id=lambda: 'personal-test-workspace',
                                 api=lambda *a, **kw: calls.append((a, kw)))
        bind_workspace(client)
        client.api('POST', '/api/v2/workflow', {'name': 'test'})
        self.assertEqual(calls[0][1], {'workspaceId': 'personal-test-workspace'})
        bind_workspace(client)
        client.api('GET', '/api/v2/workflow/test', limit=100)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][1], {'limit': 100, 'workspaceId': 'personal-test-workspace'})

    def test_does_not_retry_ambiguous_creation(self):
        calls = []
        def api(*args, **kw):
            calls.append(args)
            raise RuntimeError('POST /api/v2/personas -> 504')
        client = SimpleNamespace(workspace_id=lambda: 'test', api=api)
        bind_workspace(client)
        with self.assertRaises(RuntimeError): client.api('POST', '/api/v2/personas', {})
        self.assertEqual(len(calls), 1)

    def test_retries_transient_read_once(self):
        calls = []
        def api(*args, **kw):
            calls.append(args)
            if len(calls) == 1: raise RuntimeError('GET /api/v2/call/test -> 504')
            return {'ok': True}
        client = SimpleNamespace(workspace_id=lambda: 'test', api=api)
        bind_workspace(client)
        with patch('freya_client.time.sleep'):
            self.assertEqual(client.api('GET', '/api/v2/call/test'), {'ok': True})
        self.assertEqual(len(calls), 2)

    def test_poll_can_use_official_list_when_detail_times_out(self):
        calls = []
        def api(method, path, body=None, **kw):
            calls.append(path)
            if path.endswith('/test-id'): raise RuntimeError('GET '+path+' -> 504')
            return {'simulations': [{'id': 'test-id', 'status': 'completed'}]}
        client = SimpleNamespace(workspace_id=lambda: 'test', api=api)
        bind_workspace(client)
        for _ in range(2):
            self.assertEqual(client.api('GET', '/api/v2/simulations/test-id')['simulation']['status'], 'completed')
        self.assertEqual(calls.count('/api/v2/simulations/test-id'), 1)


if __name__ == '__main__':
    unittest.main()
