"""Local structural checks and hermetic examples for generated Freya workflows."""
import ast
import copy
import json
import re
import textwrap
import urllib.parse


def resolve(obj, api):
    if isinstance(obj, dict):
        if '$ref' in obj:
            ref = obj['$ref']
            if not ref.startswith('#/'):
                raise ValueError('Only local OpenAPI references are supported')
            out = api
            for part in ref[2:].split('/'):
                out = out[part.replace('~1', '/').replace('~0', '~')]
            return resolve(out, api)
        return {k: resolve(v, api) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve(v, api) for v in obj]
    return obj


def api_operations(api):
    api = resolve(api, api)
    base = api['servers'][0]['url'].rstrip('/')
    operations = {}
    for path, methods in api['paths'].items():
        for method, op in methods.items():
            if method.lower() not in ('get', 'post', 'put', 'patch', 'delete'):
                continue
            op = copy.deepcopy(op)
            parameters = {(p['name'], p['in']): p for p in methods.get('parameters', [])}
            parameters.update({(p['name'], p['in']): p for p in op.get('parameters', [])})
            if parameters: op['parameters'] = list(parameters.values())
            operations[(base + path, method.upper())] = op
    return operations


def parameter_layout(op):
    """Primitive OpenAPI parameters exposed using documented api_call fields."""
    body = op.get('requestBody', {}).get('content', {}).get('application/json', {}).get('schema', {})
    used = set(body.get('properties', {}))
    layout = []
    for parameter in op.get('parameters', []):
        location, name = parameter['in'], parameter['name']
        schema = parameter.get('schema', {})
        required = bool(parameter.get('required') or location == 'path')
        style = parameter.get('style', 'form' if location == 'query' else 'simple')
        if (location not in ('path', 'query', 'header') or schema.get('type') not in ('string', 'integer', 'number', 'boolean')
                or style != ('form' if location == 'query' else 'simple') or parameter.get('allowReserved')):
            if required: raise ValueError(f'Unsupported required OpenAPI {location} parameter {name}: type or serialization')
            continue
        if location == 'header' and not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name):
            raise ValueError('Invalid OpenAPI header name: ' + name)
        stage = '__bank_' + location + '_' + name
        while stage in used: stage = '_' + stage
        used.add(stage)
        layout.append({'name': name, 'in': location, 'required': required, 'stage': stage, 'schema': schema})
    return layout


