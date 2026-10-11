# Compile a bank's policy into a dependable phone workflow

Read ALL supplied bank material and its accompanying API schema. The material is
authoritative for bank identity, opening sentences, question order, retry budgets,
business calendars, deadlines, limits, persuasion, product handling, notes, transfers,
closing codes and terminology. No rule or value may come from memory or another
bank. A later amendment overrides an earlier extract. Explicit precedence matters.
An example in documentation illustrates syntax, never the bank's policy.
Use the language, forms of address, monetary notation and date conventions of
the supplied case. Read all file types, sheet names, tables and attached flow
diagrams. The practice bank's endpoints and collection rules are not defaults
for a different case. Examples of conversations are evidence of intended
behavior; reconcile them with explicit amendments and the service contract.

Your output is JSON with these fields:

- `policy`: a compact but COMPLETE normalized specification. List source references,
  overrides and the rule priority order. Enumerate all closing combinations and
  product-note rules. Document exactly how calendar and amount rules are computed.
- `workflow`: the complete Freya workflow, using the compact syntax below for
  tools and code nodes. All prompts, routes and bank-specific logic are authored
  by you from the input material.
- `tool_config`: object keyed by bank tool name. Each value may hold `description`,
  `field_descriptions` (map from API body field name to descriptive instruction),
  `pre_process_code`, `post_process_code`, and `response_mapping`.
- `checks`: an array of local code checks. Each has `name`, `node`, optional `tool`,
  `hook` (`code`, `pre`, or `post`), `vars`, optional `config`, optional `result`,
  and `expect_vars` and/or `expect_result`/`expect_config`. Use supplied API shapes
  and fresh synthetic data. Include weekend/holiday dates, band edges, failed
  security answers, split inputs, and successful versus failed writes where code
  handles them. Do not require external calls.
- `smoke`: when the documents include synthetic test customers, provide a name,
  an initial caller `message` in the case language, and `variables` from one
  documented test customer. Optional `expected_fragments` must be short exact
  phrases explicitly required in the opening by the source policy. This runs
  just one chat turn after publication and then ends the synthetic chat. It is
  a startup check, not a full policy score. Never invent test identities. Omit
  smoke if the documents provide no usable synthetic customer variables.

The workflow is what gets evaluated. Optimize reliability across repeated runs,
not merely prompt elegance. The phone model is fixed and relatively small.

## Compact output syntax (the builder expands this deterministically)

Do NOT repeat JSON schemas, HTTP URLs, headers, handlers or fixed tool boilerplate.
The builder derives them directly from the supplied OpenAPI, preserving fields,
types, enums and requiredness. In a conversation node write for example
`"tools": ["verify_identity", "schedule_callback", "transfer_to_agent", "close_call"]`.
For an account API node write `"pre_actions": ["get_account"]`. The corresponding
tool_config entry supplies its hooks, description and response mappings; for a
pre_action its mappings are moved to the node automatically. Do not duplicate
these mappings explicitly on that node.

Every body field is baked as an unset placeholder `arg_<tool>_<field>`, except
customer_id which is baked from the call's customer_id. Never store workflow
state under one of those arg_ names. Model values arrive in config['body'] for
pre-hooks. The post-hook can remember pre-hook values stored under separate names.

A code node has `"code": "<Python source>"` instead of pre_actions. The builder
wraps it in code_exec. Keep its silent on_enter, passthrough, fallback and
transitions explicit. An end_call node can omit terminal: the builder adds a
silent end_call with message_mode=none. Deliver the required farewell before
hangup and in the order required relative to any bank closing operation.
This compact syntax changes serialization only, never policy.

## Workflow architecture

Use compact stage-specific conversation nodes, required account lookups, code
steps for policy calculations, and terminal nodes. The following collection
patterns apply only when those actions exist in the supplied case. It is
fine for one identity node to handle name confirmation, third parties, security,
callback and pre-verification human requests. In the collection node preserve
the complete conversation history. Avoid routing on guessed user intent when a
tool result provides an authoritative transition. If the policy requires
verification before lookup, make the lookup unreachable until those checks
succeed. A failed security answer must
not be treated as success. A correction before validation is not a failed attempt.
Enforce the policy's verification and data-loading prerequisites at EVERY
account discussion/write stage, including exception/fallback routes. A code failure
must never send an unverified caller to an account conversation with empty facts.
Do not reuse a payment-write conversation as a security-answer executor. If
complete answers need deterministic validation, use a dedicated engine-run
verification step after validation, then return to a speaking security step.
Clear stale tool-result flags before each new attempt. Routes may be suppressed
until the node has spoken, so a delayed route must preserve a newly supplied
answer rather than consume it as acknowledgment of the previous tool result.

Expose only tools appropriate to the stage. Tool names, URL, fields, types,
enums and response paths must match the INPUT OpenAPI exactly. Resolve local
OpenAPI references. The phone agent calls only those endpoints. Use `default`,
not `const`. Bake customer_id from the call. For model-supplied body fields use
unique unset placeholders such as `{{arg_create_promise_amount}}`; the same
placeholder must never be a stored workflow state variable. Declare field enums
and descriptions on the body property's leaf. Do not add fictitious request fields.
Do not accidentally freeze the previous product/date/answer on node entry.

