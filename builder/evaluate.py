"""Run document-derived conversations; these are internal checks, not event scores."""
import json
import signal
import time


class EvaluationTimeout(TimeoutError):
    pass


def validate_scenarios(scenarios):
    if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= 12:
        raise ValueError('Expected 1..12 document-derived scenarios')
    names = set()
    for scenario in scenarios:
        for key in ('name', 'source', 'prompt', 'success_criteria'):
            if not isinstance(scenario.get(key), str) or not scenario[key].strip():
                raise ValueError('Scenario is missing ' + key)
        if scenario['name'] in names: raise ValueError('Duplicate scenario name')
        names.add(scenario['name'])
        if not isinstance(scenario.get('variables'), dict):
            raise ValueError('Scenario variables must come from a documented synthetic customer')


def evaluation_seconds(scenarios, max_call_seconds=300):
    """Reserve complete call waves plus control/analysis time before starting."""
    fixtures = [json.dumps(s['variables'], sort_keys=True) for s in scenarios]
    concurrency = 1 if len(set(fixtures)) != len(fixtures) else min(3, len(scenarios))
    return ((len(scenarios) + concurrency - 1) // concurrency) * max_call_seconds + 180


def summarize_runs(scenarios, persona_ids, runs, calls):
    rows = []
    for scenario, persona_id in zip(scenarios, persona_ids):
        matches = [r for r in runs if r.get('personaId') == persona_id]
        if len(matches) != 1:
            rows.append({'name': scenario['name'], 'outcome': 'inconclusive',
                         'reason': 'Expected exactly one call; found ' + str(len(matches))})
            continue
        run = matches[0]
        call_id = run.get('callId')
        call = calls.get(call_id, {})
        messages = [{k: m[k] for k in ('role', 'message', 'nodeId', 'secondsFromStart') if k in m}
                    for m in call.get('messages', [])]
        spoke = any(m.get('role') == 'assistant' and m.get('message') for m in messages)
        outcome = run.get('outcome')
        reason = run.get('reason')
        if not spoke:
            outcome, reason = 'inconclusive', 'No assistant speech: inspect startup/service availability'
        elif outcome not in ('pass', 'fail'):
            outcome, reason = 'inconclusive', reason or 'No completed judge verdict'
        rows.append({'name': scenario['name'], 'outcome': outcome, 'reason': reason,
                     'call_id': call_id, 'agent_version': run.get('agentVersionNumber'),
                     'messages': messages})
    return {'total': len(rows), 'passed': sum(r['outcome'] == 'pass' for r in rows),
            'failed': sum(r['outcome'] == 'fail' for r in rows),
            'conclusive': all(r['outcome'] in ('pass', 'fail') for r in rows), 'rows': rows}


def run_examples(freya, agent_id, scenarios, trace, *, persona_ids=None, max_call_seconds=300,
                 max_seconds=None):
    """Bound remote evaluation, including blocked HTTP calls, leaving time to export."""
    validate_scenarios(scenarios)
    budget = evaluation_seconds(scenarios, max_call_seconds) if max_seconds is None else max_seconds
    if budget <= 0: raise ValueError('Evaluation needs a positive time budget')
    started = time.monotonic()
    previous = signal.getitimer(signal.ITIMER_REAL)
    handler = signal.getsignal(signal.SIGALRM)
    # Never replace an earlier enclosing deadline with a later local deadline.
    owns_alarm = not previous[0] or budget < previous[0]
    progress = {'persona_ids': persona_ids, 'simulation_id': None}
    def expired(sig, frame):
        raise EvaluationTimeout('Document example evaluation time limit reached')
    if owns_alarm:
        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, budget)
    try:
        return _run_examples(freya, agent_id, scenarios, trace, progress,
                             persona_ids=persona_ids, max_call_seconds=max_call_seconds,
                             expires=started + budget)
    except EvaluationTimeout as error:
        result = {'passed': None, 'failed': 0, 'total': len(scenarios), 'conclusive': False,
                  'rows': [], 'status': 'evaluation_timeout', 'reason': str(error), **progress}
        trace('example_evaluation_inconclusive', **result,
              action='Retain this simulation ID; do not start another simulation while its status is unresolved')
        return result
    except RuntimeError as error:
        if 'concurrent simulations' not in str(error).lower(): raise
        result = {'passed': None, 'failed': 0, 'total': len(scenarios), 'conclusive': False,
                  'rows': [], 'status': 'workspace_busy', 'reason': str(error), **progress}
        trace('example_evaluation_inconclusive', **result,
              action='Leave the existing workspace simulation unchanged; do not retry creation')
        return result
    finally:
        if owns_alarm:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, handler)
            if previous[0]:
                signal.setitimer(signal.ITIMER_REAL, max(0.000001, previous[0] - (time.monotonic()-started)), previous[1])


