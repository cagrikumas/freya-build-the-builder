#!/usr/bin/env python3
"""One-command brief -> generated, verified and exported Freya phone agent."""
import argparse
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
KIT = ROOT / 'build-the-builder-v3' / 'build-the-builder'
sys.path.insert(0, str(KIT))
from model import call, recover_answer
from compile_resume import import_failed_compile
from session_trace import append_record, redact_secrets
from validate import validate, check_examples
from assemble import assemble
from freya_client import bind_workspace, availability_check
from patches import apply_patches, apply_with_path_repair
from http_transport import install_curl_transport
from documents import read_folder
from smoke import run_smoke
from evaluate import run_examples, validate_scenarios, evaluation_seconds, compact_feedback


def preserve_tests(original, candidate):
    """A repair may add checks, but cannot redefine the evidence it failed."""
    checks = original.get('checks', [])
    new_checks = candidate.get('checks', [])
    if (not isinstance(checks, list) or not isinstance(new_checks, list)
            or new_checks[:len(checks)] != checks
            or any(candidate.get(k) != original.get(k) for k in ('smoke', 'scenarios'))):
        raise ValueError('Automatic repair must preserve the original tests')
    return candidate


def validate_and_check(workflow, artifact, api):
    errors = validate(workflow, api)
    # Never execute model-generated code that failed the static safety checks.
    if not errors:
        errors += check_examples(workflow, artifact.get('checks', []))
    return errors


def pre_audit_static_errors(artifact, api=None, mock_url=None):
    """Give the auditor draft diagnostics without executing generated code."""
    try:
        if not isinstance(artifact, dict):
            raise ValueError('Compilation artifact must be an object')
        draft_api = copy.deepcopy(api if api is not None else artifact['openapi'])
        if not isinstance(draft_api, dict) or 'openapi' not in draft_api:
            raise ValueError('No usable OpenAPI specification')
        if api is None and not draft_api.get('paths'):
            raise ValueError('No usable OpenAPI was derived from the service contract')
        if mock_url is not None:
            draft_api['servers'] = [{'url': mock_url}]
        return validate(assemble(artifact, draft_api), draft_api)
    except (KeyError, ValueError, TypeError, AttributeError, IndexError,
            RecursionError, OverflowError, SyntaxError) as error:
        return ['Malformed draft artifact: ' + str(error)]


