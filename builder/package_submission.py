#!/usr/bin/env python3
"""Validate two finished build exports and prepare the official submission form."""
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
    if events[-1]['seconds'] > 1800:
        raise ValueError('Build exceeded the event time limit')
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
    ap.add_argument('--hidden-1', required=True, type=Path, help='Completed trace directory or result.json')
    ap.add_argument('--hidden-2', required=True, type=Path)
    a = ap.parse_args()
    if not a.repo.startswith('https://github.com/'):
        ap.error('Use the GitHub repository URL required by the event')
    results = {name: load_result(p) for name, p in [('hidden-1', a.hidden_1), ('hidden-2', a.hidden_2)]}
    status = subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True)
    if status.strip():
        raise SystemExit('Commit the source, exports and traces first; the working tree must be clean.')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    form = {'team': a.team, 'repo': a.repo, 'commit': commit,
            'run_command': 'python3 builder/build.py {brief_path} {tool_api_path}',
            'workflows': {k: v['export'] for k, v in results.items()},
            'traces': {k: v['trace'] for k, v in results.items()}}
    print(json.dumps(form, indent=2))


if __name__ == '__main__':
    main()
