# Final bank-service mock

The updated event rules require a Cloudflare Worker built from the final service
contract and supplied synthetic customers. This directory currently contains
infrastructure only. It is not deployed and cannot handle bank calls yet.

Use Node.js 22+, run `npm install`, authenticate to the participant's personal
Cloudflare account, and pin that account in the deployment configuration. Never
select a company account. After implementing the released service contract,
test every endpoint and state transition locally before `npm run deploy`.

The deployed mock should serve its exact contract at `/openapi.json`; the generic
builder can read it together with the case documents. Keep the mock reachable
until event results are announced. The final phone agent may call only this mock.
