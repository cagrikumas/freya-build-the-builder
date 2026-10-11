"""Apply small model-authored JSON edits without re-emitting an entire workflow."""
import copy


def apply_patches(artifact, patches):
    result = copy.deepcopy(artifact)
    for patch in patches:
        op, path = patch['op'], patch['path']
        if op not in ('add', 'replace', 'remove') or not path.startswith('/'):
            raise ValueError('Unsupported artifact patch')
        parts = [p.replace('~1', '/').replace('~0', '~') for p in path[1:].split('/')]
        parent = result
        for part in parts[:-1]:
            parent = parent[int(part)] if isinstance(parent, list) else parent[part]
        key = parts[-1]
        if isinstance(parent, list):
            index = len(parent) if key == '-' and op == 'add' else int(key)
            if index < 0 or index > len(parent) or (op != 'add' and index == len(parent)):
                raise ValueError('Patch index out of bounds: ' + path)
            if op == 'add': parent.insert(index, copy.deepcopy(patch['value']))
            elif op == 'replace': parent[index] = copy.deepcopy(patch['value'])
            else: parent.pop(index)
        elif isinstance(parent, dict):
            if op != 'add' and key not in parent: raise ValueError('Patch target missing: ' + path)
            if op == 'remove': del parent[key]
            else: parent[key] = copy.deepcopy(patch['value'])
        else:
            raise ValueError('Patch parent is not a container: ' + path)
    return result
