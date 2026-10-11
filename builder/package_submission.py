#!/usr/bin/env python3
"""Validate the final export and prepare the current single-case submission form."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent


def load_result(path):
    path = path.resolve()
    if path.is_dir(): path = path / 'result.json'
    result = json.loads(path.read_text())
    trace = ROOT / result['trace']
    events = [json.loads(line) for line in trace.read_text().splitlines() if line.strip()]
    if not events or events[-1].get('event') != 'build_end' or not events[-1].get('completed'):
        raise ValueError(f'Build did not finish successfully: {trace}')
    start = next((e for e in events if e.get('event') == 'build_start'), {})
    current_sources = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in sorted((ROOT / 'builder').glob('*')) if p.is_file()}
    if start.get('builder_files') != current_sources:
        raise ValueError('Builder source changed after this run; rebuild before final submission')
    if events[-1].get('result') != result:
        raise ValueError('Result file disagrees with the completed build trace')
    if events[-1]['seconds'] > start.get('max_seconds', 3600):
        raise ValueError('Build exceeded its recorded deadline')
    export = ROOT / result['export']
    if hashlib.sha256(export.read_bytes()).hexdigest() != result['sha256']:
        raise ValueError(f'Export changed after this run: {export}')
    stored = json.loads(export.read_text())
    if stored.get('workflow_id') != result['workflow_id']:
        raise ValueError('Trace and export workflow IDs do not match')
    for p in (trace, export):
        if 'fak_' in p.read_text(): raise ValueError(f'API-key-like value in {p}')
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
            'workflow': result['export'], 'trace': result['trace'], 'mock_url': a.mock_url.rstrip('/')}
    print(json.dumps(form, indent=2))


if __name__ == '__main__':
    main()
