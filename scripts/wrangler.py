#!/usr/bin/env python3
"""Project-local Wrangler, isolated from unrelated Cloudflare credentials."""
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
# Wrangler gives this legacy directory precedence over XDG_CONFIG_HOME.
# Refuse that fallback instead of reading credentials from another project.
if (Path.home()/'.wrangler').is_dir():
    raise SystemExit('Legacy global Wrangler directory detected; stop to preserve credential isolation.')
env = os.environ.copy()
for key in list(env):
    if key.startswith(('CLOUDFLARE_', 'CF_', 'WRANGLER_')):
        env.pop(key)
env['XDG_CONFIG_HOME'] = str(root/'private/cloudflare')
env['WRANGLER_SEND_METRICS'] = 'false'
account = root/'private/cloudflare-account.json'
if account.exists():
    env['CLOUDFLARE_ACCOUNT_ID'] = json.loads(account.read_text())['account_id']
if sys.argv[1:2] == ['deploy'] and '--dry-run' not in sys.argv and not account.exists():
    raise SystemExit('Select and record the personal Cloudflare account before deployment.')
node = root/'.tools/node_modules/node/bin/node'
wrangler = root/'.tools/node_modules/wrangler/bin/wrangler.js'
raise SystemExit(subprocess.call([str(node), str(wrangler), *sys.argv[1:]], cwd=root/'mock', env=env))