def _run_examples(freya, agent_id, scenarios, trace, progress, *, persona_ids, max_call_seconds, expires):
    """One simulation, fixed event phone models, original criteria reusable for repair."""
    validate_scenarios(scenarios)
    if persona_ids is None:
        created = freya.create_personas([{
            'name': s['name'], 'prompt': s['prompt'], 'successCriteria': s['success_criteria'],
            'tags': ['builder-document-example']} for s in scenarios])
        items = created.get('personas', created.get('items', []))
        if len(items) != len(scenarios): raise RuntimeError('Persona creation returned the wrong count')
        persona_ids = [p['id'] for p in items]
        trace('example_personas_created', persona_ids=persona_ids,
              scenarios=[{'name': s['name'], 'source': s['source']} for s in scenarios])
    if len(persona_ids) != len(scenarios) or len(set(persona_ids)) != len(persona_ids):
        raise ValueError('Each scenario needs a distinct persona')
    progress['persona_ids'] = persona_ids
    variables = {pid: s['variables'] for pid, s in zip(persona_ids, scenarios)}
    # Identical fixtures may share state in the bank mock; never race those calls.
    fixtures = [json.dumps(s['variables'], sort_keys=True) for s in scenarios]
    concurrency = 1 if len(set(fixtures)) != len(fixtures) else min(3, len(scenarios))
    body = {'agentId': agent_id, 'name': 'Builder document examples', 'mode': 'chat',
            'selectedPersonaIds': persona_ids, 'customerVariablesMap': variables,
            'maxConcurrentCalls': concurrency, 'runsPerPersona': 1,
            'maxCallDurationSeconds': max_call_seconds,
            'assistantLlmOverride': freya.AGENT_LLM, 'routingLlmOverride': freya.AGENT_LLM,
            'extractionLlmOverride': freya.AGENT_LLM,
            'personaLlmOverride': freya.SIM_LLM, 'analysisLlmOverride': freya.SIM_LLM}
    # Never retry this POST blindly: a timed-out creation may already have run.
    created = freya.api('POST', '/api/v2/simulations', body)
    sim_id = (created.get('simulation') or created)['id']
    progress['simulation_id'] = sim_id
    trace('example_simulation_created', simulation_id=sim_id, persona_ids=persona_ids,
          concurrency=concurrency, criteria='Document-derived internal checks; not the hidden event score')
    while True:
        if time.monotonic() >= expires:
            raise EvaluationTimeout('Document example evaluation time limit reached')
        time.sleep(min(10, max(0, expires-time.monotonic())))
        result = freya.api('GET', '/api/v2/simulations/' + sim_id)
        status = (result.get('simulation') or result).get('status')
        if status in ('completed', 'failed', 'paused'): break
    result = freya.api('GET', '/api/v2/simulations/' + sim_id + '/iterations')
    iterations = result.get('iterations', result.get('items', [])) if isinstance(result, dict) else result
    if not iterations: raise RuntimeError('Simulation has no iteration')
    it_id = iterations[0]['id']
    detail = freya.get_iteration(sim_id, it_id)
    runs = detail.get('runs', [])
    calls = {}
    for run in runs:
        if run.get('callId'): calls[run['callId']] = freya.get_call(run['callId'])
    summary = summarize_runs(scenarios, persona_ids, runs, calls)
    summary.update(simulation_id=sim_id, iteration_id=it_id, status=status, persona_ids=persona_ids)
    trace('example_evaluation_end', **{k: v for k, v in summary.items() if k != 'rows'})
    return summary
