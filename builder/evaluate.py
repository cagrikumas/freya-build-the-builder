"""Run document-derived conversations; these are internal checks, not event scores."""
import json
import math
import re
from itertools import islice
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


FEEDBACK_MAX_CHARS = 96000
FEEDBACK_ROW_CHARS = 18000
FEEDBACK_SYSTEM_CHARS = 512000
FEEDBACK_SCAN_MESSAGES = 2048
_FEEDBACK_OMIT = {'headers', 'request_headers', 'response_headers', 'raw_response',
                  'variable_table', 'authorization', 'cookie', 'set-cookie', 'api_key',
                  'api_token', 'access_token'}


def compact_feedback(summary, workflow=None, *, max_rows=12):
    """Bound model repair evidence; the persisted full summary stays untouched.

    Limits count JSON characters with ASCII escaping (a conservative bound for
    the UTF-8 prompt). Twelve rows match the compiler contract; practice may
    explicitly allow up to sixteen under the same total budget. Facts removed
    by a limit are explicitly reported.
    """
    rows = summary.get('rows') if isinstance(summary, dict) else None
    if isinstance(max_rows, bool) or not isinstance(max_rows, int) or not 1 <= max_rows <= 16:
        raise ValueError('Repair feedback row limit must be between one and sixteen')
    if not isinstance(rows, list) or len(rows) > max_rows:
        limit = 'twelve' if max_rows == 12 else str(max_rows)
        raise ValueError(f'Repair feedback requires a summary with at most {limit} rows')

    def size(value): return len(json.dumps(value))

    def bounded(value, stats, *, depth=0, text_limit=1200, nodes=None):
        nodes = [256] if nodes is None else nodes
        nodes[0] -= 1
        if nodes[0] < 0 or depth > 6:
            stats['truncated_values'] += 1
            return {'_truncated': 'nested value limit'}
        if isinstance(value, str):
            if len(value) > text_limit or size(value) > text_limit:
                stats['truncated_values'] += 1
                low, high = 0, min(len(value), text_limit)
                while low < high:
                    middle = (low+high+1)//2
                    if size(value[:middle]) <= max(0, text_limit-64): low = middle
                    else: high = middle-1
                return value[:low] + f' [TRUNCATED {len(value)-low} characters]'
            return value
        if value is None or isinstance(value, (bool, int)):
            if isinstance(value, int) and value.bit_length() > 1024:
                stats['truncated_values'] += 1
                return {'_truncated': 'oversized integer'}
            return value
        if isinstance(value, float):
            if math.isfinite(value): return value
            stats['truncated_values'] += 1
            return {'_truncated': 'non-finite number'}
        if isinstance(value, dict):
            result = {}
            for index, (key, child) in enumerate(value.items()):
                if not isinstance(key, str):
                    stats['truncated_values'] += 1
                    continue
                if key.casefold() in _FEEDBACK_OMIT:
                    stats['omitted_bulk_fields'] += 1
                    continue
                if len(result) >= 32 or nodes[0] <= 0:
                    stats['truncated_values'] += 1
                    result['_truncated'] = 'object items omitted'
                    break
                if len(key) > 128:
                    stats['truncated_values'] += 1
                    key = key[:128] + f' [TRUNCATED KEY {index}]'
                result[key] = bounded(child, stats, depth=depth+1, text_limit=text_limit, nodes=nodes)
            return result
        if isinstance(value, list):
            result = [bounded(child, stats, depth=depth+1, text_limit=text_limit, nodes=nodes)
                      for child in value[:32]]
            if len(value) > 32:
                stats['truncated_values'] += 1
                result.append({'_truncated': f'{len(value)-32} list items omitted'})
            return result
        stats['truncated_values'] += 1
        return {'_truncated': 'unsupported value type'}

    def references(value):
        found, stack, examined = set(), [value], 0
        while stack and examined < 128:
            current = stack.pop(); examined += 1
            if isinstance(current, dict):
                name = current.get('variable')
                if isinstance(name, str) and len(name) <= 128: found.add(name)
                stack.extend(islice(current.values(), 32))
            elif isinstance(current, list): stack.extend(current[:32])
        return found

    def metadata(value, stats, limit=1200):
        projected = bounded(value, stats, text_limit=limit)
        if size(projected) > limit:
            stats['truncated_values'] += 1
            return {'_truncated': 'large metadata value'}
        return projected

    def template_references(node):
        if not isinstance(node, dict): return set()
        templates = [node.get(key) for key in ('task_message', 'system_prompt', 'role_message')]
        entry = node.get('on_enter')
        if isinstance(entry, dict): templates += [entry.get('text'), entry.get('prompt')]
        found = set()
        for text in templates:
            if not isinstance(text, str): continue
            for match in re.finditer(r'\{\{\s*([^{}]+?)\s*\}\}', text[:FEEDBACK_SYSTEM_CHARS]):
                name = match.group(1).strip()
                if name and len(name) <= 128 and name.casefold() not in _FEEDBACK_OMIT:
                    found.add(name)
                if len(found) >= 32: break
        return found

    shared_prompt_refs = template_references(workflow)
    prompt_ref_cache = {}
    def node_references(name):
        if not isinstance(name, str) or len(name) > 128 or not isinstance(workflow, dict): return set()
        if name not in prompt_ref_cache:
            refs = set()
            for collection in ('nodes', 'global_nodes'):
                nodes = workflow.get(collection, {})
                node = nodes.get(name) if isinstance(nodes, dict) else None
                if node is None:
                    candidates = nodes.values() if isinstance(nodes, dict) else nodes if isinstance(nodes, list) else []
                    node = next((candidate for candidate in islice(candidates, 256)
                                 if isinstance(candidate, dict) and name in (candidate.get('name'), candidate.get('id'))), None)
                refs.update(template_references(node))
            prompt_ref_cache[name] = refs
        return prompt_ref_cache[name]

    def table_value(table, name):
        value = table[name]
        return value['value'] if isinstance(value, dict) and 'value' in value else value

    overall_stats = {'truncated_values': 0, 'omitted_bulk_fields': 0}
    result = {key: metadata(summary[key], overall_stats) for key in
              ('total', 'passed', 'failed', 'conclusive', 'simulation_id', 'iteration_id', 'status', 'reason')
              if key in summary}
    result['rows'] = []
    result['feedback_limits'] = {'total_json_chars': FEEDBACK_MAX_CHARS,
                               'row_json_chars': FEEDBACK_ROW_CHARS,
                               'string_chars': 1200, 'utterance_chars': 2000,
                               'nested_depth': 6, 'container_items': 32,
                               'prompt_variable_json_chars_per_event': 3200,
                               'messages_scanned_per_row': FEEDBACK_SCAN_MESSAGES}
    # Reserve space for metadata and every scenario before allocating messages.
    row_budget = min(FEEDBACK_ROW_CHARS, (FEEDBACK_MAX_CHARS-size(result)-1024)//max(1, len(rows)))
    for original in rows:
        stats = {'truncated_values': 0, 'omitted_bulk_fields': 0, 'unparsed_system_messages': 0}
        if not isinstance(original, dict):
            result['rows'].append({'name': None, 'outcome': None, 'reason': 'Malformed scenario row',
                                   'feedback': {'malformed_row': True}})
            continue
        row = {key: metadata(original.get(key), stats, limit=500 if key == 'name' else 1200)
               for key in ('name', 'outcome', 'reason')}
        for key in ('call_id', 'agent_version'):
            if key in original: row[key] = metadata(original[key], stats, limit=256)
        source_messages = original.get('messages', [])
        if not isinstance(source_messages, list):
            source_messages = []
            stats['unparsed_system_messages'] += 1
        candidates, extracted, current_node = [], set(), None
        for index, message in enumerate(source_messages[:FEEDBACK_SCAN_MESSAGES]):
            if not isinstance(message, dict):
                stats['unparsed_system_messages'] += 1
                continue
            role = message.get('role')
            item = {'index': index, 'role': role if role in ('user', 'assistant', 'system') else 'unknown'}
            for key in ('nodeId', 'secondsFromStart'):
                if key in message: item[key] = bounded(message[key], stats, text_limit=256)
            if isinstance(message.get('nodeId'), str): current_node = message['nodeId']
            text = message.get('message')
            priority = 0
            if role in ('user', 'assistant') and isinstance(text, str):
                item['message'] = bounded(text, stats, text_limit=2000)
                priority = 4
            elif role == 'system':
                problem = None
                if isinstance(text, str) and len(text) <= FEEDBACK_SYSTEM_CHARS:
                    try: event = json.loads(text)
                    except (ValueError, RecursionError): problem = 'Malformed JSON'
                elif isinstance(text, dict): event = text
                else: problem = 'Oversized or non-structured system message'
                if not problem and (not isinstance(event, dict) or not isinstance(event.get('event'), str)):
                    problem = 'System message lacks a structured event'
                if problem:
                    stats['unparsed_system_messages'] += 1
                    item['diagnostic'] = {'unparsed_system_message': True, 'reason': problem}
                else:
                    facts = {key: event[key] for key in
                             ('event', 'function', 'tool_name', 'node', 'node_id', 'from_node',
                              'source_node', 'target', 'matched', 'reason', 'confidence',
                              'name', 'value', 'source', 'input_text', 'deferred') if key in event}
                    if isinstance(facts.get('function'), dict):
                        definition = facts['function']
                        facts['function'] = {key: definition[key] for key in ('name', 'handler') if key in definition}
                        stats['omitted_bulk_fields'] += max(0, len(definition)-len(facts['function']))
                    kind = event['event']
                    for key in ('node', 'node_id', 'source_node', 'from_node'):
                        if isinstance(event.get(key), str):
                            current_node = event[key]
                            break
                    if kind == 'variable_extracted' and isinstance(event.get('name'), str) and len(event['name']) <= 128:
                        extracted.add(event['name'])
                    if kind == 'function_call_start':
                        args = event.get('args')
                        if isinstance(args, dict):
                            facts['args'] = {key: value for key, value in args.items()
                                             if key not in ('code', 'headers')}
                            stats['omitted_bulk_fields'] += sum(key in args for key in ('code', 'headers'))
                        else:
                            facts['args'] = args
                        priority = 3
                    elif kind.startswith('function_call_complete'):
                        outcome = event.get('result')
                        facts['result'] = ({key: outcome[key] for key in
                                            ('status', 'status_code', 'validation_errors', 'message', 'data')
                                            if key in outcome} if isinstance(outcome, dict) else outcome)
                        priority = 5 if isinstance(outcome, dict) and outcome.get('validation_errors') else 3
                    elif kind == 'route_evaluated':
                        facts['branches'] = event.get('branches')
                        priority = 2
                    elif kind in ('tool_call_routing', 'variable_extracted'): priority = 2
                    else: priority = 1
                    table = event.get('variable_table')
                    if isinstance(table, dict):
                        stats['omitted_bulk_fields'] += 1
                        prompt_refs = (shared_prompt_refs | node_references(current_node)
                                       | node_references(event.get('target')))
                        prompt_values, omitted_prompt_values = {}, 0
                        for key in sorted(prompt_refs):
                            if key not in table: continue
                            if len(prompt_values) >= 16:
                                omitted_prompt_values += 1
                                continue
                            value = metadata(table_value(table, key), stats, limit=1000)
                            if size({**prompt_values, key: value}) <= 3200:
                                prompt_values[key] = value
                            else: omitted_prompt_values += 1
                        if prompt_values:
                            facts['prompt_variables'] = prompt_values
                            priority = max(priority, 3)
                        if omitted_prompt_values:
                            facts['prompt_variables_omitted'] = omitted_prompt_values
                            stats['truncated_values'] += omitted_prompt_values
                        referenced = references(facts.get('branches')) | extracted
                        routing = {}
                        # Branch inputs and extracted fields first; then small
                        # state/route flags. No repeated prompts/account snapshots.
                        keys = [key for key in sorted(referenced) if key in table]
                        keys += [key for key in islice(table, 256) if isinstance(key, str) and key not in referenced
                                 and not key.startswith(('system.', 'call.'))
                                 and re.search(r'(^|[._])(route|state|phase|counts?|attempts?|ready)([._]|$)', key, re.I)]
                        for key in keys[:32]:
                            value = table_value(table, key)
                            if value is None or isinstance(value, (bool, int, float)) or (isinstance(value, str) and len(value) <= 256):
                                routing[key] = value
                        if routing: facts['routing_variables'] = routing
                        if len(keys) > 32 or len(table) > 256: stats['truncated_values'] += 1
                    item['event'] = bounded(facts, stats)
            else:
                item['diagnostic'] = {'unparsed_message': True}
                stats['unparsed_system_messages'] += 1
            # A wide nested result may still exceed the row's allowance. Keep
            # explicit scalar status/errors instead of cutting serialized JSON.
            if size(item) > 6000:
                facts = item.get('event', {})
                outcome = facts.get('result')
                if isinstance(outcome, dict):
                    outcome.pop('data', None)
                    outcome['_truncated'] = 'large result data omitted'
                facts.pop('branches', None)
                facts.pop('args', None)
                facts['_truncated'] = 'large event payload omitted'
                stats['truncated_values'] += 1
            candidates.append((priority, index, item))
        selected, used = [], size(row) + 512
        for priority, index, item in sorted(candidates, key=lambda value: (-value[0], value[1])):
            cost = size(item) + 1
            if len(selected) < 160 and used + cost <= row_budget:
                selected.append((index, item)); used += cost
        row['messages'] = [item for index, item in sorted(selected)]
        row['feedback'] = {**stats, 'original_messages': len(source_messages),
                           'included_messages': len(selected),
                           'omitted_messages': len(source_messages)-len(selected)}
        # The remaining excess can only be JSON escaping of long metadata or
        # diagnostics; remove lowest-priority messages, never the scenario row.
        while size(row) > row_budget and row['messages']:
            row['messages'].pop()
            row['feedback']['included_messages'] -= 1
            row['feedback']['omitted_messages'] += 1
        result['rows'].append(row)
    result['feedback'] = overall_stats
    if size(result) > FEEDBACK_MAX_CHARS:
        # Huge Unicode metadata must also respect the transport limit.
        for row in result['rows']:
            for key in ('name', 'outcome', 'reason'):
                if isinstance(row.get(key), str) and len(row[key]) > 128:
                    row[key] = row[key][:128] + ' [TRUNCATED metadata]'
                    row.setdefault('feedback', {}).setdefault('truncated_values', 0)
                    row['feedback']['truncated_values'] += 1
    return result


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
