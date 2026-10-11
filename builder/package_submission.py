#!/usr/bin/env python3
"""Validate the final export and prepare the current single-case submission form."""
import argparse
import hashlib
import json
from pathlib import Path
import re
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


def require_committed(paths, commit_ref='HEAD'):
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        try:
            committed = subprocess.check_output(['git', 'cat-file', 'blob', commit_ref + ':' + relative],
                                                cwd=ROOT, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as error:
            raise ValueError('Required submission file is missing from ' + commit_ref + ': ' + relative) from error
        if committed != path.read_bytes():
            raise ValueError('Required submission file differs from ' + commit_ref + ': ' + relative)


def load_result(path, commit_ref='HEAD'):
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
    require_committed([*artifacts, export, *(ROOT / p for p in current_sources)], commit_ref=commit_ref)
    return result



def submission_reference(value, *, allow_planned=False):
    """Accept immutable object IDs or explicit tag names, never branch expressions."""
    if not isinstance(value, str) or not value or len(value) > 200:
        raise ValueError('Commit reference must be a full object SHA or safe tag name')
    head = subprocess.check_output(['git', 'rev-parse', '--verify', 'HEAD^{commit}'],
                                   cwd=ROOT, text=True, stderr=subprocess.PIPE).strip()
    if re.fullmatch(r'(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})', value):
        lookup = value.lower()
    else:
        if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]*', value)
                or value == 'HEAD' or value.startswith('refs/')):
            raise ValueError('Commit reference must be a full object SHA or safe tag name')
        lookup = 'refs/tags/' + value
        try:
            subprocess.check_output(['git', 'check-ref-format', lookup], cwd=ROOT, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as error:
            raise ValueError('Invalid planned tag name: ' + value) from error
        try:
            subprocess.check_output(['git', 'show-ref', '--verify', '--quiet', lookup],
                                    cwd=ROOT, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as error:
            if error.returncode != 1:
                raise ValueError('Unable to inspect submission tag: ' + value) from error
            if allow_planned: return value, None
            raise ValueError('Submission tag does not exist yet: ' + value) from error
    try:
        resolved = subprocess.check_output(['git', 'rev-parse', '--verify', lookup + '^{commit}'],
                                           cwd=ROOT, text=True, stderr=subprocess.PIPE).strip()
    except subprocess.CalledProcessError as error:
        raise ValueError('Submission reference does not resolve to a commit: ' + value) from error
    if resolved != head:
        raise ValueError('Existing submission reference must resolve to current HEAD: ' + value)
    return value, resolved


def final_context(result, mock_url):
    events = [json.loads(line) for line in (ROOT / result['trace']).read_text().splitlines() if line.strip()]
    start = next(e for e in events if e.get('event') == 'build_start')
    if not isinstance(mock_url, str) or not start.get('folder_mode') or start.get('mock_url') != mock_url.rstrip('/'):
        raise ValueError('Final trace must come from the case folder and this exact mock URL')
    return start


def verify_submission(path):
    """Read-only proof that all three attachments and run sources are at the named commit."""
    path = Path(path)
    if path.is_absolute():
        try: path = path.relative_to(ROOT)
        except ValueError as error: raise ValueError('Submission manifest must be inside the repository') from error
    manifest = repository_file(path)
    form = json.loads(manifest.read_text())
    if not isinstance(form, dict): raise ValueError('Submission manifest must be an object')
    reference, resolved = submission_reference(form.get('commit'))
    for key in ('workflow', 'trace'):
        if not isinstance(form.get(key), str): raise ValueError('Missing submission attachment path: ' + key)
    export, trace = repository_file(form['workflow']), repository_file(form['trace'])
    result = load_result(trace.parent / 'result.json', commit_ref=resolved)
    if form['workflow'] != result['export'] or form['trace'] != result['session_trace']:
        raise ValueError('Submission attachments do not match the completed run')
    final_context(result, form.get('mock_url'))
    require_committed([manifest, export, trace], commit_ref=resolved)
    return {'reference': reference, 'commit': resolved,
            'files': [p.relative_to(ROOT).as_posix() for p in (manifest, export, trace)]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--verify', type=Path, help='Verify committed manifest and all three exact attachments; no writes')
    ap.add_argument('--commit-ref', help='Full object SHA or planned immutable tag name; required when generating')
    ap.add_argument('--team')
    ap.add_argument('--repo')
    ap.add_argument('--final', type=Path, help='Completed trace directory or result.json')
    ap.add_argument('--mock-url')
    ap.add_argument('--name', help='Solo member name')
    ap.add_argument('--email', help='Solo member email')
    a = ap.parse_args()
    generation = ('team', 'repo', 'final', 'mock_url', 'name', 'email', 'commit_ref')
    if a.verify:
        if any(getattr(a, name) is not None for name in generation):
            ap.error('--verify must be used alone')
        print(json.dumps(verify_submission(a.verify), indent=2))
        return
    missing = ['--' + name.replace('_', '-') for name in generation if getattr(a, name) is None]
    if missing: ap.error('Required when generating: ' + ', '.join(missing))
    if not a.repo.startswith('https://github.com/'):
        ap.error('Use the GitHub repository URL required by the event')
    result = load_result(a.final)
    start = final_context(result, a.mock_url)
    status = subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True)
    if status.strip():
        raise SystemExit('Commit the source, exports and traces first; the working tree must be clean.')
    commit, _ = submission_reference(a.commit_ref, allow_planned=True)
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