Perform the calculations the case actually requires. Calculate from the CALL's
`now`, never the server clock, for policy-defined matters such as:
business-day deadlines per product, next permissible days, persuasion offer days,
callback windows, floors and any amount rounding. Give these facts to the model
in tool responses/prompts, including actual product IDs and human product labels.
The account result is a runtime value, never a public test fixture. Code must
handle a list, JSON string or flattened keys when reading mapped data. All code
uses only json, re, datetime (and basic built-ins), initializes fallback variables,
is wrapped in try/except, and has no double opening or closing braces anywhere.
An initial code node can be skipped by the chat API: prefer a conversation as the
initial node and compute callback facts within the callback hook, or include a
safe fallback from `now`. Account-derived calculations run after account lookup.
The chat API can start directly with the caller's first message without running
the initial on_enter greeting. Put the required opening in the initial node's
task_message too, conditioned on it not already having been spoken in history.
Do not assume an entry action ran merely because the initial node is active.
The builder also persists declared response_mapping values from the post-hook,
so structured lists and objects are available under your mapped variable names.
For automatic pre_actions the flattened response prefix is the NODE name, such
as lookup_response, not necessarily the tool name. Use the actual node name if
you implement a flattened fallback; test that fallback with the same prefix.

Post-hooks must remove headers and add a short `what_to_do_next` instruction to
the data actually seen by the model. Cover success AND failure. Direct it to speak
or perform the next permitted tool call immediately, never leave an empty turn.
`result` is an envelope: its `data` is the bank body; code must check types.
Post-hooks may maintain explicit state in `vars`, mapped into string route flags.
Keep tool retry budgets explicit; maxRetries=0 on writes. Do not fake a bank
success to cover an invalid request. A pre-hook may normalize representation,
but must not silently alter a customer's confirmed amount or date. Invalid
proposals must be explained and reconfirmed before a bank write. Do not rely on
raising in a hook to cancel an action (that behavior is undocumented).

Track successful promises and transfers from actual responses. Do not infer
success from an HTTP envelope alone: inspect the bank's success field. Avoid
duplicate writes. If a write failed, retry only as many times as the brief allows,
and follow its failure outcome. Never claim a failed operation was recorded.
No notes should be emitted early if the brief forbids notes on a later transfer;
defer such notes until final resolution. Pending promises are distinct from
recorded promises. A later transfer must not record unconfirmed or merely agreed
promises if the policy forbids it. Preserve valid recorded promises.

Follow the case's closing protocol exactly once. If it supplies a bank closing
operation, obey its required ordering (including making it the last bank call
when specified), and gate completion on its actual success. If there is no such
operation, do not invent one. Say required confirmations and farewell before
the silent end_call. Do not add a duplicate lifecycle close. Omit optional
closing reasons for outcomes that require none.
Prefer one authoritative closing path with deterministic outcome reconciliation
against actual recorded state and the brief. A transfer takes precedence if the
brief says so. Do not overwrite a correct unverified/third-party close code with
a generic no-promise fallback. Never disclose protected account information
outside the case's verification and privacy rules.

## Conversation robustness

Interpret the corrected portion of a sentence, not the first mentioned value.
Assemble digits spread over turns before validating. Preserve leading zeroes.
Do not validate a partial answer. Normalize spoken numbers, dates and codes
to the API's prescribed representation. Security answers must come from the
customer. Ask only for missing pieces, and retry only the failed question.
Use the supplied date interpretation rules, including weekday conventions.
An unrelated event/date in small talk is not a payment proposal.
Brief-specific refusal/clarification limits still apply to questions asked back.

Cover every policy branch: unclear name, wrong number, deceased, relative offers
to pay, invalid callbacks, suspicion/AI/human questions, refusal of identity,
wrong answers and hints, all-product opening, already-paid versus historical
dispute, hardship taking precedence over ordinary negotiation, restructuring,
partial payment, per-product attempts, ambiguous/late/nonbusiness dates,
read-back corrections, duplicate promise requests, and write failures. Only
apply a branch when the supplied policy defines it; never import its wording
or thresholds from another brief. State the full debt before asking for payment
when required. Do not introduce extra questions that prematurely solicit refusal.

Never ask the customer for an amount if policy requires agent-led offers.
Do not count a proposed date or amount as refusal where the policy distinguishes
them. Track attempts per product, respect early/late limits, avoid repeating
rejected offers. For multiple products, follow source order and read-back rules.
The user may change one element at confirmation: revalidate and confirm anew.
No extraneous internal explanations, node names, tool names or implementation
details in customer-facing dialogue. Keep questions short and sequential.

## Platform invariants

- No nulls and no agent_config. Valid node_type, node name matches its key.
- All workflow test_variables values must be strings.
- No tools on code/api_request nodes; no pre_actions on conversation nodes.
- response_mapping on the tool for conversation tools, on the node for pre_actions.
- Mapping paths start with data.; boolean conditions accept true and True or
  preferably use explicit string state. Avoid stale success flags in retries.
- Top-level condition groups use logic=or; nest and-groups if needed.
- Every passthrough node has a final always transition and fallback target.
- Nodes holding ongoing conversation need no unconditional self-transition.
- Only the terminal handler performs hangup, after the required closing protocol.
- No context_variables dependency: the platform can silently strip it.
- No placeholder substitution inside code. Use vars directly.
- Tools must trigger actions, not merely describe them. After any result the
  phone model must either speak or call the next permitted tool.
- Stay within 4-9 nodes unless the policy truly requires more. Avoid long chains
  that delay speech. Do not expose optional workflow architecture to the customer.

Do a final adversarial policy coverage review internally before returning JSON.
