# Final bank-service mock

The updated event rules require a Cloudflare Worker built from the final service
contract and supplied synthetic customers. This directory currently contains
infrastructure only. It is not deployed and cannot handle bank calls yet.

Use the project-local Node.js 22+ and Wrangler through `scripts/wrangler.py`.
After the participant identifies their personal Cloudflare account, authenticate
with `python3 scripts/wrangler.py login` from the repository root. Record its
32-character account ID in the ignored `private/cloudflare-account.json` as
`{"account_id": "..."}`. Never select a company account.

The wrapper isolates Cloudflare authentication, blocks configuration/auth overrides,
and prevents implicit `.env` loading. Keep `wrangler.jsonc` valid JSON; every
configured `account_id`, including environment-specific values, must match the
recorded personal account. `npm run dev`, `npm run check`, and `npm run deploy`
inside this directory all use the wrapper. Only local development and dry-run
deployment are available before an account is recorded. After implementing the
released contract, test every endpoint and state transition locally before deployment.

The deployed mock should serve its exact contract at `/openapi.json`; the generic
builder can read it together with the case documents. Keep the mock reachable
until event results are announced. The final phone agent may call only this mock.
