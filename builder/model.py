"""Model calls through the user's existing authenticated Codex CLI.

Each invocation compiles supplied text. It does not edit the builder or use tools.
"""
import json
import os
import subprocess
import time
import re
from pathlib import Path
from session_trace import capture_session


def json_object(text):
    text = text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find('{')
        if start >= 0:
            obj, end = json.JSONDecoder().raw_decode(text[start:])
            if not text[start + end:].strip():
                return obj
        raise


def _invoke(prompt, purpose, trace, run_dir, timeout=600, images=None):
    # Preserve the locally selected Codex model unless explicitly configured.
    config = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'config.toml'
    match = re.search(r'^model\s*=\s*"([^"]+)"', config.read_text(), re.M) if config.exists() else None
    model = os.environ.get('BUILDER_MODEL') or (match.group(1) if match else None)
    seq = len(list(run_dir.glob('model-*.prompt.txt'))) + 1
    stem = run_dir / f'model-{seq:02d}'
    trace('model_call_start', call_id=stem.name, model=model, purpose=purpose, images=[str(p) for p in (images or [])])
    stem.with_suffix('.prompt.txt').write_text(prompt)
    answer = stem.with_suffix('.answer.json')
    cmd = ['codex', 'exec', '--ignore-user-config',
           '--skip-git-repo-check', '--sandbox', 'read-only', '--json',
           '--output-last-message', str(answer),
           '-c', 'web_search="disabled"',
           '-c', 'features.multi_agent=false',
           '-c', 'features.shell_tool=false',
           '-c', 'features.apps=false',
           '-c', 'features.plugins=false',
           '-c', 'features.hooks=false',
           '-c', 'features.browser_use=false',
           '-c', 'features.computer_use=false',
           '-c', 'features.image_generation=false',
           '-c', 'features.skip_host_skill_discovery=true']
    if model:
        cmd += ['--model', model]
    effort = re.search(r'^model_reasoning_effort\s*=\s*"([^"]+)"', config.read_text(), re.M) if config.exists() else None
    if effort:
        cmd += ['-c', 'model_reasoning_effort=' + json.dumps(effort.group(1))]
    for picture in images or []:
        cmd += ['--image', str(Path(picture).resolve())]
    cmd += ['-']
    env = os.environ.copy()
    # Phone-agent secrets never need to reach the model transport.
    for key in list(env):
        if key.startswith('FREYA_'):
            env.pop(key)
    started = time.monotonic()
    instruction = 'This is a compilation request over supplied documents and any attached images. Do not call any tools, inspect files, edit files, delegate, or browse. All source material is supplied here. Return the requested JSON object only, without Markdown.\n\n'
    # Persist events during generation, so a timeout still leaves a reviewable trace.
    events_path = stem.with_suffix('.events.jsonl')
    stderr_path = stem.with_suffix('.stderr.txt')
    transport_error = None
    with events_path.open('w') as stdout, stderr_path.open('w') as stderr:
        try:
            result = subprocess.run(cmd, input=instruction + prompt, text=True,
                                    stdout=stdout, stderr=stderr, timeout=timeout,
                                    cwd=run_dir, env=env)
        except BaseException as e:
            transport_error = e
    # subprocess.run waits for a killed child too; archive its available rollout
    # after output handles close, including when the call failed or timed out.
    try:
        session = capture_session(events_path, stem, run_dir, config.parent)
        trace('model_session_captured', **session)
    except Exception as e:
        trace('model_session_capture_error', call_id=stem.name, error=str(e))
        if transport_error is None:
            transport_error = e
    if transport_error is not None:
        trace('model_call_end', call_id=stem.name, purpose=purpose, requested_model=model,
              seconds=round(time.monotonic() - started, 2), error=str(transport_error))
        raise transport_error
    output = events_path.read_text()
    if result.returncode:
        trace('model_call_end', call_id=stem.name, purpose=purpose, requested_model=model,
              seconds=round(time.monotonic() - started, 2), error=True,
              returncode=result.returncode)
        raise RuntimeError(f'Model transport exited {result.returncode}: {stderr_path.read_text()[-1500:]} {output[-1500:]}')
    events = [json.loads(line) for line in output.splitlines() if line.strip().startswith('{')]
    completed = [e for e in events if e.get('type') == 'turn.completed']
    errors = [e for e in events if e.get('type') in ('error', 'turn.failed')]
    trace('model_call_end', call_id=stem.name, purpose=purpose, requested_model=model,
          actual_models=[model] if model else [],
          seconds=round(time.monotonic() - started, 2),
          usage=[e.get('usage') for e in completed], error=bool(errors))
    if errors:
        raise RuntimeError(str(errors)[:2000])
    if not answer.exists():
        raise RuntimeError('Codex did not produce a final JSON artifact')
    return answer.read_text(), stem


def _strict_object(text):
    def invalid_constant(value):
        raise ValueError('Invalid JSON constant: ' + value)
    value = json.loads(text, parse_constant=invalid_constant)
    if not isinstance(value, dict):
        raise ValueError('Model output must be a JSON object')
    return value