def request_pre_hook(authored, url, method, layout, has_body=False):
    """Normalize first, then serialize URI parameters without trusting caller URLs."""
    authored = (authored or 'pass').rstrip('\n')
    ast.parse(authored)
    spec = [{'name': p['name'], 'in': p['in'], 'required': p['required'], 'stage': p['stage'],
             **{k: v for k, v in p['schema'].items() if k in (
                 'type', 'enum', 'minLength', 'maxLength', 'pattern', 'minimum', 'maximum')}} for p in layout]
    encoded = repr(json.dumps(spec, ensure_ascii=True)).replace('{', r'\x7b').replace('}', r'\x7d')
    serialization = '''import json
import re
_bank_parameters = json.loads(SPEC)
_bank_body = config.setdefault('body', {})
_bank_headers = config.setdefault('headers', {})
if not isinstance(_bank_body, dict) or not isinstance(_bank_headers, dict):
    raise ValueError('Bank request body and headers must be objects')
def _bank_encode(value):
    return ''.join(chr(byte) if byte in b'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~' else '%' + format(byte, '02X') for byte in value.encode('utf-8'))
def _bank_scalar(value, parameter):
    kind = parameter['type']
    if isinstance(value, (dict, list, tuple)):
        raise ValueError('Bank parameter must be primitive: ' + parameter['name'])
    if kind == 'boolean':
        if value is True or value is False: parsed = value
        elif isinstance(value, str) and value.lower() in ('true', 'false'): parsed = value.lower() == 'true'
        else: raise ValueError('Invalid boolean bank parameter')
        text = 'true' if parsed else 'false'
    elif kind in ('integer', 'number'):
        if isinstance(value, bool): raise ValueError('Invalid numeric bank parameter')
        parsed = float(value)
        if parsed != parsed or abs(parsed) == float('inf'): raise ValueError('Non-finite bank parameter')
        if kind == 'integer':
            if not parsed.is_integer(): raise ValueError('Invalid integer bank parameter')
            parsed = int(value) if isinstance(value, (str, int)) else int(parsed)
        text = str(parsed)
        if 'minimum' in parameter and parsed < parameter['minimum']: raise ValueError('Bank parameter below minimum')
        if 'maximum' in parameter and parsed > parameter['maximum']: raise ValueError('Bank parameter above maximum')
    else:
        parsed = str(value)
        text = parsed
        if 'minLength' in parameter and len(text) < parameter['minLength']: raise ValueError('Bank parameter too short')
        if 'maxLength' in parameter and len(text) > parameter['maxLength']: raise ValueError('Bank parameter too long')
        if 'pattern' in parameter and re.search(parameter['pattern'], text) is None: raise ValueError('Bank parameter pattern mismatch')
    if 'enum' in parameter and parsed not in parameter['enum']: raise ValueError('Bank parameter outside enum')
    return text
_bank_url = URL
_bank_query = []
for _bank_parameter in _bank_parameters:
    _bank_location = _bank_parameter['in']
    if _bank_location == 'header':
        _bank_value = _bank_headers.get(_bank_parameter['name'])
    else:
        _bank_value = _bank_body.pop(_bank_parameter['stage'], None)
    if _bank_value is None or (isinstance(_bank_value, str) and _bank_value.startswith(chr(123) * 2) and _bank_value.endswith(chr(125) * 2)):
        if _bank_parameter['required']: raise ValueError('Missing bank parameter: ' + _bank_parameter['name'])
        if _bank_location == 'header': _bank_headers.pop(_bank_parameter['name'], None)
        continue
    _bank_text = _bank_scalar(_bank_value, _bank_parameter)
    if _bank_location == 'path':
        if not _bank_text: raise ValueError('Empty bank path parameter')
        if _bank_text in ('.', '..'): raise ValueError('Bank path parameter cannot be a dot segment')
        _bank_url = _bank_url.replace(chr(123) + _bank_parameter['name'] + chr(125), _bank_encode(_bank_text))
    elif _bank_location == 'query':
        _bank_query.append(_bank_encode(_bank_parameter['name']) + '=' + _bank_encode(_bank_text))
    else:
        if '\\r' in _bank_text or '\\n' in _bank_text: raise ValueError('Invalid bank header value')
        _bank_headers[_bank_parameter['name']] = _bank_text
if chr(123) in _bank_url or chr(125) in _bank_url: raise ValueError('Unresolved bank path parameter')
if _bank_query: _bank_url += '?' + '&'.join(_bank_query)
config['url'] = _bank_url
config['method'] = METHOD
if not KEEP_BODY and not _bank_body: config.pop('body', None)
'''
    literals = {'SPEC': encoded, 'URL': repr(url), 'METHOD': repr(method), 'KEEP_BODY': repr(has_body)}
    serialization = re.sub(r'\b(SPEC|URL|METHOD|KEEP_BODY)\b', lambda match: literals[match.group()], serialization)
    return ('# Bank parameter adapter\ntry:\n    # Begin authored hook\n' + textwrap.indent(authored, '    ')
            + '\n    # End authored hook\n' + textwrap.indent(serialization.rstrip(), '    ')
            + "\nexcept Exception as _bank_error:\n    config['url'] = ''\n    vars['bank_request_error'] = str(_bank_error)\n")


