#!/usr/bin/env python3
"""Run the unchanged kit scorer with the authenticated workspace attached."""
import runpy
import sys
import argparse
import datetime
import hashlib
import json
import time
from pathlib import Path
from build import load_env, KIT, ROOT
from freya_client import bind_workspace
from http_transport import install_curl_transport

resume = None
if '--resume-session' in sys.argv:
    i = sys.argv.index('--resume-session')
    resume = json.loads(Path(sys.argv[i+1]).read_text())
    sys.argv = [sys.argv[0], *resume['arguments']]
    recovery_args = argparse.ArgumentParser(add_help=False)
    recovery_args.add_argument('--reps', type=int, default=1)
    recovery_args.add_argument('--rerun-if-slow', type=int, default=0)
    recovery, _ = recovery_args.parse_known_args()
    if recovery.reps != 1 or recovery.rerun_if_slow:
        raise SystemExit('Recovery supports one repetition only; it cannot count the same simulation as multiple independent runs.')
    if not resume.get('simulation_id'):
        raise SystemExit('This session has no recorded simulation to recover.')
load_env()
import freya
install_curl_transport(freya)
bind_workspace(freya, lambda event, **data: print(json.dumps({'event': event, **data}), flush=True))
if '--publish-generated' in sys.argv:
    parser = argparse.ArgumentParser(description='Publish an unchanged generated practice workflow; not a final build trace.')
    parser.add_argument('--publish-generated', type=Path, required=True)
    parser.add_argument('--slot', required=True)
    args, rest = parser.parse_known_args()
    source = args.publish_generated.resolve()
    workflow = json.loads(source.read_text())
    ids = freya.save_workflow(args.slot, workflow, state_file=str(ROOT / '.freya-agents.json'))
    if 'version' not in ids:
        ids['version'] = freya.update_workflow(ids['workflow_id'], workflow)
    record = {'kind': 'practice_only_recovery', 'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'source': str(source.relative_to(ROOT)), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest(), **ids}
    print(json.dumps(record), flush=True)
    (source.parent / 'practice-recovery.json').write_text(json.dumps(record, indent=2))
    sys.argv = [sys.argv[0], ids['agent_id'], *rest]

# Preserve the public bank sessions before any remote wait. This allows a failed
# status request to resume scoring the SAME calls, without making a new test.
sys.path.insert(0, str(KIT / 'tools'))
import score
original_bank_http = score.http
state = resume or {'arguments': sys.argv[1:], 'sessions': {}}
out = Path(sys.argv[sys.argv.index('--out')+1]) if '--out' in sys.argv else ROOT / 'private/practice.json'
state_path = out.with_suffix('.session.json')
state_path.parent.mkdir(parents=True, exist_ok=True)
def save_state():
    state_path.write_text(json.dumps(state, indent=2))
def bank_http(path, body=None):
    if resume and path == '/v1/practice/sessions':
        return {'variables': state['sessions'][body['case']]}
    result = original_bank_http(path, body)
    if path == '/v1/practice/sessions' and 'variables' in result:
        state['sessions'][body['case']] = result['variables']
        save_state()
    return result
score.http = bank_http
original_api = freya.api
def journal_api(method, path, body=None, **params):
    result = original_api(method, path, body, **params)
    if method == 'POST' and path == '/api/v2/simulations':
        state['simulation_id'] = (result.get('simulation') or result)['id']
        save_state()
    return result
freya.api = journal_api
if resume:
    def existing_simulation(*args, **kwargs):
        sim_id = state['simulation_id']
        while True:
            current = freya.api('GET', '/api/v2/simulations/' + sim_id)
            current = current.get('simulation') or current
            if current.get('status') in ('completed', 'failed', 'paused'): break
            time.sleep(10)
        iterations = freya.api('GET', '/api/v2/simulations/' + sim_id + '/iterations')
        iterations = iterations.get('iterations') or iterations.get('items') or iterations
        return sim_id, iterations[0]['id'], current['status']
    freya.run_simulation = existing_simulation
sys.argv[0] = str(KIT / 'tools' / 'run_cases.py')
runpy.run_path(sys.argv[0], run_name='__main__')
