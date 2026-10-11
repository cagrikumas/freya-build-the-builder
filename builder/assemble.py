"""Expand a compact, model-authored workflow using the supplied OpenAPI schema.

This code knows platform syntax, not bank rules. Prompts, hooks, routing and
policy calculations are generated from the input brief on every build.
"""
import copy
import json
import re
from validate import api_operations, parameter_layout, request_pre_hook, workflow_nodes


def materialize_mappings(tool, mappings):
    """Persist mapped structured results before Freya flattens the envelope."""
    if tool.get('function', {}).get('handler') != '__function__:api_call' or not mappings:
        return
    for mapping in mappings:
        if not isinstance(mapping.get('path'), str) or not isinstance(mapping.get('variable'), str):
            raise ValueError('Response mappings require path and variable strings')
    bridge = "\ntry:\n    for _mapping in " + repr(mappings) + ":\n        try:\n            _mapped = result\n            for _part in _mapping['path'].split('.'):\n                _mapped = _mapped[int(_part)] if isinstance(_mapped, list) else _mapped[_part]\n            vars[_mapping['variable']] = _mapped\n        except (KeyError, IndexError, TypeError, ValueError):\n            pass\nexcept Exception:\n    pass\n"
    tool['post_process_code'] = tool.get('post_process_code', '') + bridge


def assemble(artifact, api):
    workflow = copy.deepcopy(artifact['workflow'])
    if 'test_variables' in workflow:
        workflow['test_variables'] = {k: v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
                                      for k, v in workflow['test_variables'].items()}
    specs = {}
    for (url, method), op in api_operations(api).items():
        name = op.get('operationId') or url.rstrip('/').rsplit('/', 1)[-1]
        if name in specs: raise ValueError('Ambiguous tool name in OpenAPI: ' + name)
        specs[name] = (url, method, op)
    registry = artifact.get('tool_config', {})

    def bank_tool(name, *, lifecycle=False):
        if name not in specs: raise ValueError('Unknown bank tool: ' + name)
        url, method, op = specs[name]
        layout = parameter_layout(op)
        declared_paths = {p['name'] for p in layout if p['in'] == 'path'}
        if set(re.findall(r'\{([^{}]+)\}', url)) != declared_paths:
            raise ValueError(f'{name}: unresolved OpenAPI path parameter')
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
        props = tool['function']['parameters']['properties']
        for parameter in layout:
            field = parameter['name']
            leaf = copy.deepcopy(parameter['schema'])
            placeholder = field if field == 'customer_id' else 'arg_' + name + '_' + parameter['in'] + '_' + field
            leaf['default'] = '{{' + placeholder + '}}'
            descriptions = cfg.get('field_descriptions', {})
            description = descriptions.get(parameter['in'] + ':' + field, descriptions.get(field))
            if description: leaf['description'] = description
            if parameter['in'] == 'header':
                container = props['headers']
                key = field
                for previous in list(container['properties']):
                    if previous.casefold() == key.casefold(): del container['properties'][previous]
            else:
                container = props['body']
                key = parameter['stage']
            container.setdefault('properties', {})[key] = leaf
            if parameter['required']: container.setdefault('required', []).append(key)
        if layout:
            tool['pre_process_code'] = request_pre_hook(cfg.get('pre_process_code', ''), url, method, layout, 'requestBody' in op)
        if lifecycle and 'alwaysRunsAt' in cfg:
            tool['config']['alwaysRunsAt'] = copy.deepcopy(cfg['alwaysRunsAt'])
        return tool

    if 'tools' in workflow:
        workflow['tools'] = [bank_tool(item, lifecycle=True) if isinstance(item, str) else item for item in workflow['tools']]
        for tool in workflow['tools']:
            materialize_mappings(tool, tool.get('response_mapping', []))
    for name, node, is_global in workflow_nodes(workflow):
        if is_global: node.setdefault('node_type', 'conversation')
        for group in ('tools', 'pre_actions'):
            if group in node:
                expanded = []
                for item in node[group]:
                    tool = bank_tool(item) if isinstance(item, str) else item
                    if group == 'pre_actions' and isinstance(item, str) and tool.get('response_mapping'):
                        node.setdefault('response_mapping', []).extend(tool.pop('response_mapping'))
                    expanded.append(tool)
                node[group] = expanded
        for tool in node.get('tools', []):
            materialize_mappings(tool, tool.get('response_mapping', []))
        for tool in node.get('pre_actions', []):
            materialize_mappings(tool, node.get('response_mapping', []))
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