def adapter_matches(code, url, method, layout, has_body=False):
    prefix = '# Bank parameter adapter\ntry:\n    # Begin authored hook\n'
    marker = '\n    # End authored hook\n'
    if not isinstance(code, str) or not code.startswith(prefix) or marker not in code: return False
    authored = textwrap.dedent(code[len(prefix):].rsplit(marker, 1)[0])
    try: return code == request_pre_hook(authored, url, method, layout, has_body)
    except (SyntaxError, ValueError, TypeError): return False


def workflow_nodes(workflow):
    for group in ('nodes', 'global_nodes'):
        for name, node in workflow.get(group, {}).items():
            yield name, node, group == 'global_nodes'


def actions(workflow):
    """Visit every documented position that executes a function or its hooks."""
    for tool in workflow.get('tools', []):
        yield 'workflow', 'lifecycle_tools', tool
    for name, node, _ in workflow_nodes(workflow):
        for group in ('tools', 'pre_actions'):
            for tool in node.get(group, []):
                yield name, group, tool
        if 'terminal' in node:
            yield name, 'terminal', node['terminal']


def snippets(workflow):
    for nk, _, tool in actions(workflow):
        if not isinstance(tool, dict): continue
        name = tool.get('function', {}).get('name', '')
        for field, kind in [('pre_process_code', 'pre'), ('post_process_code', 'post')]:
            if tool.get(field):
                yield nk, name, kind, tool[field]
        f = tool.get('function', {})
        if f.get('handler') == '__function__:code_exec':
            code = f.get('parameters', {}).get('properties', {}).get('code', {}).get('default', '')
            yield nk, name, 'code', code


def variable_text(value):
    """Compare declared enum values as scalars stored in Freya's variable table."""
    if isinstance(value, str): return value
    if value is True: return 'true'
    if value is False: return 'false'
    if value is None: return 'null'
    if isinstance(value, (int, float)): return str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def extraction_contracts(workflow):
    declarations = [(name, node.get('extraction_schema', [])) for name, node, _ in workflow_nodes(workflow)]
    declarations += [(name + '/' + str(tool.get('function', {}).get('name', '')),
                      tool.get('extraction_schema', [])) for name, _, tool in actions(workflow) if isinstance(tool, dict)]
    contracts, errors = {}, []
    for source, fields in declarations:
        if not isinstance(fields, list):
            errors.append(source + ': extraction_schema must be an array')
            continue
        for field in fields:
            if not isinstance(field, dict) or not isinstance(field.get('name'), str) or not field['name']:
                errors.append(source + ': extraction field needs a name')
                continue
            name = field['name']
            kind = field.get('type', 'string')
            if kind == 'enum': kind = 'string'
            values = field.get('enum_values', [])
            if not isinstance(values, list):
                errors.append(f'{source}/{name}: enum_values must be an array')
                continue
            allowed = frozenset(variable_text(value) for value in values) if values else None
            signature = (kind, allowed, field.get('validation_pattern'))
            previous = contracts.get(name)
            if previous and previous['signature'] != signature:
                errors.append(f"Extraction variable '{name}' has incompatible schemas in {previous['source']} and {source}; "
                              'use distinct names or identical type, enum_values and validation_pattern')
            else:
                contracts.setdefault(name, {'source': source, 'signature': signature, 'allowed': allowed})
    return contracts, errors


