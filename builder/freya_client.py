"""Workspace-scoped adapter around the unmodified event client."""
import time


def bind_workspace(freya, trace=None):
    if getattr(freya, '_builder_workspace_bound', False):
        return freya
    workspace = freya.workspace_id()
    original = freya.api

    def scoped_api(method, path, body=None, **params):
        # The staging create endpoint times out without this explicit context.
        # Use the authenticated key's workspace, never a guessed account ID.
        params.setdefault('workspaceId', workspace)
        for attempt in range(2):
            started = time.monotonic()
            if trace: trace('freya_request_start', method=method, path=path, attempt=attempt)
            try:
                result = original(method, path, body, **params)
                if trace: trace('freya_request_end', method=method, path=path, seconds=round(time.monotonic()-started, 2), success=True)
                return result
            except RuntimeError as e:
                if trace: trace('freya_request_end', method=method, path=path, seconds=round(time.monotonic()-started, 2), success=False, error=str(e))
                # Repeating an identical PUT is safe; POST creation is not.
                if attempt or method not in ('GET', 'PUT') or not any('-> '+str(c) in str(e) for c in (502, 503, 504)):
                    raise
                time.sleep(3)

    freya.api = scoped_api
    freya._builder_workspace_bound = True
    return freya
