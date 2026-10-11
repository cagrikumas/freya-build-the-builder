from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'builder'))
from evaluate import run_examples, summarize_runs, validate_scenarios, EvaluationTimeout


def scenario(name='example'):
    return {'name': name, 'source': 'examples.md / sample', 'variables': {'fixture': 'sample'},
            'prompt': 'Answer only what the agent asks.', 'success_criteria': 'Follow the supplied policy.'}


class ExampleEvaluationTests(unittest.TestCase):
    def test_no_speech_is_inconclusive_even_when_the_judge_says_fail(self):
        result = summarize_runs([scenario()], ['p'], [{'personaId': 'p', 'callId': 'c', 'outcome': 'fail'}],
                                {'c': {'messages': [{'role': 'system', 'message': 'node_enter'}]}})
        self.assertFalse(result['conclusive'])
        self.assertEqual(result['failed'], 0)
        self.assertEqual(result['rows'][0]['outcome'], 'inconclusive')

    def test_duplicate_or_missing_runs_cannot_count_as_pass(self):
        run = {'personaId': 'p', 'callId': 'c', 'outcome': 'pass'}
        for runs in ([], [run, run]):
            result = summarize_runs([scenario()], ['p'], runs, {})
            self.assertFalse(result['conclusive'])
            self.assertEqual(result['passed'], 0)

    def test_unfinished_judgment_does_not_trigger_policy_repair(self):
        result = summarize_runs([scenario()], ['p'], [{'personaId': 'p', 'callId': 'c', 'outcome': 'analyzing'}],
                                {'c': {'messages': [{'role': 'assistant', 'message': 'Hello'}]}})
        self.assertFalse(result['conclusive'])
        self.assertEqual(result['failed'], 0)

    def test_retest_reuses_original_personas_and_fixed_phone_models(self):
        api = Mock(side_effect=[{'simulation': {'id': 'sim'}}, {'simulation': {'status': 'completed'}},
                               {'iterations': [{'id': 'iteration'}]}])
        client = SimpleNamespace(api=api, create_personas=Mock(), AGENT_LLM={'model': 'fixed'},
                                 SIM_LLM={'model': 'customer'},
                                 get_iteration=Mock(return_value={'runs': [{'personaId': 'p', 'callId': 'c', 'outcome': 'pass'}]}),
                                 get_call=Mock(return_value={'messages': [{'role': 'assistant', 'message': 'Hello'}]}))
        with patch('evaluate.time.sleep'):
            result = run_examples(client, 'agent', [scenario()], Mock(), persona_ids=['p'])
        client.create_personas.assert_not_called()
        body = api.call_args_list[0].args[2]
        self.assertEqual(body['assistantLlmOverride'], client.AGENT_LLM)
        self.assertEqual(body['routingLlmOverride'], client.AGENT_LLM)
        self.assertEqual(body['extractionLlmOverride'], client.AGENT_LLM)
        self.assertEqual(body['customerVariablesMap'], {'p': {'fixture': 'sample'}})
        self.assertEqual(result['passed'], 1)
        self.assertTrue(result['conclusive'])

    def test_creation_timeout_is_not_retried(self):
        client = SimpleNamespace(api=Mock(side_effect=RuntimeError('504')), AGENT_LLM={}, SIM_LLM={})
        with self.assertRaises(RuntimeError):
            run_examples(client, 'agent', [scenario()], Mock(), persona_ids=['p'])
        self.assertEqual(client.api.call_count, 1)

    def test_queued_simulation_timeout_preserves_id_and_does_not_retry(self):
        client = SimpleNamespace(api=Mock(return_value={'id': 'sim'}), AGENT_LLM={}, SIM_LLM={})
        with patch('evaluate.time.sleep', side_effect=EvaluationTimeout('queue timeout')):
            result = run_examples(client, 'agent', [scenario()], Mock(), persona_ids=['p'], max_seconds=30)
        self.assertFalse(result['conclusive'])
        self.assertEqual(result['failed'], 0)
        self.assertEqual(result['simulation_id'], 'sim')
        self.assertEqual(client.api.call_count, 1)

    def test_busy_workspace_is_inconclusive_without_creation_retry(self):
        client = SimpleNamespace(api=Mock(side_effect=RuntimeError('API -> 409: concurrent simulations are not allowed')),
                                 AGENT_LLM={}, SIM_LLM={})
        result = run_examples(client, 'agent', [scenario()], Mock(), persona_ids=['p'])
        self.assertFalse(result['conclusive'])
        self.assertEqual(result['status'], 'workspace_busy')
        self.assertEqual(client.api.call_count, 1)

    def test_network_creation_is_bounded_by_local_alarm(self):
        import time
        import signal
        def slow_api(*args): time.sleep(1)
        client = SimpleNamespace(api=slow_api, AGENT_LLM={}, SIM_LLM={})
        prior = signal.getsignal(signal.SIGALRM)
        result = run_examples(client, 'agent', [scenario()], Mock(), persona_ids=['p'], max_seconds=0.02)
        self.assertFalse(result['conclusive'])
        self.assertIsNone(result['simulation_id'])
        self.assertEqual(signal.getsignal(signal.SIGALRM), prior)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL)[0], 0)

    def test_a_scenario_without_source_or_fixture_is_rejected(self):
        item = scenario(); del item['source']
        with self.assertRaises(ValueError): validate_scenarios([item])
        item = scenario(); item['variables'] = None
        with self.assertRaises(ValueError): validate_scenarios([item])
