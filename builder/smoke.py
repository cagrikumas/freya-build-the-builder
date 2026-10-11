"""Check that the published workflow starts, using document-supplied test data."""
def run_smoke(freya, workflow_id, spec):
    if not isinstance(spec, dict) or not isinstance(spec.get('message'), str) or not isinstance(spec.get('variables'), dict):
        raise ValueError('A smoke check needs a caller message and document-derived variables')
    response = freya.api('POST', '/api/v2/chat/message', {
        'workflowId': workflow_id, 'message': spec['message'], 'customerVariables': spec['variables']})
    call_id = response.get('callId')
    try:
        speech = response.get('response')
        errors = []
        if not isinstance(speech, str) or not speech.strip(): errors.append('No spoken opening returned')
        elif '{{' in speech or '}}' in speech: errors.append('Unresolved workflow variable in speech')
        for fragment in spec.get('expected_fragments', []):
            if not isinstance(speech, str) or fragment.casefold() not in speech.casefold():
                errors.append('Required opening fragment missing: ' + fragment)
        return {'call_id': call_id, 'response': speech, 'errors': errors, 'passed': not errors}
    finally:
        if call_id: freya.api('POST', '/api/v2/chat/end', {'callId': call_id})
