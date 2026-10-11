import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'builder'))
from assemble import assemble
from validate import check_examples, validate


class ToolBindingTests(unittest.TestCase):
    def fixtures(self):
        api = {'openapi': '3.0.3', 'servers': [{'url': 'https://service.example/v2'}], 'paths': {
            '/records/{record_ref}': {'post': {'operationId': 'inspect', 'parameters': [
                {'name': 'record_ref', 'in': 'path', 'required': True, 'schema': {'type': 'string'}},
                {'name': 'scope', 'in': 'query', 'schema': {'type': 'string', 'enum': ['brief', 'full']}},
                {'name': 'X-Region', 'in': 'header', 'required': True, 'schema': {'type': 'string'}},
            ], 'requestBody': {'content': {'application/json': {'schema': {
                'type': 'object', 'properties': {
                    'record_ref': {'type': 'string'},
                    'revision': {'type': 'integer', 'minimum': 0},
                    'mode': {'type': 'string', 'enum': ['brief', 'full']}},
                'required': ['record_ref', 'revision']}}}}}}}}
        artifact = {'workflow': {'initial_node': 'start', 'nodes': {'start': {
            'name': 'start', 'node_type': 'conversation', 'tools': ['inspect'], 'transitions': []}}},
            'tool_config': {'inspect': {'bindings': {
                'body:record_ref': 'supplied_record', 'body:revision': 'supplied_revision',
                'body:mode': 'supplied_mode', 'path:record_ref': 'route_record',
                'query:scope': 'requested_scope', 'header:X-Region': 'service_region'}}}}
        return artifact, api

    def test_explicit_body_uri_and_header_bindings_preserve_contract_and_inputs(self):
        artifact, api = self.fixtures()
        original_artifact, original_api = copy.deepcopy(artifact), copy.deepcopy(api)
        workflow = assemble(artifact, api)
        self.assertEqual(validate(workflow, api), [])
        properties = workflow['nodes']['start']['tools'][0]['function']['parameters']['properties']
        body = properties['body']['properties']
        expected = {'record_ref': 'supplied_record', 'revision': 'supplied_revision',
                    'mode': 'supplied_mode', '__bank_path_record_ref': 'route_record',
                    '__bank_query_scope': 'requested_scope'}
        for field, variable in expected.items():
            self.assertEqual(body[field]['default'], '{{' + variable + '}}')
        self.assertEqual(body['revision']['type'], 'integer')
        self.assertEqual(body['revision']['minimum'], 0)
        self.assertEqual(body['mode']['enum'], ['brief', 'full'])
        self.assertEqual(properties['body']['required'], ['record_ref', 'revision', '__bank_path_record_ref'])
        self.assertEqual(properties['headers']['properties']['X-Region']['default'], '{{service_region}}')
        self.assertEqual(artifact, original_artifact)
        self.assertEqual(api, original_api)

    def test_unbound_fields_use_model_argument_placeholders_for_each_location(self):
        artifact, api = self.fixtures()
        artifact['tool_config']['inspect'].pop('bindings')
        properties = assemble(artifact, api)['nodes']['start']['tools'][0]['function']['parameters']['properties']
        body = properties['body']['properties']
        for field, variable in {'record_ref': 'arg_inspect_record_ref',
                                '__bank_path_record_ref': 'arg_inspect_path_record_ref',
                                '__bank_query_scope': 'arg_inspect_query_scope'}.items():
            self.assertEqual(body[field]['default'], '{{' + variable + '}}')
        self.assertEqual(properties['headers']['properties']['X-Region']['default'], '{{arg_inspect_header_X-Region}}')

    def test_unknown_or_malformed_bindings_fail_instead_of_being_ignored(self):
        for bindings in ({'body:absent': 'supplied_record'}, {'record_ref': 'supplied_record'},
                         {'cookie:scope': 'requested_scope'}, {'header:x-region': 'service_region'},
                         {'body:record_ref': '{{supplied_record}}'}, {'body:record_ref': ''},
                         {'body:record_ref': 'two names'}, {'body:record_ref': 'supplied_record:json'},
                         {'body:record_ref': 'bad\x00name'},
                         {'body:record_ref': 7}, {'body:record_ref': None}, [], None):
            with self.subTest(bindings=bindings):
                artifact, api = self.fixtures()
                artifact['tool_config']['inspect']['bindings'] = bindings
                with self.assertRaisesRegex(ValueError, 'binding'):
                    assemble(artifact, api)

    def test_pre_hook_can_supply_and_transform_bound_inputs_before_uri_serialization(self):
        artifact, api = self.fixtures()
        artifact['tool_config']['inspect']['pre_process_code'] = (
            "config['body']['__bank_path_record_ref'] = vars['route_record'].strip()\n"
            "config['body']['record_ref'] = vars['supplied_record']\n"
            "config['body']['revision'] = int(vars['supplied_revision'])\n"
            "config['headers']['X-Region'] = vars['service_region']\n")
        workflow = assemble(artifact, api)
        self.assertEqual(validate(workflow, api), [])
        self.assertEqual(check_examples(workflow, [{'name': 'normalize bound request', 'node': 'start',
            'tool': 'inspect', 'hook': 'pre', 'vars': {'route_record': ' a/b ',
                'supplied_record': 'record-7', 'supplied_revision': '3', 'service_region': 'west'},
            'config': {'body': {}, 'headers': {}}, 'expect_config': {
                'url': 'https://service.example/v2/records/a%2Fb', 'method': 'POST',
                'body': {'record_ref': 'record-7', 'revision': 3}, 'headers': {'X-Region': 'west'}}}]), [])
