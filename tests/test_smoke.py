from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'builder'))
from smoke import run_smoke


class SmokeTests(unittest.TestCase):
    def test_opening_uses_fixture_and_closes_the_chat(self):
        client=SimpleNamespace(api=Mock(side_effect=[{'callId':'call','response':'Welcome, test caller.'},{}]))
        result=run_smoke(client,'workflow',{'message':'Hello','variables':{'customer_id':'fixture'},'expected_fragments':['Welcome']})
        self.assertTrue(result['passed'])
        self.assertEqual(client.api.call_args_list[0].args[2]['customerVariables'],{'customer_id':'fixture'})
        self.assertEqual(client.api.call_args_list[1].args,('POST','/api/v2/chat/end',{'callId':'call'}))

    def test_unresolved_placeholders_fail_without_leaving_chat_open(self):
        client=SimpleNamespace(api=Mock(side_effect=[{'callId':'call','response':'Hello {{name}}'},{}]))
        result=run_smoke(client,'workflow',{'message':'Hello','variables':{}})
        self.assertFalse(result['passed'])
        self.assertEqual(client.api.call_args.args[1],'/api/v2/chat/end')
