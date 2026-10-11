"""Verify and import a completed builder run before evidence-driven refinement."""
import hashlib
import json
from pathlib import Path
from assemble import assemble
from session_trace import append_record, records, validate_full_session


def import_completed_run(source, destination, prompt, inputs, trace):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        raise ValueError('Refinement needs a different immutable source run')
    events = list(records(source / 'trace.jsonl'))
    if not events or events[-1].get('event') != 'build_end' or events[-1].get('completed') is not True:
        raise ValueError('Refinement requires a completed exported run')
    start, end = events[0], events[-1]
    actual = {}
    for p in source.rglob('*'):
        if p.is_symlink():
            raise ValueError('Refinement source cannot contain symlinks')
        if p.is_file() and p != source / 'trace.jsonl':
            actual[p.relative_to(source).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    if actual != end.get('artifacts'):
        raise ValueError('Original run artifact hashes changed')
    if start.get('inputs') != inputs:
        raise ValueError('Refinement input paths or hashes differ')
    if (source / 'model-01.prompt.txt').read_text() != prompt:
        raise ValueError('Refinement compiler prompt changed')
    result = json.loads((source / 'result.json').read_text())
    validate_full_session(source, events, result)
    api = json.loads((source / 'tool-api.json').read_text())
    workflow = json.loads((source / 'workflow.json').read_text())
    candidates = []
    for name in actual:
        if not name.endswith('.json'):
            continue
        try:
            item = json.loads((source / name).read_text())
            if isinstance(item, dict) and 'workflow' in item and 'checks' in item and assemble(item, api) == workflow:
                candidates.append((name, item))
        except (ValueError, TypeError, KeyError):
            continue
    if not candidates or any(item != candidates[0][1] for _, item in candidates):
        raise ValueError('No unambiguous artifact assembles to the original exported workflow')
    candidate_name, artifact = candidates[0]
    captured = {e['call_id']:e for e in events if e.get('event') == 'model_session_captured'}
    session_records = {}
    for row in records(source / 'full-session.jsonl'):
        if row.get('event') == 'codex_session_record':
            session_records.setdefault(row['call_id'], []).append(row)
    for name in actual:
        if name.startswith('model-') and '/' not in name:
            target = destination / name
            if target.exists():
                raise ValueError('Refusing to overwrite imported model evidence')
            target.write_bytes((source / name).read_bytes())
    (destination / 'resumed-artifact.json').write_bytes((source / candidate_name).read_bytes())
    trace('completed_run_imported', source=str(source), candidate=candidate_name,
          source_trace_sha256=hashlib.sha256((source / 'trace.jsonl').read_bytes()).hexdigest(),
          source_result=result, original_builder_files=start['builder_files'])
    for event in events:
        if event.get('event') not in ('model_call_start','model_session_captured','model_call_end'):
            continue
        if event['event'] == 'model_session_captured':
            for row in session_records[event['call_id']]:
                append_record(destination / 'full-session.jsonl', row)
        trace(event['event'], **{k:v for k,v in event.items() if k not in ('event','at','imported','original_at','source')},
              imported=True, original_at=event.get('original_at',event['at']), source=str(source))
    return artifact, api
