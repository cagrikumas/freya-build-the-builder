import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'builder'))
from assemble import assemble
from validate import validate, check_examples


class AssemblyTests(unittest.TestCase):
    def setUp(self):
        self.api = {'openapi': '3.0.3', 'servers': [{'url': 'https://bank.example/v9'}],
                    'paths': {'/record': {'post': {'operationId': 'record',
                        'requestBody': {'content': {'application/json': {'schema': {
                            'type': 'object', 'properties': {
                                'customer_id': {'type': 'string'},
                                'amount_minor': {'type': 'integer'},
                                'resolution': {'type': 'string', 'enum': ['new', 'retry']}},
                            'required': ['customer_id', 'amount_minor']}}}}}}}}
        self.artifact = {'workflow': {'initial_node': 'start', 'nodes': {
            'start': {'name': 'start', 'node_type': 'conversation', 'tools': ['record'], 'transitions': []}}},
            'tool_config': {'record': {'post_process_code': "vars['saved'] = 'yes' if result['data']['ok'] else 'no'"}}}

    def test_input_schema_changes_are_preserved_and_inputs_untouched(self):
        source, artifact = copy.deepcopy(self.api), copy.deepcopy(self.artifact)
        wf = assemble(self.artifact, self.api)
        tool = wf['nodes']['start']['tools'][0]
        props = tool['function']['parameters']['properties']
        body = props['body']
        self.assertEqual(props['url']['default'], 'https://bank.example/v9/record')
        self.assertEqual(body['required'], ['customer_id', 'amount_minor'])
        self.assertEqual(body['properties']['amount_minor']['type'], 'integer')
        self.assertEqual(body['properties']['resolution']['enum'], ['new', 'retry'])
        self.assertEqual(body['properties']['customer_id']['default'], '{{customer_id}}')
        self.assertEqual(body['properties']['amount_minor']['default'], '{{arg_record_amount_minor}}')
        self.assertEqual(validate(wf, self.api), [])
        self.assertEqual(self.api, source)
        self.assertEqual(self.artifact, artifact)

    def test_pre_action_mappings_are_attached_to_node(self):
        self.artifact['workflow']['nodes']['start'] = {'name': 'start', 'node_type': 'api_request', 'pre_actions': ['record']}
        mapping = [{'path': 'data.ok', 'variable': 'saved'}]
        self.artifact['tool_config']['record']['response_mapping'] = mapping
        node = assemble(self.artifact, self.api)['nodes']['start']
        self.assertEqual(node['response_mapping'], mapping)
        self.assertNotIn('response_mapping', node['pre_actions'][0])

    def test_mapped_structures_survive_before_platform_flattens_results(self):
        self.artifact['workflow']['nodes']['start'] = {'name': 'start', 'node_type': 'api_request', 'pre_actions': ['record']}
        self.artifact['tool_config']['record']['response_mapping'] = [
            {'path': 'data.items', 'variable': 'account_items'},
            {'path': 'data.items.0.code', 'variable': 'first_code'},
            {'path': 'data.absent', 'variable': 'missing'},
        ]
        workflow = assemble(self.artifact, self.api)
        items = [{'code': 'new-schema-value', 'total': 27.5}]
        checks = [{'name': 'structured pre-action result', 'node': 'start', 'tool': 'record', 'hook': 'post',
                   'result': {'data': {'ok': True, 'items': items}},
                   'expect_vars': {'account_items': items, 'first_code': 'new-schema-value', 'saved': 'yes'}}]
        self.assertEqual(check_examples(workflow, checks), [])

    def test_test_variables_are_platform_strings_without_mutating_artifact(self):
        original = {'attempts': 0, 'ready': False, 'items': ['a'], 'digits': '0007'}
        self.artifact['workflow']['test_variables'] = original.copy()
        workflow = assemble(self.artifact, self.api)
        self.assertEqual(workflow['test_variables'], {'attempts': '0', 'ready': 'false', 'items': '["a"]', 'digits': '0007'})
        self.assertEqual(self.artifact['workflow']['test_variables'], original)

    def test_generated_hook_executes_on_expanded_tool(self):
        wf = assemble(self.artifact, self.api)
        checks = [{'name': 'failed write', 'node': 'start', 'tool': 'record', 'hook': 'post',
                   'result': {'data': {'ok': False}}, 'expect_vars': {'saved': 'no'}}]
        self.assertEqual(check_examples(wf, checks), [])

    def test_unknown_bank_tool_is_rejected(self):
        self.artifact['workflow']['nodes']['start']['tools'] = ['invented_action']
        with self.assertRaisesRegex(ValueError, 'Unknown bank tool'):
            assemble(self.artifact, self.api)

    def test_compact_code_is_executable_and_end_call_is_silent(self):
        nodes = self.artifact['workflow']['nodes']
        nodes['compute'] = {'name': 'compute', 'node_type': 'code', 'code': "vars['total'] = 3 * 7"}
        nodes['end'] = {'name': 'end', 'node_type': 'end_call'}
        wf = assemble(self.artifact, self.api)
        self.assertEqual(check_examples(wf, [{'name': 'math', 'node': 'compute', 'hook': 'code', 'expect_vars': {'total': 21}}]), [])
        self.assertEqual(wf['nodes']['end']['terminal']['function']['parameters']['properties']['message_mode']['default'], 'none')


if __name__ == '__main__':
    unittest.main()
