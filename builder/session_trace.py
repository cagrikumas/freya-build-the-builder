"""Archive only each compiler call's own Codex rollout, without shortening it."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re


MAX_SESSION_BYTES = 256 * 1024 * 1024
MAX_RECORD_BYTES = 64 * 1024 * 1024
MAX_RUN_BYTES = 1024 * 1024 * 1024
_UUID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
_SECRET_KEY = re.compile(r'(^|_)(api_key|team_key|access_token|refresh_token|id_token|client_secret|password|secret|token|authorization|cookie|credentials)$', re.I)


def redact_text(text):
    # Read runtime values only; never open an authentication or credential file.
    values = {value for key, value in os.environ.items()
              if value and (_SECRET_KEY.search(key) or key.endswith('_KEY'))}
    for value in sorted(values, key=len, reverse=True):
        text = text.replace(value, '[REDACTED]')
    text = re.sub(r'\b(?:fak_|sk-)[A-Za-z0-9_-]{8,}', '[REDACTED]', text)
    return re.sub(r'(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/-]+=*', r'\1 [REDACTED]', text)


def redact_secrets(value):
    if isinstance(value, dict):
        return {key: ('[REDACTED]' if isinstance(item, str) and _SECRET_KEY.search(str(key).replace('-', '_'))
                      else redact_secrets(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return redact_text(value) if isinstance(value, str) else value


def append_record(path, record):
    with Path(path).open('a', encoding='utf-8') as out:
        out.write(json.dumps(redact_secrets(record), ensure_ascii=False, default=str) + '\n')


def records(path, limit=MAX_SESSION_BYTES):
    """Resource limits reject a trace; they never return a shortened trace."""
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError('Missing, symlinked or oversized session trace: ' + str(path))
    consumed = 0
    with path.open('rb') as source:
        while raw := source.readline(MAX_RECORD_BYTES + 1):
            consumed += len(raw)
            if len(raw) > MAX_RECORD_BYTES or consumed > limit:
                raise ValueError('Session trace exceeds explicit size limit: ' + str(path))
            if raw.strip():
                row = json.loads(raw)
                if not isinstance(row, dict):
                    raise ValueError('Session trace record must be an object')
                yield row


def capture_session(events_path, stem, run_dir, codex_home):
    """Resolve the emitted UUID by filename, then verify metadata before copying."""
    starts = [row.get('thread_id') for row in records(events_path)
              if row.get('type') == 'thread.started']
    if len(starts) != 1 or not isinstance(starts[0], str) or not _UUID.fullmatch(starts[0]):
        raise ValueError('Model call must identify exactly one Codex session UUID')
    thread_id = starts[0]
    sessions = Path(codex_home).expanduser() / 'sessions'
    if sessions.is_symlink() or not sessions.is_dir():
        raise ValueError('Codex session directory is unavailable or symlinked')
    # Standard Codex layout. Inspect only matching filenames, never other logs.
    candidates = list(sessions.glob('????/??/??/rollout-*-' + thread_id + '.jsonl'))
    if len(candidates) != 1:
        raise ValueError('Own Codex session rollout is missing or ambiguous')
    source = candidates[0]
    if any(p.is_symlink() for p in (source, *source.parents) if p != sessions.parent):
        raise ValueError('Own Codex session path must not contain symlinks')
    if not source.resolve().is_relative_to(sessions.resolve()):
        raise ValueError('Own Codex session escaped its session directory')
    first = next(records(source), {})
    meta = first.get('payload', {})
    if first.get('type') != 'session_meta' or not isinstance(meta, dict) or meta.get('id') != thread_id:
        raise ValueError('Codex session metadata ID disagrees with this call')
    if not isinstance(meta.get('cwd'), str) or Path(meta['cwd']).resolve() != Path(run_dir).resolve():
        raise ValueError('Codex session belongs to a different working directory')
    destination = Path(stem).with_suffix('.session.jsonl')
    aggregate = Path(run_dir) / 'full-session.jsonl'
    if destination.exists():
        raise ValueError('Refusing to replace an archived Codex session')
    captured = dt.datetime.now(dt.timezone.utc).isoformat()
    count = 0
    # Keep every record, including unknown future record types. Never summarize.
    for count, row in enumerate(records(source), 1):
        clean = redact_secrets(row)
        append_record(destination, clean)
        append_record(aggregate, {'at': row.get('timestamp', captured),
                      'event': 'codex_session_record', 'call_id': Path(stem).name,
                      'thread_id': thread_id, 'sequence': count, 'record': clean})
    return {'call_id': Path(stem).name, 'thread_id': thread_id,
            'file': destination.name, 'records': count, 'complete': True,
            'redacted': True, 'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}


def validate_full_session(run_dir, events, result):
    """Check the single attachment contains milestones and all archived records."""
    run_dir = Path(run_dir)
    aggregate = run_dir / 'full-session.jsonl'
    if not result.get('session_trace') or Path(result['session_trace']).name != aggregate.name:
        raise ValueError('Build lacks its full coding-agent session trace; rebuild')
    captures = [row for row in events if row.get('event') == 'model_session_captured']
    calls = [row.get('call_id') for row in events if row.get('event') == 'model_call_start']
    if not calls or len(set(calls)) != len(calls) or set(calls) != {row.get('call_id') for row in captures} or len(captures) != len(calls):
        raise ValueError('Full session trace does not cover every model call')
    expected = {}
    counts = {}
    for row in captures:
        call_id = row['call_id']
        if not isinstance(call_id, str) or not re.fullmatch(r'model-\d+', call_id) or row.get('complete') is not True:
            raise ValueError('Incomplete or invalid model session capture')
        source = run_dir / (call_id + '.session.jsonl')
        if row.get('file') != source.name or hashlib.sha256(source.read_bytes()).hexdigest() != row.get('sha256'):
            raise ValueError('Archived model session disagrees with capture record')
        expected[call_id] = (row, iter(records(source)))
        counts[call_id] = 0
    milestones = []
    for row in records(aggregate, MAX_RUN_BYTES):
        if row.get('event') != 'codex_session_record':
            milestones.append(row)
            continue
        call_id = row.get('call_id')
        if call_id not in expected:
            raise ValueError('Unexpected model session in full trace')
        capture, source = expected[call_id]
        counts[call_id] += 1
        if (row.get('thread_id') != capture.get('thread_id') or row.get('sequence') != counts[call_id]
                or row.get('record') != next(source, None)):
            raise ValueError('Full trace changed or omitted a model session record')
    for call_id, (capture, source) in expected.items():
        if next(source, None) is not None or counts[call_id] != capture.get('records'):
            raise ValueError('Full trace omitted model session records')
    if milestones != events[:-1] or not milestones or milestones[-1].get('event') != 'run_completed':
        raise ValueError('Full trace does not preserve the completed build milestones')
    if milestones[-1].get('completed') is not True or milestones[-1].get('result') != result:
        raise ValueError('Full trace does not identify the final exported result')
    return aggregate
