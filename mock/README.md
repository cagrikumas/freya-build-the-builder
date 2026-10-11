# Final bank-service mock

This Worker implements the seven test services in the released
`2026-10-01-service-contract.md` and `test-environment/test-customers.md`.
All responses come from the exact supplied synthetic customer table; amounts,
strings, missing fields and error envelopes are preserved. The current fixture
is from complete snapshot `20261011T172903.227205Z` (unchanged from the earlier
17:27 release), SHA-256
`d6ce155638f61ab17910d53ea993a2b0d68cf4e10d6b9db2fb8e4a7add0ef44d`.

Every bank route is a JSON `POST` under `/voice/v1/` with fields inside `data`:

| Route suffix | Fixture selectors | Additional required request fields |
|---|---|---|
| `cards.list` | `customerNo` | none |
| `cards.balance` | exact `cardNumber` from the list | none |
| `statement.week.get` | exact `cardNumber` | none |
| `statement.week.decide` | `cardNumber`, `newStatementWeek` | current `statementDay` |
| `statement.week.change` | `cardNumber`, `newStatementWeek` | current `statementDay` |
| `contact.email.get` | `customerNo` | nonempty `intAddressInfoType` |
| `statement.pdf.send` | `customerNo` | `cardNumber`, `currencyType`, `statementDate`, `emailAddress` |

Numeric and string customer numbers/weeks select the same answer. Missing or
empty required fields return a 400 `INVALID_ARGUMENTS_ERROR` envelope. Missing
fixtures return the service's documented 404, or 400 when that service has no
404. The one `delaySeconds: 12` fixture waits twelve seconds before returning;
that metadata is never included in the response body.

As required by the test-environment rules, token, headers, `call` and `aiFlow`
are ignored. There is no production OAuth service or invented token. The data is
an immutable fixture table: preview/change/send calls return their exact fixture
without inventing persistent mutations, annual counters or reset endpoints.
Registered-address authorization belongs to the assistant: the PDF mock does not
reject alternate nonempty addresses, matching the backend/test contract.

`GET /openapi.json` publishes the seven-route contract with the requesting
Worker's origin as its server URL. `GET /health` returns ready status. Unknown
routes return 404; known bank routes used with other methods return 405.

Use project-local Node.js 22+ and Wrangler through `scripts/wrangler.py`:

```sh
.tools/node_modules/node/bin/node --test mock/test/*.test.js
python3 scripts/wrangler.py dev --local --port 8787
```

The tests replay all 617 fixture HTTP responses, check response schemas, exercise
missing/unknown inputs, verify ignored metadata and numeric/string key handling,
and check exact static responses across repeated writes. The twelve-second delay
is observed through an injected wait function so unit tests finish quickly.
All 617 responses were also replayed through local Wrangler, including the real
twelve-second wait, with exact HTTP status/body comparisons.

After the participant identifies their personal Cloudflare account, authenticate
with `python3 scripts/wrangler.py login` from the repository root. Record its
32-character account ID in the ignored `private/cloudflare-account.json` as
`{"account_id": "..."}`. Never select a company account. The wrapper isolates
authentication, blocks configuration/auth overrides, and prevents implicit
`.env` loading. Keep `wrangler.jsonc` valid JSON. All configured account IDs must
match the recorded personal account.

Deployment uses `python3 scripts/wrangler.py deploy` after local verification and
account authorization. Keep the same public Worker reachable until event results
are announced. Point the builder at its HTTPS origin; the builder reads the
published schema without needing credentials. Deployed on 2026-10-11 to
`https://freya-bank-mock-cagrikumas.freya-hackathon-bank-mock.workers.dev`
(version `41f921e7-a2de-42fc-ba20-8c1b195dfe57`). Twelve remote checks passed,
covering all seven services, exact 404/500 fixtures and the real twelve-second
delay. See `results/20261011-mock-cloudflare-smoke.json`. The verifier uses its
own descriptive User-Agent because Cloudflare rejects the generic Python-urllib
client signature; ordinary httpx access also passed. Final Freya tool access is
verified separately by the builder run.