def _syntax_fingerprint(text):
    # Preserve all already-valid JSON string tokens (including code/prompts),
    # and all non-structural text outside them. This deliberately refuses repairs
    # that would rewrite string contents or manufacture/change literal values.
    string = r'"(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"'
    tokens = re.findall(string, text)
    outside = re.sub(string, '', text)
    return tokens, re.sub(r'[\s{}\[\],:]', '', outside)


def _apply_syntax_edits(candidate, patch):
    if not isinstance(patch, dict) or set(patch) != {'edits'}:
        raise ValueError('Syntax repair must contain only edits')
    edits = patch['edits']
    if not isinstance(edits, list) or not 1 <= len(edits) <= 32:
        raise ValueError('Syntax repair needs 1..32 edits')
    spans = []
    total = 0
    for edit in edits:
        if not isinstance(edit, dict) or set(edit) != {'old', 'new'}:
            raise ValueError('Each syntax edit needs only old and new')
        old, new = edit['old'], edit['new']
        if not isinstance(old, str) or not isinstance(new, str) or not old or old == new:
            raise ValueError('Syntax edits need nonempty distinct string replacements')
        size = len(old.encode('utf-8')) + len(new.encode('utf-8'))
        if max(len(old.encode('utf-8')), len(new.encode('utf-8'))) > 4096:
            raise ValueError('Syntax edit exceeds 4096 bytes per string')
        total += size
        if total > 65536:
            raise ValueError('Syntax edits exceed 65536 total bytes')
        start = candidate.find(old)
        if start < 0 or candidate.find(old, start + 1) >= 0:
            raise ValueError('Syntax edit old text must occur exactly once')
        spans.append((start, start + len(old), new))
    spans.sort()
    if any(left[1] > right[0] for left, right in zip(spans, spans[1:])):
        raise ValueError('Syntax edits overlap')
    repaired = candidate
    for start, end, new in reversed(spans):
        repaired = repaired[:start] + new + repaired[end:]
    if _syntax_fingerprint(repaired) != _syntax_fingerprint(candidate):
        raise ValueError('Syntax repair changed a string token or literal value')
    return repaired


def call(prompt, purpose, trace, run_dir, timeout=600, images=None):
    deadline = time.monotonic() + timeout
    candidate, original_stem = _invoke(prompt, purpose, trace, run_dir,
                                       timeout=_remaining(deadline), images=images)
    return _recover_answer(candidate, purpose, trace, run_dir, deadline, original_stem.name)


def _remaining(deadline):
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise TimeoutError('Model call budget exhausted, including JSON syntax repair')
    return seconds


def recover_answer(raw_text, purpose, trace, run_dir, timeout=600,
                   original_call_id='prior-answer'):
    """Repair a verified prior answer; callers own prompt/session provenance checks."""
    return _recover_answer(raw_text, purpose, trace, run_dir,
                           time.monotonic() + timeout, original_call_id)


def _recover_answer(candidate, purpose, trace, run_dir, deadline, original_call_id):
    def remaining():
        return _remaining(deadline)
    for attempt in range(3):
        remaining()
        try:
            return _strict_object(candidate)
        except ValueError as error:
            diagnostic = str(error)
        if attempt == 2:
            raise ValueError('Model output remains invalid JSON after 2 syntax repairs: ' + diagnostic)
        repair_prompt = (
            'Repair only JSON syntax in the candidate below. Do not alter any policy, '
            'prompt, code, schema, string token or literal value. Only punctuation and '
            'whitespace outside already-valid JSON strings may change. Return exactly '
            '{"edits":[{"old":"unique existing substring","new":"replacement"}]}. '
            'Use 1..32 nonoverlapping edits, each old text occurring exactly once in the '
            'candidate. Include unchanged context to make matches unique. Each old/new '
            'string is at most4096 UTF-8 bytes; their combined total is at most65536 bytes. '
            'Do not return the entire candidate. Your edits must produce one strict JSON '
            'object, with no Markdown or surrounding commentary.\n'
            'Parser diagnostic: ' + diagnostic + '\nCandidate:\n' + candidate)
        trace('model_json_repair_start', original_call_id=original_call_id,
              attempt=attempt + 1, diagnostic=diagnostic)
        try:
            output, repair_stem = _invoke(repair_prompt, purpose + ' JSON syntax repair',
                                         trace, run_dir, timeout=remaining())
            remaining()
            patch = _strict_object(output)
            repaired = _apply_syntax_edits(candidate, patch)
            # Keep the raw original answer and repair answer unchanged. Archive
            # each candidate separately for review and later semantic validation.
            repaired_path = repair_stem.with_suffix('.repaired-candidate.json')
            repaired_path.write_text(repaired)
            trace('model_json_repair_end', original_call_id=original_call_id,
                  attempt=attempt + 1, candidate=str(repaired_path), error=False)
            candidate = repaired
        except (ValueError, TypeError) as error:
            trace('model_json_repair_end', original_call_id=original_call_id,
                  attempt=attempt + 1, error=str(error))
            if attempt == 1:
                raise ValueError('JSON syntax repair failed: ' + str(error)) from error
