import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'builder'))
from evaluate import EvaluationTimeout, evaluation_seconds, run_examples, scenario_batches


def examples(fixtures):
    return [{'name': 'case' + str(i), 'source': 'source' + str(i),
             'prompt': 'prompt' + str(i), 'success_criteria': 'criteria' + str(i),
             'variables': {'fixture': fixture}} for i, fixture in enumerate(fixtures)]


class Client:
    AGENT_LLM = {'model': 'fixed'}
    SIM_LLM = {'model': 'customer'}

    def __init__(self, *, inconclusive=False, busy_second=False):
        self.bodies = []
        self.active = False
        self.inconclusive = inconclusive
        self.busy_second = busy_second
        self.create_personas = Mock(side_effect=lambda rows: {'personas': [
            {'id': 'p' + str(i)} for i in range(len(rows))]})

    def api(self, method, path, body=None):
        if method == 'POST':
            assert not self.active, 'A simulation was created before the prior one completed'
            if self.busy_second and len(self.bodies) == 1:
                raise RuntimeError('409 concurrent simulations are not allowed')
            self.bodies.append(body)
            self.active = True
            return {'id': 's' + str(len(self.bodies))}
        if path.endswith('/iterations'):
            return {'iterations': [{'id': 'i' + str(len(self.bodies))}]}
        self.active = False
        return {'simulation': {'status': 'completed'}}

    def get_iteration(self, simulation, iteration):
        if self.inconclusive:
            return {'runs': []}
        body = self.bodies[int(simulation[1:]) - 1]
        return {'runs': [{'personaId': pid, 'callId': simulation + '-' + pid,
                          'outcome': 'fail' if pid == 'p1' else 'pass'}
                         for pid in body['selectedPersonaIds']]}

    def get_call(self, call):
        return {'messages': [{'role': 'assistant', 'message': 'Hello ' + call}]}


class EvaluationBatchTests(unittest.TestCase):
    def test_one_duplicate_uses_11_plus_1_and_1860_seconds(self):
        scenarios = examples(list(range(11)) + [0])
        before = copy.deepcopy(scenarios)
        self.assertEqual(scenario_batches(scenarios), [list(range(11)), [11]])
        self.assertEqual(evaluation_seconds(scenarios), 1860)
        self.assertEqual(evaluation_seconds(examples(range(12))), 1380)
        self.assertEqual(scenarios, before)

    def test_equivalent_fixture_dict_order_is_not_raced(self):
        scenarios = examples(['a', 'b', 'a'])
        scenarios[0]['variables'] = {'a': 1, 'b': 2}
        scenarios[2]['variables'] = {'b': 2, 'a': 1}
        self.assertEqual(scenario_batches(scenarios), [[0, 1], [2]])

    def test_batches_finish_sequentially_and_rows_restore_original_order(self):
        scenarios = examples(['a', 'a', 'b', 'c'])
        before = copy.deepcopy(scenarios)
        client = Client()
        with patch('evaluate.time.sleep'):
            result = run_examples(client, 'agent', scenarios, Mock())
        self.assertEqual([body['selectedPersonaIds'] for body in client.bodies],
                         [['p0', 'p2', 'p3'], ['p1']])
        self.assertEqual([body['maxConcurrentCalls'] for body in client.bodies], [3, 1])
        self.assertEqual(result['persona_ids'], ['p0', 'p1', 'p2', 'p3'])
        self.assertEqual([row['name'] for row in result['rows']], [row['name'] for row in scenarios])
        self.assertEqual([row['call_id'] for row in result['rows']], ['s1-p0', 's2-p1', 's1-p2', 's1-p3'])
        self.assertEqual((result['passed'], result['failed'], result['conclusive']), (3, 1, True))
        self.assertEqual(result['simulation_ids'], ['s1', 's2'])
        self.assertEqual(result['iteration_ids'], ['i1', 'i2'])
        self.assertEqual(scenarios, before)
        created = client.create_personas.call_args.args[0]
        self.assertEqual([row['prompt'] for row in created], [row['prompt'] for row in scenarios])
        self.assertEqual([row['successCriteria'] for row in created], [row['success_criteria'] for row in scenarios])

    def test_retest_reuses_all_personas_without_recreating(self):
        client = Client()
        with patch('evaluate.time.sleep'):
            result = run_examples(client, 'agent', examples(['a', 'a', 'a']), Mock(),
                                  persona_ids=['p0', 'p1', 'p2'])
        client.create_personas.assert_not_called()
        self.assertEqual([body['maxConcurrentCalls'] for body in client.bodies], [1, 1, 1])
        self.assertEqual(result['simulation_ids'], ['s1', 's2', 's3'])

    def test_inconclusive_batch_stops_before_next_simulation(self):
        client = Client(inconclusive=True)
        with patch('evaluate.time.sleep'):
            result = run_examples(client, 'agent', examples(['a', 'a', 'b']), Mock(),
                                  persona_ids=['p0', 'p1', 'p2'])
        self.assertEqual(len(client.bodies), 1)
        self.assertFalse(result['conclusive'])
        self.assertEqual(len(result['rows']), 3)
        self.assertIn('Not started', result['rows'][1]['reason'])

    def test_second_batch_busy_retains_completed_rows_and_all_known_ids(self):
        client = Client(busy_second=True)
        with patch('evaluate.time.sleep'):
            result = run_examples(client, 'agent', examples(['a', 'a', 'b']), Mock(),
                                  persona_ids=['p0', 'p1', 'p2'])
        self.assertEqual(result['status'], 'workspace_busy')
        self.assertEqual(result['passed'], 2)
        self.assertEqual(result['simulation_ids'], ['s1'])
        self.assertEqual(result['iteration_ids'], ['i1'])
        self.assertFalse(result['conclusive'])
        self.assertEqual(result['rows'][0]['outcome'], 'pass')
        self.assertEqual(len(client.bodies), 1)

    def test_second_batch_timeout_retains_new_id_and_prior_success(self):
        client = Client()
        with patch('evaluate.time.sleep', side_effect=[None, EvaluationTimeout('timeout')]):
            result = run_examples(client, 'agent', examples(['a', 'a', 'b']), Mock(),
                                  persona_ids=['p0', 'p1', 'p2'])
        self.assertEqual(result['status'], 'evaluation_timeout')
        self.assertEqual(result['passed'], 2)
        self.assertEqual(result['simulation_ids'], ['s1', 's2'])
        self.assertEqual(result['iteration_ids'], ['i1'])
        self.assertEqual(result['batches'][1]['simulation_id'], 's2')
        self.assertFalse(result['conclusive'])

    def test_deadline_is_shared_and_expiry_blocks_later_batch_creation(self):
        client = Client()
        clock = [0]
        def sleep(seconds):
            clock[0] += seconds
        original_get_call = client.get_call
        def get_call(call):
            clock[0] = 21
            return original_get_call(call)
        client.get_call = get_call
        with patch('evaluate.time.monotonic', side_effect=lambda: clock[0]), patch('evaluate.time.sleep', side_effect=sleep):
            result = run_examples(client, 'agent', examples(['a', 'a', 'b']), Mock(),
                                  persona_ids=['p0', 'p1', 'p2'], max_seconds=20)
        self.assertEqual(len(client.bodies), 1)
        self.assertEqual(result['status'], 'evaluation_timeout')
        self.assertEqual(result['passed'], 2)
        self.assertEqual(result['simulation_ids'], ['s1'])


if __name__ == '__main__':
    unittest.main()
