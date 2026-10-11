#!/usr/bin/env python3
"""Run the unchanged kit scorer with the authenticated workspace attached."""
import runpy
import sys
import argparse
import datetime
import hashlib
import json
from pathlib import Path
from build import load_env, KIT, ROOT
from freya_client import bind_workspace
from http_transport import install_curl_transport

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
sys.argv[0] = str(KIT / 'tools' / 'run_cases.py')
runpy.run_path(sys.argv[0], run_name='__main__')
