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
  `field_descriptions` (map from API body field name, or `path:<name>`,
  `query:<name>` or `header:<name>`, to descriptive instruction),
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
- `scenarios`: when a case folder includes example conversations and usable
  synthetic test customers, turn those examples into up to 12 end-to-end checks.
  Each has `name`, `source` (document/section), `variables` (only documented call
  inputs), `prompt` (instructions to the simulated customer), and
  `success_criteria` (an independent judge's policy, outcome and honesty checks).
  The customer must answer naturally, only reveal requested security information,
  follow the example's intent and corrections, and never coach the agent with
  the expected bank policy or tool names. Criteria must come from the documents,
  not the candidate's implementation; check actual tool outcomes as well as
  speech where visible. Do not preload internal success flags or account facts
  as call inputs. Use documented customers only, and do not fabricate a bank
  reset endpoint. Use this field in folder mode when usable examples and fixtures
  are supplied. Omit it in individual-brief mode, where the official practice
  scorer is used, or when no usable fixtures are supplied. A folder's label as
  synthetic, sample or practice does not by itself make its examples unusable.

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

Primitive OpenAPI path/query/header parameters are also derived from the schema.
For path/query parameters the builder stages model arguments in temporary body
leaves `__bank_path_<name>` and `__bank_query_<name>` (prepend another underscore
if that name collides with an actual body field). Authored pre-hooks may normalize
these leaves; header parameters are in `config['headers'][<name>]`. The builder
then removes the temporary leaves and percent-encodes the URI parameters into
the fixed contract endpoint. Do not manually rewrite its URL or method. Use
location-prefixed field_descriptions when parameter names overlap body fields.
Ordinary request-body fields retain their original names. Complex parameter
serialization is not assumed; compilation must respect supported schema types.
Automatic pre_actions have no caller-model argument turn. Supply their required
values from documented call variables or previously verified state in the
pre-hook, including staged URI parameters; test the actual unset/default inputs.

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

Treat extraction and policy evaluation as one contract. For every extraction
field, account for every declared enum and every representation its description
permits. The evaluator must accept ordinary, unambiguous spoken entity names
and aliases using the loaded entities; do not require a caller to supply internal
IDs or repeat a complete label when the shorter name identifies one entity.
Clarify genuinely ambiguous references without inventing an entity. The
extraction model sees recent messages and its schema, not the dialogue prompt or
arbitrary workflow variables; do not assume it can infer invisible runtime IDs.
Extraction variables are shared across the workflow. Use distinct stage-specific
names for fields with different meanings or enum vocabularies; never reuse a
generic event name with incompatible identity and action-stage definitions.
Every value written by code or hooks into an extracted variable must satisfy its
declared schema too. To mark input consumed, use a declared neutral sentinel or
a separate processed-state variable; clearing an enum to an undeclared empty
string can be rejected and leave the previous value active. Check these writes
and the next turn, including out-of-vocabulary model output handled safely.

Use small primitive extraction fields with explicit neutral/unknown values. Do
not encode a complex list or object as JSON inside an extraction string and
assume its description guarantees valid serialization. Assemble correlated
statements in code from source-appropriate primitive fields. If several
statements are permitted, preserve each statement's entity, amount, date and
kind together through bounded primitive slots derived from the source, or
clarify the statements in stages without discarding the caller's other terms.
Validate representation and semantic consistency before consuming a reply.
Unknown, malformed or conflicting extraction is an explicit unresolved-input
state: clarify under source rules. It must not silently become a refusal, a
paid/disputed claim, acceptance, or a fabricated customer proposal. In
particular, a proposal classification with missing/unparseable terms cannot
consume a refusal budget merely because a parser returned an empty list.

Every speaking node must state its exact permitted questions and next actions,
derived from the source. Critical identity-field names and restrictions cannot
exist only in code or extraction descriptions: the dialogue model needs them in
its own task. Do not let it invent a plausible security question, add a new step,
or continue an earlier stage after a closing transition. If deterministic code
supplies the next utterance, make that instruction authoritative and do not
combine it with a broad invitation to improvise the workflow.
Keep entry speech separate from processing the next fresh caller reply. For
an initialized question-only stage whose complete authorized utterance is
computed by code, use on_enter {"type":"tts","text":"{{computed_speech}}"}.
Initialize that variable on every reachable entry; never speak an unresolved
placeholder or rely on an LLM entry to repeat the value exactly. Route the
next user reply to the evaluator through an ordinary deterministic transition
with condition {"operator":"always"}, omitting is_tool_call (or setting it
false), and no loop_condition that can intercept it. Documented extraction
runs before this routing. The question node must wait for the reply: it is
not passthrough. The evaluator processes the fresh fields and chooses the
next initialized speaking stage. Do not ask an LLM entry to dispatch fresh
input or choose whether the evaluator runs. Explicitly retain/consume fresh
input once across result-only re-entry and preserve caller-first behavior.
Use separate speaking stages when permitted question types differ. Reserve
LLM entry for stages whose task actually requires model action selection; a
custom prompt there must be self-contained, interpolate its actual values,
and state exact source-derived boundaries and authorized action.
A fixed TTS entry does not automatically invoke conversation tools:
preserve any source-required action after speech through an explicit, verified
engine route or a tightly specified LLM action stage. In particular, closing
must not wait for another user reply if the source requires immediate action.

Give empty, unclear, non-answer and refusal classifications explicit handling
under the SOURCE policy, including its clarification and attempt limits. A
repeated unchanged question must not bypass a source-defined termination budget.
Count questions actually delivered, including caller-first starts where no entry
speech ran. Distinguish a new reply from a tool-result-only re-entry; retain new
answers and clear consumed input exactly once. Combine initial-question rules
with exception rules rather than applying either in isolation. A new proposal
and a rejected offer remain distinct; preserve that distinction while obeying
source limits on repeated offers.

Recognize relative periods, incomplete dates and exact dates by their meaning
and the supplied date conventions, not only a short phrase whitelist. Track
clarification allowances across turns independently of the wording used. Retain
relevant prior context and resolve only what the source and call inputs support;
clarify ambiguity instead of guessing or letting a new wording reset a limit.
Handle source-language weekday names combined with ordinal or numeric day-of-month
fragments, preserving the established month/year or period context. Distinguish
an unsupported spelling from a genuinely ambiguous date; never silently replace
a resolvable customer date with a deadline just because its spelling was missed.

At confirmation, resolve corrections against the entities and terms actually
read back, not a stale negotiation index. Preserve a proposal's selected entities,
amounts and dates across clarification turns; an answer to one missing detail
must not silently narrow its scope or discard its other terms. If the reference
is ambiguous, clarify it under the source rules before changing or recording it.

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

Derive adversarial local checks from the source, independently of the generated
implementation. Cover realistic extraction outputs, natural entity aliases,
unclear replies, repeated rejected offers, date paraphrases and source-defined
limits across consecutive turns. Trace complete node transitions, result hooks,
speaking re-entry and the next caller correction before encoding checks in the
supported format. Use reachable states, not invented success flags or oracle
IDs unavailable to the extractor. Include interactions between rules and the
first question, not only isolated happy paths. A deterministic replay supplied
with hand-selected extraction values validates those values only; never present
it as evidence that speech extraction or live dialogue passed.

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
