#!/usr/bin/env python3
"""Validate the final export and prepare the current single-case submission form."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from session_trace import validate_full_session

ROOT = Path(__file__).resolve().parent.parent


def repository_file(relative):
    path = ROOT / relative
    if Path(relative).is_absolute() or not path.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError('Submission file must be inside the repository: ' + str(relative))
    if path.is_symlink():
        raise ValueError('Submission files must not be symlinks: ' + str(relative))
    return path


def source_hashes():
    paths = [p for p in (ROOT / 'builder').glob('*') if p.is_file()]
    kit = ROOT / 'build-the-builder-v3' / 'build-the-builder'
    paths += [kit / 'freya.py', kit / 'docs/workflow-format.md', kit / 'docs/tools-and-code.md']
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def trace_artifacts(trace, final_event):
    expected = final_event.get('artifacts')
    if not isinstance(expected, dict) or not expected:
        raise ValueError('Completed build lacks its trace artifact manifest; rebuild before submission')
    current = {}
    for path in trace.parent.rglob('*'):
        if path.is_symlink():
            raise ValueError('Trace artifacts must not be symlinks: ' + str(path))
        if path.is_file() and path != trace:
            current[path.relative_to(trace.parent).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if current != expected:
        missing = sorted(set(expected) - set(current))
        added = sorted(set(current) - set(expected))
        changed = sorted(p for p in set(expected) & set(current) if expected[p] != current[p])
        raise ValueError(f'Trace artifact manifest disagrees: missing={missing}, added={added}, changed={changed}')
    return [trace, *(trace.parent / relative for relative in sorted(expected))]


def require_committed(paths):
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        try:
            committed = subprocess.check_output(['git', 'cat-file', 'blob', 'HEAD:' + relative],
                                                cwd=ROOT, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as error:
            raise ValueError('Required submission file is missing from HEAD: ' + relative) from error
        if committed != path.read_bytes():
            raise ValueError('Required submission file differs from HEAD: ' + relative)


def load_result(path):
    path = path.resolve()
    if path.is_dir(): path = path / 'result.json'
    result = json.loads(path.read_text())
    trace = repository_file(result['trace'])
    events = [json.loads(line) for line in trace.read_text().splitlines() if line.strip()]
    if not events or events[-1].get('event') != 'build_end' or not events[-1].get('completed'):
        raise ValueError(f'Build did not finish successfully: {trace}')
    start = next((e for e in events if e.get('event') == 'build_start'), {})
    current_sources = source_hashes()
    if start.get('builder_files') != current_sources:
        raise ValueError('Builder source changed after this run; rebuild before final submission')
    if events[-1].get('result') != result:
        raise ValueError('Result file disagrees with the completed build trace')
    if events[-1]['seconds'] > start.get('max_seconds', 3600):
        raise ValueError('Build exceeded its recorded deadline')
    for item in start.get('inputs', []):
        original = ROOT / item['path']
        if (original.is_symlink() or not original.is_file()
                or hashlib.sha256(original.read_bytes()).hexdigest() != item['sha256']):
            raise ValueError('Original build input is missing or changed: ' + item['path'])
    export = repository_file(result['export'])
    if hashlib.sha256(export.read_bytes()).hexdigest() != result['sha256']:
        raise ValueError(f'Export changed after this run: {export}')
    stored = json.loads(export.read_text())
    if stored.get('workflow_id') != result['workflow_id']:
        raise ValueError('Trace and export workflow IDs do not match')
    for p in (trace, export):
        if 'fak_' in p.read_text(): raise ValueError(f'API-key-like value in {p}')
    artifacts = trace_artifacts(trace, events[-1])
    session_trace = repository_file(result.get('session_trace', ''))
    if session_trace != trace.parent / 'full-session.jsonl':
        raise ValueError('Full session trace must belong to this completed build')
    validate_full_session(trace.parent, events, result)
    if path != trace.parent / 'result.json':
        raise ValueError('Use the completed trace directory or its original result.json')
    require_committed([*artifacts, export, *(ROOT / p for p in current_sources)])
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--team', required=True)
    ap.add_argument('--repo', required=True)
    ap.add_argument('--final', required=True, type=Path, help='Completed trace directory or result.json')
    ap.add_argument('--mock-url', required=True)
    ap.add_argument('--name', required=True, help='Solo member name')
    ap.add_argument('--email', required=True, help='Solo member email')
    a = ap.parse_args()
    if not a.repo.startswith('https://github.com/'):
        ap.error('Use the GitHub repository URL required by the event')
    result = load_result(a.final)
    events = [json.loads(line) for line in (ROOT / result['trace']).read_text().splitlines() if line.strip()]
    start = next(e for e in events if e.get('event') == 'build_start')
    if not start.get('folder_mode') or start.get('mock_url') != a.mock_url.rstrip('/'):
        raise ValueError('Final trace must come from the case folder and this exact mock URL')
    status = subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True)
    if status.strip():
        raise SystemExit('Commit the source, exports and traces first; the working tree must be clean.')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    command = 'python3 builder/build.py {case_folder} {mock_url}'
    if start.get('max_seconds', 3600) != 3600:
        command += ' --max-seconds ' + str(start['max_seconds'])
    if start.get('slot', 'final') != 'final':
        import shlex
        command += ' --slot ' + shlex.quote(start['slot'])
    form = {'team': a.team, 'repo': a.repo, 'commit': commit,
            'members': [{'name': a.name, 'email': a.email}],
            'run_command': command,
            'workflow': result['export'], 'trace': result['session_trace'], 'mock_url': a.mock_url.rstrip('/')}
    print(json.dumps(form, indent=2))


if __name__ == '__main__':
    main()
