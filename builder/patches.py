"""Apply small model-authored JSON edits without re-emitting an entire workflow."""
import copy


class PatchError(ValueError):
    def __init__(self, index, patch, reason):
        self.index = index
        self.patch = patch
        super().__init__(f'Patch {index} at {patch.get("path")!r}: {reason}')


def apply_patches(artifact, patches):
    result = copy.deepcopy(artifact)
    for index, patch in enumerate(patches):
        try:
            apply_one(result, patch)
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as error:
            raise PatchError(index, patch if isinstance(patch, dict) else {}, str(error)) from error
    return result


def apply_one(result, patch):
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


def apply_with_path_repair(artifact, patches, repair, limit=3):
    """Keep every audit edit and value; ask the model to repair invalid pointers."""
    edits = copy.deepcopy(patches)
    for attempt in range(limit + 1):
        try:
            return apply_patches(artifact, edits)
        except PatchError as error:
            if attempt == limit:
                raise
            answer = repair(artifact, edits, error)
            if (not isinstance(answer, dict) or set(answer) != {'path'}
                    or not isinstance(answer['path'], str)
                    or not answer['path'].startswith('/')
                    or answer['path'] == edits[error.index].get('path')):
                raise ValueError('Audit pointer repair must return one changed absolute path')
            edits[error.index]['path'] = answer['path']