def validate(workflow, api):
    errors = []
    ops = api_operations(api)
    allowed_urls = {url for url, method in ops}
    nodes = workflow.get('nodes', {})
    global_nodes = workflow.get('global_nodes', {})
    targets = set(nodes) | set(global_nodes)
    for name in set(nodes) & set(global_nodes):
        errors.append(f'{name}: normal and global node names must be distinct')
    if workflow.get('initial_node') not in nodes:
        errors.append('initial_node is missing')
    if 'agent_config' in workflow:
        errors.append('Omit agent_config')
    def walk(obj, path='workflow'):
        if obj is None:
            errors.append(path + ' is null')
        if isinstance(obj, dict):
            for k, v in obj.items(): walk(v, path + '.' + k)
        elif isinstance(obj, list):
            for i, v in enumerate(obj): walk(v, path + f'[{i}]')
    walk(workflow)
    _, extraction_errors = extraction_contracts(workflow)
    errors.extend(extraction_errors)
    for name, node, is_global in workflow_nodes(workflow):
        typ = node.get('node_type', 'conversation' if is_global else None)
        if typ not in ('conversation', 'code', 'api_request', 'end_call'):
            errors.append(f'{name}: unsupported node_type {typ}')
        if node.get('name') != name:
            errors.append(f'{name}: name must equal map key')
        if typ != 'conversation' and node.get('tools'):
            errors.append(f'{name}: tools would be stripped')
        if typ == 'conversation' and node.get('pre_actions'):
            errors.append(f'{name}: pre_actions would be stripped')
        transitions = node.get('transitions', [])
        if node.get('passthrough') and (not transitions or transitions[-1].get('condition', {}).get('operator') != 'always'):
            errors.append(f'{name}: passthrough requires last always transition')
        for t in transitions:
            if t.get('target_node') not in targets and not (is_global and t.get('target_node') == '__previous__'):
                errors.append(f'{name}: unknown target {t.get("target_node")}')
            if t.get('condition', {}).get('logic') == 'and':
                errors.append(f'{name}: top-level condition logic cannot be and')
        for field in ('passthrough_default_transition', 'max_turn_transition'):
            target = node.get(field)
            if target is not None and target not in targets and not (is_global and target == '__previous__'):
                errors.append(f'{name}: unknown {field} {target}')
        if 'terminal' in node and typ != 'end_call':
            errors.append(f'{name}: terminal requires node_type=end_call')
    for name, group, tool in actions(workflow):
        if not isinstance(tool, dict):
            errors.append(f'{name}/{group}: action must be a function object')
            continue
        f = tool.get('function', {})
        handler = f.get('handler')
        allowed_handlers = ('__function__:end_call',) if group == 'terminal' else ('__function__:api_call', '__function__:code_exec')
        if handler not in allowed_handlers:
            errors.append(f'{name}/{f.get("name")}: handler not permitted in {group}')
        lifecycle = tool.get('config', {}).get('alwaysRunsAt')
        if group == 'lifecycle_tools' or lifecycle is not None:
            if (not isinstance(lifecycle, list) or not lifecycle
                    or any(value not in ('start_of_call', 'end_of_call') for value in lifecycle)):
                errors.append(f'{name}/{f.get("name")}: lifecycle tools require implemented alwaysRunsAt values')
        if handler != '__function__:api_call': continue
        props = f.get('parameters', {}).get('properties', {})
        url = props.get('url', {}).get('default')
        if url not in allowed_urls:
            errors.append(f'{name}/{f.get("name")}: URL is not an input bank endpoint')
            continue
        op = ops.get((url, props.get('method', {}).get('default')))
        if op is None:
            errors.append(f'{name}/{f.get("name")}: wrong HTTP method')
            continue
        try:
            layout = parameter_layout(op)
        except ValueError as error:
            errors.append(f'{name}/{f.get("name")}: {error}')
            continue
        declared_paths = {p['name'] for p in layout if p['in'] == 'path'}
        if set(re.findall(r'\{([^{}]+)\}', url)) != declared_paths:
            errors.append(f'{name}/{f.get("name")}: unresolved OpenAPI path parameter')
        if layout and not adapter_matches(tool.get('pre_process_code'), url, props.get('method', {}).get('default'), layout, 'requestBody' in op):
            errors.append(f'{name}/{f.get("name")}: non-body parameters require the schema-derived request adapter')
        expected = copy.deepcopy(op.get('requestBody', {}).get('content', {}).get('application/json', {}).get('schema', {}))
        for parameter in layout:
            if parameter['in'] == 'header':
                header = props.get('headers', {}).get('properties', {}).get(parameter['name'])
                if header is None:
                    if parameter['required']: errors.append(f'{name}/{f.get("name")}: missing required header {parameter["name"]}')
                elif header.get('type') != parameter['schema'].get('type') or 'default' not in header:
                    errors.append(f'{name}/{f.get("name")}: malformed header parameter {parameter["name"]}')
            else:
                expected.setdefault('properties', {})[parameter['stage']] = parameter['schema']
                if parameter['required']: expected.setdefault('required', []).append(parameter['stage'])
        fields = props.get('body', {}).get('properties', {})
        for field in expected.get('required', []):
            if field not in fields: errors.append(f'{name}/{f.get("name")}: missing required body field {field}')
        for field, schema in fields.items():
            target = expected.get('properties', {}).get(field)
            if target is None:
                errors.append(f'{name}/{f.get("name")}: invented body field {field}'); continue
            if schema.get('type') != target.get('type'):
                errors.append(f'{name}/{f.get("name")}/{field}: wrong type')
            if 'default' not in schema:
                errors.append(f'{name}/{f.get("name")}/{field}: leaf must have default')
            if target.get('enum') and not set(schema.get('enum', target['enum'])).issubset(target['enum']):
                errors.append(f'{name}/{f.get("name")}/{field}: invented enum')
    for nk, tool, hook, code in snippets(workflow):
        try:
            if '{{' in code or '}}' in code: raise ValueError('Code contains template braces')
            tree = ast.parse(code)
            for n in ast.walk(tree):
                if isinstance(n, (ast.Import, ast.ImportFrom)):
                    modules = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module]
                    if any(m not in ('datetime', 'json', 're') for m in modules):
                        raise ValueError('Only datetime, json, re imports are allowed')
                if isinstance(n, ast.Name) and (n.id.startswith('__') or n.id in ('open', 'eval', 'exec', 'compile', 'globals', 'locals')):
                    raise ValueError('Unsafe code name: ' + n.id)
                if isinstance(n, ast.Attribute) and n.attr.startswith('__'):
                    raise ValueError('Dunder attribute access is not allowed')
            compile(tree, f'{nk}/{tool}/{hook}', 'exec')
        except Exception as e:
            errors.append(f'{nk}/{tool}/{hook}: {e}')
    return errors