def artifact_manifest(run_dir):
    return {str(p.relative_to(run_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(run_dir.rglob('*')) if p.is_file() and p != run_dir / 'trace.jsonl'}


def compact_practice_feedback(failures, workflow):
    """Adapt public scorer evidence to the shared bounded repair format."""
    rows = [{'name': failure['case'], 'outcome': 'fail',
             'reason': {'failed': failure.get('failed'), 'tools': failure.get('tools')},
             'call_id': failure.get('call_id'), 'messages': failure.get('messages', [])}
            for failure in failures]
    return compact_feedback({'total': len(rows), 'passed': 0, 'failed': len(rows),
                             'conclusive': True, 'rows': rows}, workflow, max_rows=16)


def load_env():
    env = ROOT / 'env.sh'
    if env.exists():
        import shlex
        for line in env.read_text().splitlines():
            words = shlex.split(line, comments=True)
            if words and words[0] == 'export': words = words[1:]
            for word in words:
                if '=' in word:
                    key, value = word.split('=', 1)
                    os.environ.setdefault(key, value)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('inputs', nargs='+', help='A case folder and mock URL, or practice briefs and OpenAPI JSON')
    ap.add_argument('--slot')
    ap.add_argument('--resume-compile', type=Path, help='Recover only malformed JSON from an unchanged, fully traced failed compiler call')
    ap.add_argument('--offline', action='store_true', help='Compile and verify locally, without Freya calls')
    ap.add_argument('--practice', choices=['A', 'B', 'all'])
    ap.add_argument('--style', choices=['pieces', 'corrects', 'talkative', 'asks_back', 'in_words'])
    ap.add_argument('--max-seconds', type=int, default=3600, help='Local build deadline, default 3600 seconds')
    args = ap.parse_args()
    folder_mode = len(args.inputs) == 2 and Path(args.inputs[0]).is_dir()
    mock_url = args.inputs[1].rstrip('/') if folder_mode else None
    if folder_mode:
        parsed = urlsplit(mock_url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            ap.error('The deployed mock must have a plain HTTPS URL without credentials, query or fragment')
        folder = Path(args.inputs[0]).resolve()
        inputs = sorted(p for p in folder.rglob('*') if p.is_file() and not any(v.startswith('.') for v in p.relative_to(folder).parts))
        api = None
        slot = args.slot or 'final'
        if args.practice: ap.error('The public scorer is only for the practice briefs')
    else:
        inputs = [Path(p).resolve() for p in args.inputs]
        api_paths = [p for p in inputs if p.suffix.lower() == '.json']
        briefs = [p for p in inputs if p.suffix.lower() != '.json']
        if len(api_paths) != 1 or not briefs: ap.error('Supply a case folder and mock URL, or practice briefs and one API JSON')
        api = json.loads(api_paths[0].read_text())
        if 'openapi' not in api: ap.error('The JSON input must be an OpenAPI specification')
        slot = args.slot or briefs[-1].stem
    if not 60 <= args.max_seconds <= 10800: ap.error('max-seconds must be 60..10800')
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', slot): ap.error('Invalid slot name')
    load_env()
    import freya
    started = time.monotonic()
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    run_dir = ROOT / 'traces' / f'{stamp}-{slot}'
    run_dir.mkdir(parents=True)
    trace_path = run_dir / 'trace.jsonl'
    def redact(value):
        return json.dumps(redact_secrets(value), ensure_ascii=False, default=str)
    def trace(event, **data):
        row = {'at': dt.datetime.now(dt.timezone.utc).isoformat(), 'event': event, **data}
        line = redact(row)
        with trace_path.open('a') as out: out.write(line + '\n')
        # Final build_end contains the artifact hash of the already frozen log.
        if event != 'build_end':
            append_record(run_dir / 'full-session.jsonl', json.loads(line))
        print(line, flush=True)
    def remaining(): return args.max_seconds - (time.monotonic() - started)
    def deadline(sig, frame): raise TimeoutError('Builder deadline reached')
    signal.signal(signal.SIGALRM, deadline); signal.alarm(args.max_seconds)
    trace('build_start', slot=slot, offline=args.offline, max_seconds=args.max_seconds, folder_mode=folder_mode, mock_url=mock_url,
          builder_files={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sorted(list((ROOT / 'builder').glob('*')) + [KIT / 'freya.py']
                                         + [KIT / 'docs' / name for name in ('workflow-format.md', 'tools-and-code.md')])
                         if p.is_file()},
          inputs=[{'path': str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs])
    final = None
    try:
        if not args.offline:
            install_curl_transport(freya)
            bind_workspace(freya, trace)
        images = []
        if folder_mode:
            documents, images, manifest = read_folder(folder, run_dir)
            trace('documents_read', files=manifest, images=len(images))
            (run_dir / 'documents.txt').write_text(documents)
            # Prefer the mock's published contract when supplied. Otherwise the
            # compiler derives it from the service documents, never from memory.
            for path in inputs:
                if path.suffix.lower() == '.json':
                    value = json.loads(path.read_text())
                    if isinstance(value, dict) and 'openapi' in value:
                        if api is not None: raise ValueError('Multiple OpenAPI inputs are ambiguous')
                        api = value
            if api is None and not args.offline:
                from http_transport import request
                try:
                    value = request('GET', mock_url + '/openapi.json', {'User-Agent': 'Freya-hackathon-builder'})
                    if isinstance(value, dict) and 'openapi' in value:
                        api = value
                        trace('mock_contract_read', url=mock_url + '/openapi.json')
                except (RuntimeError, ValueError) as e:
                    trace('mock_contract_unavailable', error=str(e), action='Infer schema from the supplied service contract')
            if api is not None:
                api['servers'] = [{'url': mock_url}]
                (run_dir / 'tool-api.json').write_text(json.dumps(api, indent=2))
                documents += '\n\n### DEPLOYED MOCK OPENAPI\n' + json.dumps(api)
            documents += '\n\n### DEPLOYMENT\nAll phone tools must use this mock base URL: ' + mock_url
        else:
            documents = '\n\n'.join(f'### INPUT {p.name}\n{p.read_text()}' for p in inputs)
        docs = '\n\n'.join((KIT / 'docs' / p).read_text() for p in ['workflow-format.md', 'tools-and-code.md'])
        compiler_instructions = (ROOT / 'builder' / 'compile_prompt.md').read_text()
        compiler_instructions += '\nINPUT MODE: ' + ('folder; derive scenarios from supplied example conversations and synthetic customer records.' if folder_mode else 'individual briefs; public practice is evaluated by the official scorer.') + '\n'
        derive_api = api is None
        if derive_api:
            compiler_instructions += '\nThe case supplies its service contract in documents rather than OpenAPI. Add an openapi field to your output containing a complete OpenAPI 3 specification derived strictly from that service contract. Preserve endpoint paths, methods, body fields, types, enumerations and response shapes. Set servers to the supplied deployed mock URL. Your tool_config and workflow must use this derived schema. Do not import the practice bank tools or policy.\n'
        prompt = compiler_instructions + '\n\n# PLATFORM REFERENCE\n' + docs + '\n\n# BANK INPUT DOCUMENTS\n' + documents
        if args.resume_compile:
            input_hashes = [{'path': str(p.relative_to(ROOT)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs]
            raw = import_failed_compile(args.resume_compile, run_dir, prompt, input_hashes, trace)
            artifact = recover_answer(raw, 'Recover malformed compiler JSON without changing its policy', trace, run_dir,
                                      timeout=min(600, int(remaining()-20)), original_call_id='model-01')
        else:
            artifact = call(prompt, 'Compile all supplied rules and API schema into workflow and local checks', trace, run_dir, timeout=min(1500, int(remaining()-20)), images=images)
        pre_audit_errors = pre_audit_static_errors(artifact, api, mock_url)
        trace('pre_audit_static_validation', errors=pre_audit_errors, code_executed=False)
        audit_instructions = (ROOT / 'builder' / 'audit_prompt.md').read_text()
        audit = call(audit_instructions + '\n\n# COMPILER CONTRACT\n' + compiler_instructions + '\n\n# PLATFORM REFERENCE\n' + docs + '\n\n# BANK INPUTS\n' + documents + '\n\n# CANDIDATE\n' + json.dumps(artifact)
                     + '\n\n# PRE-AUDIT STATIC VALIDATION\n' + json.dumps(pre_audit_errors)
                     + '\nThese diagnostics only assemble and statically validate the draft; generated code has not run. Correct their causes. Post-audit validation remains authoritative.',
                     'Independently audit policy coverage, deterministic code and failure paths', trace, run_dir, timeout=min(1200, int(remaining()-30)), images=images)
        trace('policy_audit', approved=audit.get('approved'), issues=audit.get('issues', []))
        (run_dir / 'audit.json').write_text(json.dumps(audit, indent=2))
        if not audit.get('approved'):
            def repair_audit_path(original, edits, error):
                trace('audit_patch_error', index=error.index, error=str(error))
                if remaining() < 180:
                    raise error
                repair_prompt = ('The audit contains an invalid JSON Pointer. Return only {"path":"/correct/pointer"} for the failed edit. '
                    'Preserve its operation, value and intended audit correction. Inspect the ACTUAL candidate and the preceding edits; '
                    'array indexes are zero-based. Never redirect a correction to an unrelated field just to make it apply. '
                    'If the intended correction has no unambiguous target, return {"error":"reason"}. '
                    'Do not return an artifact or other changes.\n# CANDIDATE\n' + json.dumps(original)
                    + '\n# AUDIT ISSUES\n' + json.dumps(audit.get('issues', []))
                    + '\n# ORDERED EDITS\n' + json.dumps(edits)
                    + '\n# FAILED EDIT\n' + json.dumps({'index': error.index, 'error': str(error)}))
                correction = call(repair_prompt, 'Repair an invalid audit JSON Pointer without changing its operation or value',
                                  trace, run_dir, timeout=min(240, int(remaining()-30)))
                trace('audit_patch_pointer_correction', index=error.index, correction=correction)
                return correction
            artifact = audit['artifact'] if 'artifact' in audit else apply_with_path_repair(artifact, audit['patches'], repair_audit_path)
        for attempt in range(4):
            path = run_dir / f'candidate-{attempt}.json'
            path.write_text(json.dumps(artifact, indent=2))
            try:
                if derive_api:
                    api = artifact['openapi']
                    if not isinstance(api, dict) or 'openapi' not in api or not api.get('paths'):
                        raise ValueError('No usable OpenAPI was derived from the service contract')
                    api['servers'] = [{'url': mock_url}]
                    (run_dir / 'tool-api.json').write_text(json.dumps(api, indent=2))
                workflow = assemble(artifact, api)
                errors = validate_and_check(workflow, artifact, api)
                if folder_mode and artifact.get('scenarios'):
                    validate_scenarios(artifact['scenarios'])
            except (KeyError, ValueError, TypeError, AttributeError) as e:
                errors = ['Malformed compilation artifact: ' + str(e)]
            trace('local_validation', attempt=attempt, checks=len(artifact.get('checks', [])), errors=errors)
            if not errors and not args.offline:
                try:
                    freya.validate_workflow(slot, workflow)
                    trace('platform_validation', success=True)
                except Exception as e:
                    errors.append(str(e))
                    trace('platform_validation', success=False, error=str(e))
            if not errors: break
            if attempt == 3 or remaining() < 180: raise RuntimeError('Validation failed: ' + '; '.join(errors))
            candidate = call(prompt + '\n\n# REPAIR REQUIRED\nPrevious artifact:\n' + json.dumps(artifact) + '\nFailures:\n' + json.dumps(errors) + '\nReturn the full corrected artifact. Preserve smoke, scenarios and all existing checks exactly; you may append checks. Fix causes, never weaken checks to conceal policy errors.', 'Repair locally or platform-detected compilation defects', trace, run_dir, timeout=min(900 if folder_mode else 600, int(remaining()-20)), images=images)
            artifact = preserve_tests(artifact, candidate)
        (run_dir / 'workflow.json').write_text(json.dumps(workflow, indent=2))
        if args.offline:
            final = {'workflow': str(run_dir / 'workflow.json'), 'trace': str(trace_path)}
            return
        ids = freya.save_workflow(slot, workflow, state_file=str(ROOT / '.freya-agents.json'))
        # Existing slots are already normalized and published by save_workflow.
        if 'version' not in ids:
            ids['version'] = freya.update_workflow(ids['workflow_id'], workflow)
        trace('published', **ids, nodes=len(workflow['nodes']), tools=sum(len(n.get('tools', [])) + len(n.get('pre_actions', [])) for n in workflow['nodes'].values()))
        if folder_mode:
            live_available = True
            if artifact.get('smoke'):
                trace('smoke_test_start', name=artifact['smoke'].get('name', 'Opening from the case documents'))
                smoke_result = availability_check(lambda: run_smoke(freya, ids['workflow_id'], artifact['smoke']), trace, 'opening')
                trace('smoke_test_end', **smoke_result)
                live_available = smoke_result['passed'] is not None
                if smoke_result['passed'] is False:
                    if remaining() < 600: raise RuntimeError('Published workflow failed its opening smoke check')
                    repaired = call(prompt + '\n\n# CANDIDATE\n' + json.dumps(artifact) + '\n\n# OPENING SMOKE FAILURE\n' + json.dumps(smoke_result) + '\nReturn JSON with issues and patches (JSON Patch into the artifact). Repair the runtime or policy cause; do not remove or weaken expectations from the source documents.',
                                    'Repair an observed opening/runtime failure', trace, run_dir, timeout=min(600, int(remaining()-420)), images=images)
                    candidate = preserve_tests(artifact, apply_patches(artifact, repaired['patches']))
                    (run_dir/'smoke-repair.json').write_text(json.dumps(repaired, indent=2))
                    repaired_workflow = assemble(candidate, api)
                    errors = validate_and_check(repaired_workflow, candidate, api)
                    if errors: raise RuntimeError('Smoke repair validation failed: ' + '; '.join(errors))
                    freya.validate_workflow(slot, repaired_workflow)
                    selected = False
                    try:
                        ids['version'] = freya.update_workflow(ids['workflow_id'], repaired_workflow)
                        trace('smoke_repair_published', **ids)
                        smoke_result = availability_check(lambda: run_smoke(freya, ids['workflow_id'], artifact['smoke']), trace, 'opening after repair')
                        trace('smoke_test_end', **smoke_result)
                        live_available = smoke_result['passed'] is not None
                        if smoke_result['passed'] is False: raise RuntimeError('Opening smoke check failed after automatic repair')
                        if smoke_result['passed'] is True:
                            workflow, artifact = repaired_workflow, candidate
                            selected = True
                    finally:
                        if not selected:
                            ids['version'] = freya.update_workflow(ids['workflow_id'], workflow)
                            trace('original_restored', reason='Opening repair did not complete with a measured pass', **ids)
            else:
                trace('smoke_test_skipped', reason='No usable synthetic test variables supplied by the documents')
            if artifact.get('scenarios'):
                # Preserve the original test suite across repairs. These verdicts
                # are internal feedback, never presented as the hidden score.
                scenarios = artifact['scenarios']
                evaluation_budget = evaluation_seconds(scenarios)
                if not live_available:
                    trace('example_evaluation_skipped', reason='Opening request exposed a conversation-service outage')
                elif remaining() < evaluation_budget + 300:
                    trace('example_evaluation_skipped', reason='Insufficient remaining build time',
                          required_seconds=evaluation_budget + 300, remaining_seconds=int(remaining()))
                else:
                    evaluated = availability_check(lambda: run_examples(freya, ids['agent_id'], scenarios, trace,
                                                                         max_seconds=min(evaluation_budget, remaining()-300)), trace, 'document examples')
                    (run_dir / 'examples.json').write_text(redact(evaluated))
                    if evaluated['failed'] and evaluated['conclusive'] and remaining() >= evaluation_budget + 900:
                        feedback = compact_feedback({**evaluated, 'rows': [r for r in evaluated['rows'] if r['outcome'] == 'fail']}, workflow=workflow)
                        (run_dir / 'example-repair-feedback.json').write_text(redact(feedback))
                        trace('example_repair_feedback', full_evidence='examples.json',
                              model_feedback='example-repair-feedback.json',
                              characters=len(redact(feedback)))
                        repaired = call(prompt + '\n\n# CANDIDATE\n' + json.dumps(artifact)
                                        + '\n\n# OBSERVED EXAMPLE CONVERSATION FAILURES\n' + redact(feedback)
                                        + '\nReturn JSON with issues and patches (JSON Patch into the artifact). Fix general runtime/policy causes from the documents. Never hardcode the example customer or coach tests. Preserve scenarios, smoke and existing checks exactly; you may append additional local checks.',
                                        'Repair policy/runtime defects in document-derived conversations', trace, run_dir,
                                        timeout=min(600, int(remaining()-evaluation_budget-300)), images=images)
                        candidate = preserve_tests(artifact, apply_patches(artifact, repaired['patches']))
                        repaired_workflow = assemble(candidate, api)
                        errors = validate_and_check(repaired_workflow, candidate, api)
                        trace('example_repair_validation', errors=errors)
                        (run_dir / 'example-repair.json').write_text(redact(repaired))
                        if not errors and remaining() >= evaluation_budget + 300:
                            freya.validate_workflow(slot, repaired_workflow)
                            selected = False
                            try:
                                ids['version'] = freya.update_workflow(ids['workflow_id'], repaired_workflow)
                                trace('example_repair_published', **ids)
                                rescored = availability_check(lambda: run_examples(freya, ids['agent_id'], scenarios, trace,
                                                                                   persona_ids=evaluated['persona_ids'],
                                                                                   max_seconds=min(evaluation_budget, remaining()-300)), trace, 'document examples after repair')
                                (run_dir / 'examples-repaired.json').write_text(redact(rescored))
                                if rescored['conclusive'] and rescored['passed'] >= evaluated['passed']:
                                    workflow, artifact = repaired_workflow, candidate
                                    selected = True
                                    trace('example_repair_selected', passed=rescored['passed'], total=rescored['total'])
                            finally:
                                if not selected:
                                    ids['version'] = freya.update_workflow(ids['workflow_id'], workflow)
                                    trace('original_restored', reason='Example repair did not complete with a conclusive improvement', **ids)
        if args.practice:
            out_path = run_dir / 'practice.json'
            cmd = [sys.executable, str(ROOT / 'builder' / 'practice.py'), ids['agent_id'], '--out', str(out_path)]
            if args.practice != 'all': cmd += ['--brief', args.practice]
            if args.style: cmd += ['--style', args.style]
            if remaining() < 60: raise TimeoutError('Insufficient time for test')
            trace('test_start', command=cmd)
            result = subprocess.run(cmd, cwd=KIT, text=True, capture_output=True, timeout=max(1, int(remaining()-15)))
            (run_dir / 'practice.log').write_text(result.stdout + result.stderr)
            scored = json.loads(out_path.read_text()) if out_path.exists() else {}
            trace('test_end', returncode=result.returncode, passed=scored.get('passed'), total=scored.get('total'), output=result.stdout[-14000:], error=result.stderr[-2000:])
            if result.returncode: raise RuntimeError('Practice test failed to execute')
            # A repair remains part of THIS unattended build and shares its deadline.
            if scored.get('passed', 0) < scored.get('total', 0) and remaining() >= 600:
                failures = []
                for row in scored.get('rows', []):
                    if row.get('pass'): continue
                    detail = {'case': row['id'], 'failed': row.get('failed'),
                              'tools': row.get('tools'), 'call_id': row.get('call_id')}
                    if row.get('call_id'):
                        call_data = freya.get_call(row['call_id'])
                        detail['transcript'] = call_data.get('transcript')
                        detail['messages'] = [{k: m[k] for k in ('role', 'message', 'nodeId') if k in m} for m in call_data.get('messages', [])]
                    failures.append(detail)
                (run_dir / 'practice-repair-evidence.json').write_text(redact(failures))
                feedback = compact_practice_feedback(failures, workflow)
                (run_dir / 'practice-repair-feedback.json').write_text(redact(feedback))
                trace('practice_repair_feedback', full_evidence='practice-repair-evidence.json',
                      model_feedback='practice-repair-feedback.json', characters=len(redact(feedback)))
                trace('repair_start', failed_cases=[f['case'] for f in failures])
                repair = call(prompt + '\n\n# CANDIDATE\n' + json.dumps(artifact) + '\n\n# OBSERVED PRACTICE FAILURES\n' + redact(feedback) + '\nFix general policy/runtime causes. Do not hardcode customer facts or expected case outputs. Override the compilation output format: return JSON {"issues": [...], "patches": [...]} with JSON Patch add/replace/remove operations into the candidate. Replace complete code strings when needed and append new checks with path /checks/-. Do not re-emit the entire artifact.',
                                'Repair policy or runtime defects revealed by practice conversations', trace, run_dir, timeout=min(420, int(remaining()-150)))
                (run_dir / 'repair-patches.json').write_text(json.dumps(repair, indent=2))
                repaired = preserve_tests(artifact, apply_patches(artifact, repair['patches']))
                repaired_workflow = assemble(repaired, api)
                repair_errors = validate_and_check(repaired_workflow, repaired, api)
                trace('repair_validation', errors=repair_errors)
                if not repair_errors and remaining() > 360:
                    selected = False
                    publication_attempted = False
                    try:
                        freya.validate_workflow(slot, repaired_workflow)
                        publication_attempted = True
                        ids['version'] = freya.update_workflow(ids['workflow_id'], repaired_workflow)
                        trace('repair_published', **ids)
                        (run_dir / 'repair.json').write_text(json.dumps(repaired, indent=2))
                        repaired_path = run_dir / 'practice-repaired.json'
                        repair_cmd = cmd.copy(); repair_cmd[repair_cmd.index('--out') + 1] = str(repaired_path)
                        trace('test_start', command=repair_cmd)
                        rr = subprocess.run(repair_cmd, cwd=KIT, text=True, capture_output=True, timeout=max(1, int(remaining()-300)))
                        (run_dir / 'practice-repaired.log').write_text(rr.stdout + rr.stderr)
                        rescored = json.loads(repaired_path.read_text()) if repaired_path.exists() else {}
                        trace('test_end', returncode=rr.returncode, passed=rescored.get('passed'), total=rescored.get('total'), output=rr.stdout[-14000:], error=rr.stderr[-2000:])
                        if rr.returncode == 0 and rescored.get('passed', -1) >= scored.get('passed', 0):
                            workflow = repaired_workflow; artifact = repaired; scored = rescored
                            selected = True
                            trace('repair_selected', passed=scored.get('passed'), total=scored.get('total'))
                    except (subprocess.TimeoutExpired, RuntimeError) as e:
                        if remaining() <= 10: raise
                        trace('practice_repair_inconclusive', error=str(e))
                    finally:
                        if publication_attempted and not selected:
                            ids['version'] = freya.update_workflow(ids['workflow_id'], workflow)
                            trace('original_restored', reason='Practice repair did not complete with an improved measured score', **ids)
        (run_dir / 'workflow.json').write_text(json.dumps(workflow, indent=2))
        export_path = ROOT / 'submission' / f'{slot}.workflow.json'
        export_path.parent.mkdir(exist_ok=True)
        freya.export_workflow(ids['workflow_id'], str(export_path))
        final = {**ids, 'export': str(export_path.relative_to(ROOT)), 'trace': str(trace_path.relative_to(ROOT)), 'session_trace': str((run_dir / 'full-session.jsonl').relative_to(ROOT)), 'sha256': hashlib.sha256(export_path.read_bytes()).hexdigest()}
        (run_dir / 'result.json').write_text(json.dumps(final, indent=2))
        trace('exported', **final)
    except BaseException as e:
        trace('build_error', error=f'{type(e).__name__}: {e}')
        raise
    finally:
        signal.alarm(0)
        seconds = round(time.monotonic()-started, 2)
        trace('run_completed', seconds=seconds, completed=final is not None, result=final)
        trace('build_end', seconds=seconds, completed=final is not None,
              result=final, artifacts=artifact_manifest(run_dir))


if __name__ == '__main__':
    main()
