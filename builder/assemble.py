"""Expand a compact, model-authored workflow using the supplied OpenAPI schema.

This code knows platform syntax, not bank rules. Prompts, hooks, routing and
policy calculations are generated from the input brief on every build.
"""
import copy
from validate import resolve


def assemble(artifact, api):
    workflow = copy.deepcopy(artifact['workflow'])
    api = resolve(api, api)
    base = api['servers'][0]['url'].rstrip('/')
    specs = {}
    for path, methods in api['paths'].items():
        for method, op in methods.items():
            if method.lower() not in ('post', 'get', 'put', 'patch', 'delete'):
                continue
            name = op.get('operationId') or path.rstrip('/').rsplit('/', 1)[-1]
            if name in specs: raise ValueError('Ambiguous tool name in OpenAPI: ' + name)
            specs[name] = (base + path, method.upper(), op)
    registry = artifact.get('tool_config', {})

    def bank_tool(name):
        if name not in specs: raise ValueError('Unknown bank tool: ' + name)
        url, method, op = specs[name]
        cfg = registry.get(name, {})
        schema = copy.deepcopy(op.get('requestBody', {}).get('content', {}).get('application/json', {}).get('schema', {'type': 'object', 'properties': {}}))
        for field, leaf in schema.get('properties', {}).items():
            placeholder = field if field == 'customer_id' else 'arg_' + name + '_' + field
            leaf['default'] = '{{' + placeholder + '}}'
            if field in cfg.get('field_descriptions', {}):
                leaf['description'] = cfg['field_descriptions'][field]
            if leaf.get('enum'):
                leaf['description'] = leaf.get('description', '') + ' Allowed values: ' + ', '.join(map(str, leaf['enum'])) + '.'
        tool = {'type': 'function', 'config': {'timeoutMs': 12000, 'maxRetries': 0},
                'function': {'name': name, 'handler': '__function__:api_call',
                             'description': cfg.get('description') or op.get('summary', name),
                             'parameters': {'type': 'object', 'properties': {
                                 'url': {'type': 'string', 'default': url},
                                 'method': {'type': 'string', 'default': method},
                                 'headers': {'type': 'object', 'properties': {'Content-Type': {'type': 'string', 'default': 'application/json'}}},
                                 'body': schema}}}}
        for field in ('pre_process_code', 'post_process_code', 'response_mapping'):
            if field in cfg: tool[field] = copy.deepcopy(cfg[field])
        return tool

    for name, node in workflow.get('nodes', {}).items():
        for group in ('tools', 'pre_actions'):
            if group in node:
                expanded = []
                for item in node[group]:
                    tool = bank_tool(item) if isinstance(item, str) else item
                    if group == 'pre_actions' and isinstance(item, str) and tool.get('response_mapping'):
                        node.setdefault('response_mapping', []).extend(tool.pop('response_mapping'))
                    expanded.append(tool)
                node[group] = expanded
        if 'code' in node:
            if node.get('node_type') != 'code': raise ValueError('The compact code field requires node_type=code')
            if node.get('pre_actions'): raise ValueError('Use either code or pre_actions, not both')
            code = node.pop('code')
            node['pre_actions'] = [{'type': 'function', 'function': {
                'name': 'code_exec', 'handler': '__function__:code_exec',
                'parameters': {'type': 'object', 'properties': {
                    'code': {'type': 'string', 'default': code},
                    'timeout_ms': {'type': 'number', 'default': 10000}}}}}]
        if node.get('node_type') == 'end_call' and 'terminal' not in node:
            node['on_enter'] = {'type': 'silent'}
            node['disable_inactivity_monitor'] = True
            node['transitions'] = []
            node['terminal'] = {'type': 'function', 'function': {
                'name': 'call_completed', 'handler': '__function__:end_call',
                'parameters': {'type': 'object', 'properties': {
                    'message_mode': {'type': 'string', 'default': 'none'}}}}}
    return workflow
