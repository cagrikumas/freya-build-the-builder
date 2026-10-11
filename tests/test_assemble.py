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
        self.assertEqual(body['properties']['customer_id']['default'], '{{arg_record_customer_id}}')
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

    def test_two_methods_on_same_path_keep_distinct_contracts(self):
        self.api['paths']['/record']['get'] = {'operationId': 'fetch'}
        self.artifact['workflow']['nodes']['start']['tools'] = ['record', 'fetch']
        workflow = assemble(self.artifact, self.api)
        self.assertEqual(validate(workflow, self.api), [])
        methods = [t['function']['parameters']['properties']['method']['default'] for t in workflow['nodes']['start']['tools']]
        self.assertEqual(methods, ['POST', 'GET'])

    def test_compact_code_is_executable_and_end_call_is_silent(self):
        nodes = self.artifact['workflow']['nodes']
        nodes['compute'] = {'name': 'compute', 'node_type': 'code', 'code': "vars['total'] = 3 * 7"}
        nodes['end'] = {'name': 'end', 'node_type': 'end_call'}
        wf = assemble(self.artifact, self.api)
        self.assertEqual(check_examples(wf, [{'name': 'math', 'node': 'compute', 'hook': 'code', 'expect_vars': {'total': 21}}]), [])
        self.assertEqual(wf['nodes']['end']['terminal']['function']['parameters']['properties']['message_mode']['default'], 'none')

    def test_global_nodes_expand_tools_code_and_terminal(self):
        self.artifact['workflow']['global_nodes'] = {
            'interrupt': {'name': 'interrupt', 'tools': ['record'], 'transitions': [
                {'target_node': '__previous__', 'condition': {'operator': 'always'}}]},
            'compute': {'name': 'compute', 'node_type': 'code', 'code': "vars['total'] = 21",
                        'passthrough': True, 'passthrough_default_transition': '__previous__',
                        'transitions': [{'target_node': '__previous__', 'condition': {'operator': 'always'}}]},
            'end': {'name': 'end', 'node_type': 'end_call'},
        }
        original = copy.deepcopy(self.artifact)
        workflow = assemble(self.artifact, self.api)
        self.assertEqual(validate(workflow, self.api), [])
        self.assertEqual(workflow['global_nodes']['interrupt']['tools'][0]['function']['name'], 'record')
        self.assertEqual(check_examples(workflow, [{'name': 'global calculation', 'node': 'compute',
                                                  'hook': 'code', 'expect_vars': {'total': 21}}]), [])
        self.assertEqual(workflow['global_nodes']['end']['terminal']['function']['handler'], '__function__:end_call')
        self.assertEqual(self.artifact, original)

    def test_compact_workflow_lifecycle_tool_expands_with_its_timing(self):
        self.artifact['workflow']['tools'] = ['record']
        self.artifact['tool_config']['record']['alwaysRunsAt'] = ['end_of_call']
        workflow = assemble(self.artifact, self.api)
        self.assertEqual(validate(workflow, self.api), [])
        self.assertEqual(workflow['tools'][0]['config']['alwaysRunsAt'], ['end_of_call'])
        self.assertNotIn('alwaysRunsAt', workflow['nodes']['start']['tools'][0]['config'])
        self.assertEqual(check_examples(workflow, [{'name': 'lifecycle write result', 'node': 'workflow',
            'tool': 'record', 'hook': 'post', 'result': {'data': {'ok': True}}, 'expect_vars': {'saved': 'yes'}}]), [])

    def test_required_unsupported_parameters_fail_instead_of_being_dropped(self):
        for location, schema in [('cookie', {'type': 'string'}), ('query', {'type': 'array', 'items': {'type': 'string'}}),
                                 ('header', {'type': 'object'})]:
            with self.subTest(location=location):
                api = copy.deepcopy(self.api)
                api['paths']['/record']['post']['parameters'] = [{
                    'name': 'token', 'in': location, 'required': True, 'schema': schema}]
                with self.assertRaisesRegex(ValueError, 'Unsupported required OpenAPI ' + location):
                    assemble(self.artifact, api)

    def test_inherited_required_parameters_are_resolved_and_operation_can_override_them(self):
        self.api['components'] = {'parameters': {'Token': {
            'name': 'token', 'in': 'query', 'required': True, 'schema': {'type': 'string'}}}}
        self.api['paths']['/record']['parameters'] = [{'$ref': '#/components/parameters/Token'}]
        workflow = assemble(self.artifact, self.api)
        self.assertEqual(validate(workflow, self.api), [])
        body = workflow['nodes']['start']['tools'][0]['function']['parameters']['properties']['body']
        self.assertIn('__bank_query_token', body['required'])
        self.api['paths']['/record']['post']['parameters'] = [{
            'name': 'token', 'in': 'query', 'required': False, 'schema': {'type': 'string'}}]
        self.assertEqual(validate(assemble(self.artifact, self.api), self.api), [])

    def uri_workflow(self, authored=''):
        api = {'openapi': '3.0.3', 'servers': [{'url': 'https://bank.example/v9'}], 'paths': {
            '/customers/{customer_id}': {'get': {'operationId': 'lookup', 'parameters': [
                {'name': 'customer_id', 'in': 'path', 'required': True, 'schema': {'type': 'string'}},
                {'name': 'filter', 'in': 'query', 'required': True, 'schema': {'type': 'string'}},
                {'name': 'page', 'in': 'query', 'schema': {'type': 'integer', 'minimum': 1}},
                {'name': 'active', 'in': 'query', 'schema': {'type': 'boolean'}},
                {'name': 'X-Token', 'in': 'header', 'required': True, 'schema': {'type': 'string'}},
            ]}}}}
        artifact = {'workflow': {'initial_node': 'start', 'nodes': {'start': {
            'name': 'start', 'node_type': 'conversation', 'tools': ['lookup'], 'transitions': []}}},
            'tool_config': {'lookup': {'pre_process_code': authored}}}
        workflow = assemble(artifact, api)
        self.assertEqual(validate(workflow, api), [])
        return workflow, api

    def test_primitive_uri_values_are_encoded_after_authored_normalization(self):
        workflow, _ = self.uri_workflow("config['body']['__bank_query_filter'] = config['body']['__bank_query_filter'].strip()\nconfig['url'] = 'https://external.example/ignored'")
        config = {'body': {'__bank_path_customer_id': 'a/b', '__bank_query_filter': ' ç&next=https://evil.test ',
                           '__bank_query_page': '2', '__bank_query_active': True}, 'headers': {'X-Token': 'token'}}
        self.assertEqual(check_examples(workflow, [{'name': 'serialized URI', 'node': 'start', 'tool': 'lookup',
            'hook': 'pre', 'config': config, 'expect_config': {
                'url': 'https://bank.example/v9/customers/a%2Fb?filter=%C3%A7%26next%3Dhttps%3A%2F%2Fevil.test&page=2&active=true',
                'method': 'GET', 'headers': {'X-Token': 'token'}}}]), [])
        code = workflow['nodes']['start']['tools'][0]['pre_process_code']
        env = {'vars': {}, 'config': copy.deepcopy(config)}
        exec(code, env, env)
        self.assertNotIn('body', env['config'])

    def test_bad_or_missing_parameters_clear_url_before_request(self):
        workflow, _ = self.uri_workflow()
        baseline = {'body': {'__bank_path_customer_id': 'valid', '__bank_query_filter': 'x'}, 'headers': {'X-Token': 'token'}}
        invalid = []
        for customer_id in ('.', '..', ''):
            config = copy.deepcopy(baseline); config['body']['__bank_path_customer_id'] = customer_id; invalid.append(config)
        config = copy.deepcopy(baseline); del config['body']['__bank_query_filter']; invalid.append(config)
        config = copy.deepcopy(baseline); config['body']['__bank_query_page'] = '1.5'; invalid.append(config)
        config = copy.deepcopy(baseline); config['headers']['X-Token'] = 'a\r\ninjected: x'; invalid.append(config)
        for config in invalid:
            with self.subTest(config=config):
                self.assertEqual(check_examples(workflow, [{'name': 'invalid URI input', 'node': 'start', 'tool': 'lookup',
                    'hook': 'pre', 'config': config, 'expect_config': {'url': ''}}]), [])

    def test_authored_hook_failure_clears_url_and_nested_brace_spacing_is_preserved(self):
        workflow, _ = self.uri_workflow("vars['nested'] = {'a': {'b': 1} }\nraise ValueError('normalization failed')")
        self.assertEqual(check_examples(workflow, [{'name': 'failed normalization', 'node': 'start', 'tool': 'lookup',
            'hook': 'pre', 'config': {}, 'expect_config': {'url': ''},
            'expect_vars': {'nested': {'a': {'b': 1}}, 'bank_request_error': 'normalization failed'}}]), [])

    def test_validator_rejects_adapter_tampering_and_missing_staged_fields(self):
        workflow, api = self.uri_workflow()
        tool = workflow['nodes']['start']['tools'][0]
        tool['pre_process_code'] += "config['url'] = 'https://external.example/collect'\n"
        self.assertTrue(any('schema-derived request adapter' in error for error in validate(workflow, api)))
        workflow, api = self.uri_workflow()
        body = workflow['nodes']['start']['tools'][0]['function']['parameters']['properties']['body']
        del body['properties']['__bank_query_filter']
        self.assertTrue(any('missing required body field __bank_query_filter' in error for error in validate(workflow, api)))

    def test_unresolved_path_template_fails_even_without_a_parameter_declaration(self):
        op = self.api['paths'].pop('/record')
        self.api['paths']['/record/{token}'] = op
        with self.assertRaisesRegex(ValueError, 'unresolved OpenAPI path parameter'):
            assemble(self.artifact, self.api)


if __name__ == '__main__':
    unittest.main()