def check_examples(workflow, checks):
    code_map = {(n, t, h): c for n, t, h, c in snippets(workflow)}
    contracts, failures = extraction_contracts(workflow)
    def subset(expected, actual, path):
        if isinstance(expected, dict):
            for k, v in expected.items():
                if k not in actual: raise AssertionError(f'{path}.{k} missing')
                subset(v, actual[k], path + '.' + k)
        elif expected != actual:
            raise AssertionError(f'{path}: expected {expected!r}, got {actual!r}')
    for check in checks:
        try:
            matches = [c for (n, t, h), c in code_map.items() if n == check['node'] and h == check['hook'] and ('tool' not in check or t == check['tool'])]
            if len(matches) != 1: raise ValueError('Check must identify exactly one code snippet')
            env = {'vars': copy.deepcopy(check.get('vars', {})), 'config': copy.deepcopy(check.get('config', {})), 'result': copy.deepcopy(check.get('result', {}))}
            exec(matches[0], env, env)
            enum_errors = []
            for name, contract in contracts.items():
                if contract['allowed'] is not None and name in env['vars']:
                    value = env['vars'][name]
                    if variable_text(value) not in contract['allowed']:
                        enum_errors.append(f"vars.{name}: value {value!r} is outside declared enum_values "
                                           f"{sorted(contract['allowed'])!r}")
            if enum_errors:
                raise AssertionError('; '.join(enum_errors) + '; resets must use a declared sentinel or remove the key')
            for key in ('vars', 'config', 'result'):
                if 'expect_' + key in check:
                    subset(check['expect_' + key], env[key], key)
        except Exception as e:
            failures.append(f'{check.get("name", "unnamed")}: {e}')
    return failures
