from pathlib import Path
import copy
import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'builder'))
from evaluate import (run_examples, summarize_runs, validate_scenarios, EvaluationTimeout,
                      compact_feedback, FEEDBACK_MAX_CHARS, FEEDBACK_ROW_CHARS)


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


class CompactFeedbackTests(unittest.TestCase):
    def summary(self, messages):
        return {'total': 1, 'passed': 0, 'failed': 1, 'conclusive': True,
                'rows': [{'name': 'document example', 'outcome': 'fail', 'reason': 'Identity failed',
                          'call_id': 'call', 'messages': messages}]}

    def system(self, event): return {'role': 'system', 'message': json.dumps(event)}

    def test_policy_evidence_survives_while_source_and_snapshots_are_removed(self):
        source = self.summary([
            {'role': 'assistant', 'message': 'İsminizi doğrular mısınız?', 'nodeId': 'identity'},
            {'role': 'user', 'message': 'Evet.'},
            self.system({'event': 'variable_extracted', 'name': 'identity_event', 'value': 'confirm',
                         'input_text': 'Evet.', 'source_node': 'identity',
                         'raw_response': 'RAW_RESPONSE_MARKER',
                         'variable_table': {'identity_event': 'stale', 'identity_prompt': 'PROMPT_SNAPSHOT_MARKER'}}),
            self.system({'event': 'function_call_start', 'function': 'code_exec',
                         'args': {'code': 'CODE_SOURCE_MARKER'*1000, 'timeout_ms': 10000}}),
            self.system({'event': 'function_call_complete', 'function': 'code_exec',
                         'result': {'status': 'success', 'status_code': 200, 'data': None,
                                    'validation_errors': ["variable 'identity_event' rejected by schema validation"]}}),
            self.system({'event': 'route_evaluated', 'from_node': 'evaluate', 'target': 'identity',
                         'matched': True, 'branches': [{'target': 'verify', 'result': False,
                         'condition_results': {'variable': 'route', 'operand': 'verify'}}],
                         'variable_table': {'route': 'identity', 'identity_event': 'confirm',
                                            'verification_state': 'pending', 'account_facts': 'FULL_SNAPSHOT_MARKER'}}),
            self.system({'event': 'function_call_start', 'function': 'record',
                         'args': {'headers': {'Authorization': 'HEADER_SECRET_MARKER'},
                                  'body': {'customer_id': 'sample', 'amount': 510, 'code': 'bank_outcome'}}}),
            self.system({'event': 'function_call_complete', 'function': 'record',
                         'result': {'status_code': 400, 'status': 'error', 'data': {'ok': False, 'reason': 'invalid date'}}})
        ])
        original = copy.deepcopy(source)
        compact = compact_feedback(source)
        self.assertEqual(source, original)
        self.assertEqual(compact['rows'][0]['name'], original['rows'][0]['name'])
        self.assertEqual(compact['rows'][0]['outcome'], 'fail')
        self.assertEqual(compact['rows'][0]['reason'], 'Identity failed')
        text = json.dumps(compact, ensure_ascii=False)
        for expected in ('İsminizi', 'Evet.', 'identity_event', 'rejected by schema validation',
                         '"amount": 510', '"customer_id": "sample"', 'bank_outcome', 'invalid date', 'verification_state'):
            self.assertIn(expected, text)
        for removed in ('CODE_SOURCE_MARKER', 'HEADER_SECRET_MARKER', 'RAW_RESPONSE_MARKER',
                        'PROMPT_SNAPSHOT_MARKER', 'FULL_SNAPSHOT_MARKER', 'variable_table', 'headers'):
            self.assertNotIn(removed, text)

    def test_malformed_or_plain_system_text_is_not_structured_evidence(self):
        source = self.summary([{'role': 'system', 'message': '{"event":"function_call_complete","result":BROKEN}'},
                               {'role': 'system', 'message': 'node_enter'},
                               self.system({'not_event': 'function_call_complete'})])
        row = compact_feedback(source)['rows'][0]
        self.assertEqual(row['feedback']['unparsed_system_messages'], 3)
        self.assertTrue(all('event' not in message for message in row['messages']))
        self.assertTrue(all(message['diagnostic']['unparsed_system_message'] for message in row['messages']))
        self.assertNotIn('BROKEN', json.dumps(row))

    def test_bounds_keep_every_scenario_and_report_omitted_events(self):
        rows = []
        for index in range(12):
            messages = [self.system({'event': 'function_call_complete', 'function': 'verify',
                        'result': {'status': 'success', 'validation_errors': ['schema rejected a value']}})]
            messages += [{'role': 'assistant', 'message': '話'*10000} for _ in range(200)]
            rows.append({'name': 'example '+str(index), 'outcome': 'fail', 'reason': 'policy mismatch', 'messages': messages})
        source = {'rows': rows, 'failed': 12}
        compact = compact_feedback(source)
        self.assertEqual(len(compact['rows']), 12)
        self.assertLessEqual(len(json.dumps(compact)), FEEDBACK_MAX_CHARS)
        for index, row in enumerate(compact['rows']):
            self.assertEqual(row['name'], 'example '+str(index))
            self.assertEqual(row['reason'], 'policy mismatch')
            self.assertEqual(row['outcome'], 'fail')
            self.assertLessEqual(len(json.dumps(row)), FEEDBACK_ROW_CHARS)
            self.assertGreater(row['feedback']['omitted_messages'], 0)
            self.assertGreater(row['feedback']['truncated_values'], 0)
            self.assertIn('schema rejected a value', json.dumps(row))

    def test_nested_payloads_giant_keys_and_oversized_system_json_are_safe(self):
        nested = {'value': 'NESTED_MARKER'*10000}
        for _ in range(100): nested = {'next': nested}
        source = self.summary([self.system({'event': 'function_call_complete', 'function': 'lookup',
                              'result': {'status_code': 200, 'data': {'K'*100000: nested}}}),
                              {'role': 'system', 'message': '{"event":' + 'X'*600000},
                              {'role': 'assistant', 'message': 'Done'}])
        compact = compact_feedback(source)
        self.assertLessEqual(len(json.dumps(compact)), FEEDBACK_MAX_CHARS)
        self.assertNotIn('NESTED_MARKER', json.dumps(compact))
        self.assertIn('Oversized or non-structured', json.dumps(compact))
        self.assertGreater(compact['rows'][0]['feedback']['truncated_values'], 0)

    def test_giant_unicode_metadata_obeys_total_bound(self):
        source = {'status': '話'*10000, 'reason': '話'*10000, 'simulation_id': '話'*10000,
                  'rows': [{'name': '話'*10000, 'outcome': '話'*10000, 'reason': '話'*10000,
                            'call_id': '話'*10000, 'agent_version': '話'*10000, 'messages': []} for _ in range(12)]}
        compact = compact_feedback(source)
        self.assertEqual(len(compact['rows']), 12)
        self.assertLessEqual(len(json.dumps(compact)), FEEDBACK_MAX_CHARS)
        self.assertTrue(all('TRUNCATED' in row['reason'] for row in compact['rows']))

    def test_scenario_count_limit_is_explicit(self):
        with self.assertRaisesRegex(ValueError, 'at most twelve'):
            compact_feedback({'rows': [{} for _ in range(13)]})

    def test_function_definitions_and_malformed_nested_metadata_cannot_expand_context(self):
        source = self.summary([self.system({'event': 'function_call_start',
                              'function': {'name': 'record', 'handler': 'api_call', 'code': 'DEFINITION_SOURCE_MARKER'*500},
                              'args': {'body': {'code': 'completed'}}})])
        source['rows'][0]['reason'] = {str(i): '話'*10000 for i in range(100)}
        compact = compact_feedback(source)
        text = json.dumps(compact)
        self.assertIn('completed', text)
        self.assertNotIn('DEFINITION_SOURCE_MARKER', text)
        self.assertLessEqual(len(text), FEEDBACK_MAX_CHARS)
        self.assertIn('large metadata value', text)

    def test_large_result_data_does_not_consume_the_validation_error_budget(self):
        data = {str(i): {'items': ['payload'*20 for _ in range(40)]} for i in range(40)}
        source = self.summary([self.system({'event': 'function_call_complete', 'function': 'code_exec',
                              'result': {'status': 'success', 'data': data,
                                         'validation_errors': ['stage enum rejected']}})])
        compact = compact_feedback(source)
        self.assertIn('stage enum rejected', json.dumps(compact))
        self.assertGreater(compact['rows'][0]['feedback']['truncated_values'], 0)

    def test_workflow_referenced_speech_for_current_and_target_nodes_is_retained(self):
        workflow = {'system_prompt': 'Address {{global_label}}.', 'nodes': {
                    'evaluate': {'task_message': 'Current fact {{computed_status}}.'},
                    'identity': {'task_message': 'Say {{computed_question}}.',
                                 'system_prompt': 'Use {{speaking_style}}.',
                                 'role_message': 'Remember {{persona_hint}}.',
                                 'on_enter': {'text': '{{entry_text}}', 'prompt': '{{entry_prompt}}'}},
                    'unrelated': {'task_message': '{{unused_bulk}}'}}}
        table = {'computed_question': {'value': 'Please tell me your date of birth.', 'confidence': 1},
                 'computed_status': {'value': 'name confirmed', 'type': 'string'},
                 'global_label': 'customer', 'speaking_style': 'brief', 'persona_hint': 'digital assistant',
                 'entry_text': 'Hello', 'entry_prompt': 'Continue the required question.',
                 'unused_bulk': 'UNRELATED_SNAPSHOT_MARKER'*500}
        source = self.summary([
            self.system({'event': 'node_enter', 'node': 'evaluate'}),
            self.system({'event': 'route_evaluated', 'target': 'identity', 'matched': True,
                         'variable_table': table}),
            {'role': 'assistant', 'message': 'Please tell me your SSN.'}])
        before = copy.deepcopy(source); before_workflow = copy.deepcopy(workflow)
        compact = compact_feedback(source, workflow=workflow)
        self.assertEqual(source, before)
        self.assertEqual(workflow, before_workflow)
        event = compact['rows'][0]['messages'][1]['event']
        self.assertEqual(event['prompt_variables']['computed_question'], 'Please tell me your date of birth.')
        self.assertEqual(event['prompt_variables']['computed_status'], 'name confirmed')
        for key in ('global_label', 'speaking_style', 'persona_hint', 'entry_text', 'entry_prompt'):
            self.assertEqual(event['prompt_variables'][key], table[key])
        self.assertNotIn('UNRELATED_SNAPSHOT_MARKER', json.dumps(compact))
        self.assertIn('SSN', json.dumps(compact))

    def test_message_node_id_and_extraction_wrappers_preserve_prompt_and_route_values(self):
        workflow = {'nodes': {'speaking': {'task_message': '{{computed_utterance}}'}}}
        source = self.summary([{'role': 'system', 'nodeId': 'speaking', 'message': json.dumps({
            'event': 'variable_extracted', 'name': 'route_choice', 'value': 'continue',
            'variable_table': {'computed_utterance': {'value': 'Ask the exact required question.'},
                               'route_choice': {'value': 'continue', 'confidence': 1}}})}])
        event = compact_feedback(source, workflow=workflow)['rows'][0]['messages'][0]['event']
        self.assertEqual(event['prompt_variables']['computed_utterance'], 'Ask the exact required question.')
        self.assertEqual(event['routing_variables']['route_choice'], 'continue')

    def test_long_referenced_prompt_values_keep_all_rows_within_original_limits(self):
        workflow = {'nodes': {'speaking': {'task_message': ' '.join('{{var_'+str(i)+'}}' for i in range(20))}}}
        table = {'var_'+str(i): {'value': '話'*20000} for i in range(20)}
        message = {'role': 'system', 'nodeId': 'speaking', 'message': {
                   'event': 'route_evaluated', 'target': 'speaking', 'variable_table': table}}
        source = {'rows': [{'name': 'example '+str(i), 'outcome': 'fail', 'reason': 'wrong speech',
                           'messages': [copy.deepcopy(message)]} for i in range(12)]}
        compact = compact_feedback(source, workflow=workflow)
        self.assertEqual(len(compact['rows']), 12)
        self.assertLessEqual(len(json.dumps(compact)), FEEDBACK_MAX_CHARS)
        for row in compact['rows']:
            self.assertLessEqual(len(json.dumps(row)), FEEDBACK_ROW_CHARS)
            self.assertGreater(row['feedback']['truncated_values'], 0)
            self.assertIn('TRUNCATED', json.dumps(row))
            event = row['messages'][0]['event']
            self.assertLessEqual(len(json.dumps(event['prompt_variables'])), 3200)
            self.assertGreater(event['prompt_variables_omitted'], 0)
