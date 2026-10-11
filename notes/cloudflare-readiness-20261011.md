# Cloudflare readiness — 11 October 2026

Research used official Cloudflare documentation only. No authentication, account
inspection, remote deployment, dependency installation, or source changes were
performed for this research. The participant's personal Cloudflare account is
still pending; do not assume an account or select an employer account.

## Contract-dependent durable state

If the released service contract requires persistent mutable state,
SQLite-backed Durable Objects are available on Workers Free. Each object has
private, transactional, strongly consistent storage. Persist required state with
the Storage API: in-memory fields can disappear on eviction or deployment.
The final contract must determine state boundaries, initial fixtures, repeated
customer behavior, retries, authentication, and any reset behavior.

- [Storage guarantees and restart behavior](https://developers.cloudflare.com/durable-objects/best-practices/access-durable-objects-storage/)
- [Free-plan pricing and limits](https://developers.cloudflare.com/durable-objects/platform/pricing/):
  100,000 DO requests/day, 5 million rows read/day, 100,000 rows written/day,
  5 GB total storage. Free-limit exhaustion causes operation failures; daily
  allowances reset at 00:00 UTC.
- [Named object API](https://developers.cloudflare.com/durable-objects/api/namespace/):
  repeated access to the same name in the same namespace refers to the same
  object. Test isolation must account for persisted mutations.
- [SQL transactions](https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/#transactionsync):
  `transactionSync()` can wrap synchronous SQL operations and roll back on
  exceptions. Raw SQL `BEGIN`/`SAVEPOINT` statements are unsupported.

Workers KV is eventually consistent and concurrent writes can overwrite each
other, so it is a poor authoritative ledger choice when the contract requires
immediate consistent reads or atomic changes.
[Official KV write guidance](https://developers.cloudflare.com/kv/api/write-key-value-pairs/).
[D1](https://developers.cloudflare.com/d1/platform/pricing/) is another Free SQL
option; choose only after the actual contract is available.

## Wrangler configuration

Installed Wrangler 4.149.0's local schema supports both the current `exports`
format and the legacy `migrations` format. They are mutually exclusive. The
following is an illustrative configuration, not an implemented contract:

```json
{
  "durable_objects": {
    "bindings": [{"name": "STATE", "class_name": "ContractState"}]
  },
  "exports": {
    "ContractState": {"type": "durable-object", "storage": "sqlite"}
  }
}
```

The Worker must export the matching class. Alternatively, omit `exports` and
use `"migrations": [{"tag": "v1", "new_sqlite_classes": ["ContractState"]}]`.
Do not use `new_classes` for a Free-plan namespace. Avoid unneeded class renames
or namespace deletion because lifecycle changes affect persisted data.

- [Current exports configuration](https://developers.cloudflare.com/durable-objects/reference/durable-objects-migrations/)
- [Supported legacy migrations](https://developers.cloudflare.com/durable-objects/reference/durable-object-class-migrations-legacy/)

Keep this repository's `mock/wrangler.jsonc` valid plain JSON as required by its
isolation wrapper. Use `scripts/wrangler.py`; the wrapper requires a recorded
personal account before actual deployment.

## Local verification and published contract

Use local mode through the wrapper, with a fresh persistence directory per
independent test suite:

```sh
python3 scripts/wrangler.py dev --local --persist-to /tmp/freya-contract-test-01
```

Then restart with the same directory to verify persistence. Exercise the
contract's state transitions, repeated customer calls, concurrent mutations,
and isolation. Do not add a reset endpoint or automatic reset without contract
support. Wrangler uses locally simulated resources; DO has no CLI seed command,
so initialize fixtures through application code. Raw Miniflare defaults to
memory unless persistence is configured. DO remote binding connections are not
supported; local mode is sufficient for these checks.

- [Local persistence and seeding](https://developers.cloudflare.com/workers/local-development/local-data/)
- [Miniflare Durable Objects](https://developers.cloudflare.com/workers/testing/miniflare/storage/durable-objects/)
- [Development binding support](https://developers.cloudflare.com/workers/local-development/bindings-per-env/)

README describes publishing the exact mock contract at `/openapi.json`. The
current builder fetches that URL with a `User-Agent` only; it does not attach the
mock team key. Keep the published schema readable by that fetch, or supply the
schema in the case folder/service documents. Merely setting
`FREYA_BANK_TEAM_KEY` does not define or implement a service authentication
scheme. Implement endpoint authentication only as required by the released
contract, and verify the generated phone-tool headers against it.
