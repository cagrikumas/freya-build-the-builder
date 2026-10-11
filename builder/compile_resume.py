"""Import a failed compilation's unchanged evidence for syntax-only recovery."""
import hashlib
import json
from pathlib import Path
from session_trace import append_record, records


def import_failed_compile(source, destination, prompt, inputs, trace):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        raise ValueError('Resume source must be a different completed run')
    events = list(records(source / 'trace.jsonl'))
    if not events or events[-1].get('event') != 'build_end' or events[-1].get('completed') is not False:
        raise ValueError('Only an ended failed build can supply a compilation')
    manifest = events[-1].get('artifacts', {})
    actual = {}
    for path in source.rglob('*'):
        if path.is_symlink():
            raise ValueError('Resume evidence cannot contain symlinks')
        if path.is_file() and path != source / 'trace.jsonl':
            actual[path.relative_to(source).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not manifest or actual != manifest:
        raise ValueError('Failed build artifact hashes changed')
    start = next(e for e in events if e.get('event') == 'build_start')
    if start.get('inputs') != inputs:
        raise ValueError('Resume input paths or hashes differ')
    calls = [e for e in events if e.get('event') == 'model_call_start']
    captures = [e for e in events if e.get('event') == 'model_session_captured']
    ends = [e for e in events if e.get('event') == 'model_call_end']
    if (len(calls) != 1 or calls[0].get('call_id') != 'model-01'
            or len(captures) != 1 or captures[0].get('complete') is not True
            or captures[0].get('call_id') != 'model-01'
            or len(ends) != 1 or ends[0].get('error') is not False):
        raise ValueError('Resume requires exactly one successfully captured compiler transport')
    stem = source / 'model-01'
    if stem.with_suffix('.prompt.txt').read_text() != prompt:
        raise ValueError('Current compiler prompt differs from the failed call')
    answer = stem.with_suffix('.answer.json').read_text()
    try:
        json.loads(answer)
    except json.JSONDecodeError:
        pass
    else:
        raise ValueError('Resume is only for malformed JSON, not a policy or runtime failure')
    archived = list(records(stem.with_suffix('.session.jsonl')))
    capture = captures[0]
    if (capture.get('sha256') != actual['model-01.session.jsonl']
            or capture.get('records') != len(archived)):
        raise ValueError('Original compiler session capture disagrees')
    aggregate = [e for e in records(source / 'full-session.jsonl') if e.get('event') == 'codex_session_record']
    if (len(aggregate) != len(archived)
            or any(e.get('call_id') != 'model-01' or e.get('thread_id') != capture.get('thread_id')
                   or e.get('sequence') != i or e.get('record') != row
                   for i, (e, row) in enumerate(zip(aggregate, archived), 1))):
        raise ValueError('Original full trace lost or changed compiler session records')
    for suffix in ('.prompt.txt', '.answer.json', '.events.jsonl', '.stderr.txt', '.session.jsonl'):
        target = destination / ('model-01' + suffix)
        if target.exists():
            raise ValueError('Refusing to overwrite destination model evidence')
        target.write_bytes(stem.with_suffix(suffix).read_bytes())
    trace('compilation_imported', source=str(source),
          source_trace_sha256=hashlib.sha256((source / 'trace.jsonl').read_bytes()).hexdigest(),
          original_input_hashes=start['inputs'], original_builder_files=start['builder_files'],
          raw_answer_sha256=actual['model-01.answer.json'])
    for event in calls:
        trace('model_call_start', **{k:v for k,v in event.items() if k not in ('event','at')},
              imported=True, original_at=event['at'], source=str(source))
    for row in aggregate:
        append_record(destination / 'full-session.jsonl', row)
    for event in captures + ends:
        trace(event['event'], **{k:v for k,v in event.items() if k not in ('event','at')},
              imported=True, original_at=event['at'], source=str(source))
    return answer
