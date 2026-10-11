"""Local structural checks and hermetic examples for generated Freya workflows."""
import ast
import copy
import json
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
    return {base + path: (method.upper(), op) for path, methods in api['paths'].items()
            for method, op in methods.items() if method.lower() in ('get', 'post', 'put', 'patch', 'delete')}


def snippets(workflow):
    for nk, node in workflow['nodes'].items():
        for group in ('tools', 'pre_actions'):
            for tool in node.get(group, []):
                name = tool.get('function', {}).get('name', '')
                for field, kind in [('pre_process_code', 'pre'), ('post_process_code', 'post')]:
                    if tool.get(field):
                        yield nk, name, kind, tool[field]
                f = tool.get('function', {})
                if f.get('handler') == '__function__:code_exec':
                    code = f.get('parameters', {}).get('properties', {}).get('code', {}).get('default', '')
                    yield nk, name, 'code', code


def validate(workflow, api):
    errors = []
    ops = api_operations(api)
    nodes = workflow.get('nodes', {})
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
    for name, node in nodes.items():
        typ = node.get('node_type')
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
            if t.get('target_node') not in nodes:
                errors.append(f'{name}: unknown target {t.get("target_node")}')
            if t.get('condition', {}).get('logic') == 'and':
                errors.append(f'{name}: top-level condition logic cannot be and')
        for tool in node.get('tools', []) + node.get('pre_actions', []):
            f = tool.get('function', {})
            handler = f.get('handler')
            if handler not in ('__function__:api_call', '__function__:code_exec'):
                errors.append(f'{name}/{f.get("name")}: handler not permitted in action array')
            if handler != '__function__:api_call': continue
            props = f.get('parameters', {}).get('properties', {})
            url = props.get('url', {}).get('default')
            if url not in ops:
                errors.append(f'{name}/{f.get("name")}: URL is not an input bank endpoint')
                continue
            method, op = ops[url]
            if props.get('method', {}).get('default') != method:
                errors.append(f'{name}/{f.get("name")}: wrong HTTP method')
            expected = op.get('requestBody', {}).get('content', {}).get('application/json', {}).get('schema', {})
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
                if isinstance(n, ast.Name) and n.id in ('open', 'eval', 'exec', 'compile', '__import__', 'globals', 'locals'):
                    raise ValueError('Unsafe code name: ' + n.id)
                if isinstance(n, ast.Attribute) and n.attr.startswith('__'):
                    raise ValueError('Dunder attribute access is not allowed')
            compile(tree, f'{nk}/{tool}/{hook}', 'exec')
        except Exception as e:
            errors.append(f'{nk}/{tool}/{hook}: {e}')
    return errors


def check_examples(workflow, checks):
    code_map = {(n, t, h): c for n, t, h, c in snippets(workflow)}
    failures = []
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
            for key in ('vars', 'config', 'result'):
                if 'expect_' + key in check:
                    subset(check['expect_' + key], env[key], key)
        except Exception as e:
            failures.append(f'{check.get("name", "unnamed")}: {e}')
    return failures
