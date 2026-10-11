#!/usr/bin/env python3
"""Run additional source-backed Freya conversations without editing an agent."""
import argparse
import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'builder'))
from build import load_env
from evaluate import run_examples, validate_scenarios
from freya_client import bind_workspace
from http_transport import install_curl_transport
from session_trace import redact_secrets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('agent_id')
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--max-seconds', type=int, default=1800)
    args = parser.parse_args()
    if args.out.exists() or args.out.with_suffix('.events.jsonl').exists():
        parser.error('Use a fresh output path to preserve prior test evidence')
    scenarios = json.loads(args.cases.read_text())
    validate_scenarios(scenarios)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.with_suffix('.cases.json').write_text(json.dumps(scenarios, ensure_ascii=False, indent=2))
    def trace(event, **data):
        row = redact_secrets({'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                              'event': event, **data})
        text = json.dumps(row, ensure_ascii=False)
        with args.out.with_suffix('.events.jsonl').open('a') as f:
            f.write(text + '\n')
        print(text, flush=True)
    load_env()
    import freya
    install_curl_transport(freya)
    bind_workspace(freya, trace)
    trace('extra_test_start', agent_id=args.agent_id, scenarios=len(scenarios),
          criteria='Additional document-derived checks; not an official hackathon score')
    summary = run_examples(freya, args.agent_id, scenarios, trace, max_seconds=args.max_seconds)
    args.out.write_text(json.dumps(redact_secrets(summary), ensure_ascii=False, indent=2))
    print(json.dumps({k:v for k,v in summary.items() if k != 'rows'}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
