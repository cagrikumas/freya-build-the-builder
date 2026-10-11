"""Check that the published workflow starts, using document-supplied test data."""
from freya_client import is_availability_error


def run_smoke(freya, workflow_id, spec):
    if not isinstance(spec, dict) or not isinstance(spec.get('message'), str) or not isinstance(spec.get('variables'), dict):
        raise ValueError('A smoke check needs a caller message and document-derived variables')
    response = freya.api('POST', '/api/v2/chat/message', {
        'workflowId': workflow_id, 'message': spec['message'], 'customerVariables': spec['variables']})
    call_id = response.get('callId')
    result = None
    try:
        speech = response.get('response')
        errors = []
        if not isinstance(speech, str) or not speech.strip(): errors.append('No spoken opening returned')
        elif '{{' in speech or '}}' in speech: errors.append('Unresolved workflow variable in speech')
        for fragment in spec.get('expected_fragments', []):
            if not isinstance(speech, str) or fragment.casefold() not in speech.casefold():
                errors.append('Required opening fragment missing: ' + fragment)
        result = {'call_id': call_id, 'response': speech, 'errors': errors, 'passed': not errors}
        return result
    finally:
        if call_id:
            try:
                freya.api('POST', '/api/v2/chat/end', {'callId': call_id})
            except RuntimeError as error:
                if result is None or not is_availability_error(error): raise
                result['cleanup_error'] = str(error)
                result['cleanup_confirmed'] = False
