"""Workspace-scoped adapter around the unmodified event client."""
import time
import re


def is_availability_error(error):
    return isinstance(error, RuntimeError) and bool(re.search(
        r'-> (502|503|504)(?:\D|$)|curl error (6|7|28|35|52|56):', str(error)))


def availability_check(action, trace, name):
    """Keep a completed build exportable when a remote test cannot be measured."""
    try:
        return action()
    except RuntimeError as error:
        message = str(error)
        if not is_availability_error(error): raise
        result = {'passed': None, 'failed': 0, 'conclusive': False, 'rows': [],
                  'transport_error': message}
        trace('runtime_check_inconclusive', check=name, error=message,
              reason='Remote availability failure; do not change policy based on this result')
        return result


def bind_workspace(freya, trace=None):
    if getattr(freya, '_builder_workspace_bound', False):
        return freya
    workspace = freya.workspace_id()
    original = freya.api
    list_status_paths = set()

    def simulation_from_list(path):
        target = path.rsplit('/', 1)[-1]
        offset = 0
        while True:
            result = original('GET', '/api/v2/simulations', workspaceId=workspace, limit=100, offset=offset)
            rows = result.get('simulations', result.get('items', []))
            for row in rows:
                if row.get('id') == target:
                    if trace: trace('simulation_status_from_list', simulation_id=target, status=row.get('status'))
                    return {'simulation': row}
            if len(rows) < 100: raise RuntimeError('Simulation not present in its authenticated workspace')
            offset += 100

    def scoped_api(method, path, body=None, **params):
        # Supply explicit context after observed staging timeouts.
        # Use the authenticated key's workspace, never a guessed account ID.
        params.setdefault('workspaceId', workspace)
        if method == 'GET' and path in list_status_paths:
            return simulation_from_list(path)
        for attempt in range(2):
            started = time.monotonic()
            if trace: trace('freya_request_start', method=method, path=path, attempt=attempt)
            try:
                result = original(method, path, body, **params)
                if trace: trace('freya_request_end', method=method, path=path, seconds=round(time.monotonic()-started, 2), success=True)
                return result
            except RuntimeError as e:
                if trace: trace('freya_request_end', method=method, path=path, seconds=round(time.monotonic()-started, 2), success=False, error=str(e))
                if method == 'GET' and '-> 504' in str(e) and re.fullmatch(r'/api/v2/simulations/[a-zA-Z0-9-]+', path):
                    list_status_paths.add(path)
                    return simulation_from_list(path)
                # Repeating an identical PUT is safe; POST creation is not.
                if attempt or method not in ('GET', 'PUT') or not any('-> '+str(c) in str(e) for c in (502, 503, 504)):
                    raise
                time.sleep(3)

    freya.api = scoped_api
    freya._builder_workspace_bound = True
    return freya
