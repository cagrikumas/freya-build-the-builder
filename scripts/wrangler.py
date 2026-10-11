#!/usr/bin/env python3
"""Project-local Wrangler, isolated from unrelated Cloudflare credentials."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def boolean_option(args, name):
    value = False
    for index, arg in enumerate(args):
        if arg == name:
            value = args[index + 1] != 'false' if index + 1 < len(args) else True
        elif arg == name + '=true': value = True
        elif arg in (name + '=false', '--no-' + name[2:]): value = False
    return value


def validate_arguments(args):
    forbidden = {'--config', '--cwd', '--env-file', '--profile', '--temporary', '-c'}
    for arg in args:
        option = arg.split('=', 1)[0]
        if option in forbidden or (arg.startswith('-') and not arg.startswith('--') and len(arg) > 2):
            raise SystemExit('Wrangler configuration/auth overrides are disabled: ' + arg)


def validate_accounts(config, account_id):
    if isinstance(config, dict):
        configured = config.get('account_id')
        if configured and configured != account_id:
            raise SystemExit('Wrangler config account_id must match the recorded personal account.')
        for value in config.values(): validate_accounts(value, account_id)
    elif isinstance(config, list):
        for value in config: validate_accounts(value, account_id)


def main(args=None):
    args = list(sys.argv[1:] if args is None else args)
    validate_arguments(args)
    # Wrangler gives the legacy global directory precedence over XDG_CONFIG_HOME.
    if (Path.home()/'.wrangler').is_dir():
        raise SystemExit('Legacy global Wrangler directory detected; stop to preserve credential isolation.')
    account = ROOT/'private/cloudflare-account.json'
    account_id = json.loads(account.read_text()).get('account_id') if account.exists() else None
    if account_id is not None and (not isinstance(account_id, str) or len(account_id) != 32
                                   or any(c not in '0123456789abcdef' for c in account_id.lower())):
        raise SystemExit('Record a valid 32-character personal Cloudflare account_id.')
    command = args[0] if args else ''
    harmless = command in ('login', 'whoami', 'logout', 'version', '--version', '-v', '--help', '-h', 'help')
    dry_run = command == 'deploy' and boolean_option(args, '--dry-run')
    local_dev = command == 'dev' and boolean_option(args, '--local') and not boolean_option(args, '--remote')
    if not account_id and not (harmless or dry_run or local_dev):
        raise SystemExit('Select and record the personal Cloudflare account before any remote operation.')
    config_path = ROOT/'mock/wrangler.jsonc'
    # Keep this project-owned JSONC file valid JSON so its account selection can
    # be verified before Wrangler runs (JSON is also valid JSONC).
    config = json.loads(config_path.read_text())
    validate_accounts(config, account_id)
    if local_dev:
        def remote_bindings(value):
            if isinstance(value, dict):
                return value.get('remote') is True or any(remote_bindings(v) for v in value.values())
            return isinstance(value, list) and any(remote_bindings(v) for v in value)
        if remote_bindings(config):
            raise SystemExit('Local development requires a config without remote bindings.')
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(('CLOUDFLARE_', 'CF_', 'WRANGLER_')):
            env.pop(key)
    env['XDG_CONFIG_HOME'] = str(ROOT/'private/cloudflare')
    env['WRANGLER_SEND_METRICS'] = 'false'
    if account_id: env['CLOUDFLARE_ACCOUNT_ID'] = account_id
    node = ROOT/'.tools/node_modules/node/bin/node'
    wrangler = ROOT/'.tools/node_modules/wrangler/bin/wrangler.js'
    # Prevent Wrangler from loading .env/.env.local after environment filtering.
    return subprocess.call([str(node), str(wrangler), *args,
                            '--config', str(config_path), '--env-file', os.devnull],
                           cwd=ROOT/'mock', env=env)


if __name__ == '__main__':
    raise SystemExit(main())
