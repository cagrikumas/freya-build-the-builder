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


def call(prompt, purpose, trace, run_dir, timeout=600, images=None):
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
    return json_object(answer.read_text())
