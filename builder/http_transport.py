"""Curl transport for staging, preserving the event client's API contract."""
import json
from pathlib import Path
import subprocess
import tempfile
import urllib.parse


def request(method, url, headers, body=None):
    # Secrets are supplied over stdin, never command arguments or trace output.
    config = ''.join('header = ' + json.dumps(k + ': ' + v) + '\n' for k, v in headers.items())
    cmd = ['curl', '--disable', '--silent', '--show-error', '--connect-timeout', '10',
           '--max-time', '110', '--request', method, '--write-out', '\n%{http_code}',
           '--config', '-']
    with tempfile.TemporaryDirectory(prefix='freya-http-') as directory:
        if body is not None:
            payload = Path(directory) / 'request.json'
            payload.write_text(json.dumps(body))
            payload.chmod(0o600)
            cmd += ['--data-binary', '@' + str(payload)]
        result = subprocess.run(cmd + [url], input=config, text=True, capture_output=True, timeout=115)
    if result.returncode:
        raise RuntimeError(f'{method} {urllib.parse.urlsplit(url).path}: curl error {result.returncode}: {result.stderr[-600:]}')
    content, status = result.stdout.rsplit('\n', 1)
    if int(status) >= 400:
        raise RuntimeError(f'{method} {urllib.parse.urlsplit(url).path} -> {status}: {content[:1500]}')
    return json.loads(content)


def install_curl_transport(freya):
    def api(method, path, body=None, **params):
        query = '?' + urllib.parse.urlencode(params) if params else ''
        out = request(method, freya.URL + path + query, freya.HEADERS, body)
        return out.get('data', {}).get('result', out) if isinstance(out, dict) else out
    freya.api = api
