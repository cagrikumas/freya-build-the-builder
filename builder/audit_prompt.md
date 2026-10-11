Independently audit this generated phone workflow against ALL the supplied bank
documents and the tool API. Return JSON:
{"approved": true or false, "issues": [specific defects], "patches": [JSON edits if needed]}

If approved, patches is empty. Otherwise return precise JSON Patch operations:
each has op (add, replace, remove), path (a JSON Pointer into the candidate), and
value (except remove). Use /checks/- to append a check. Replace an entire code
string if fixing it. Do not return a rewritten full artifact. The builder applies
these edits deterministically and validates the resulting artifact. Keep edits
small enough to leave time for platform validation and practice tests.
Check every pointer against the actual candidate and all preceding edits. Array
indexes are zero-based; identify checks by their actual name before counting their
index. Never assume an object key exists in a neighboring check. A JSON-encoded
string is a leaf, not a traversable object; replace that full string if needed.
Apply only the supplied policy. Distinguish amendments from superseded
rules. Do not invent a default bank rule for a missing piece.

The candidate may use the supplied compiler's compact serialization. Named tools
are expanded from OpenAPI by the builder, with hooks in tool_config; code nodes'
code strings are wrapped as code_exec. Do not flag missing expanded boilerplate
as a defect. Preserve that compact format and every tool_config entry when fixing
the artifact. All other platform and bank constraints still apply.

Review the actual Python snippets, tool schemas, conditions, prompts and response
paths. Reason through both success and failure. Look especially for:

- A transition that is reachable before its required tool succeeds, or a stale flag
  that moves the conversation early on the next attempt.
- Security and payment stages sharing an action node, delayed transitions losing
  a fresh answer, or an exception fallback bypassing source-required authorization
  or data-loading prerequisites. Honor a source-specified trusted upstream handoff
  without inventing additional identity steps. Where checks are required, trace a
  failed answer followed by its correction across actual nodes, not only hooks.
- Instructions that contradict the brief, especially first questions, negotiation
  counters, offering a floor, refusal versus a proposed value, multi-product order,
  a combined read-back, or routing a hardship/restructuring request incorrectly.
- Extraction descriptions whose valid outputs the evaluator cannot consume.
  Trace ordinary spoken names and unambiguous aliases through entity resolution;
  do not substitute internal IDs unavailable to the extractor. Check every enum,
  especially empty/none/unclear/non-answer, against source-defined clarification,
  attempt and termination rules. The extraction model does not see the dialogue
  prompt or arbitrary runtime variables.
- Complex JSON lists/objects hidden inside string extraction fields. A valid
  string can still contain prose or malformed serialization. Prefer small
  primitive fields and code-assembled correlated statements, retaining source
  scopes and each amount/date/kind together. Trace missing/malformed/conflicting
  fields and a proposal with no usable terms. These must remain unresolved
  input handled under source clarification rules, not become refusal, paid,
  dispute, acceptance, or a fabricated proposal. Check that one extracted
  field cannot contradict another and silently change the customer's act.
- Shared extraction names with incompatible types, enum sets or meanings across
  stages. Check all code/hook writes against the registered extraction schemas,
  including clearing/consumption: an undeclared empty enum value can be rejected
  by the platform and retain stale input. Use namespaced fields and valid neutral
  sentinels or separate processing state; update affected local checks to assert
  the valid contract before the test suite is frozen for later repairs.
- A dialogue task missing the exact source-defined identity questions and
  boundaries because those facts appear only in code/extraction. A small phone
  model may invent a familiar but unauthorized question or continue security in
  a closing node. Make the source-derived permitted speech explicit in each
  applicable task and make a computed next utterance authoritative.
  For initialized question-only stages with code-computed authorized speech,
  require on_enter {"type":"tts","text":"{{computed_speech}}"}, an ordinary
  deterministic always transition to the evaluator after the user reply,
  and no is_tool_call/loop_condition that delegates or blocks that route.
  The question stage waits for a reply; do not make it passthrough. Verify
  every entry initializes the speech and that extraction precedes the route.
  A strong "say exactly" LLM instruction is not equivalent to fixed speech.
  Trace caller-first input, delayed answers and result-only re-entry so fresh
  replies are consumed once before the next question. Separate stages whose
  permitted question types differ. Do not replace action-after-speech stages
  with TTS alone: required tools still need a documented explicit engine route
  or constrained action stage in source-prescribed order. TTS does not itself
  invoke tools, and a closing stage must not wait for another caller reply
  when immediate action is required. For remaining model-action entries, make
  custom prompts self-contained with actual interpolated values, source
  boundaries and the authorized operation.
- Counters initialized as though an entry question already ran, or counters that
  never advance when a repeated unclear reply takes a different taxonomy branch.
  Trace both caller-first and agent-first starts, actual speaking steps, delayed
  routes, result-only re-entry and the next fresh reply. Apply the input policy's
  authorization conditions to an exception, not just the presence of its label.
- A clarification or repeated offer loop that bypasses a source limit, loses a
  proposal, repeats an already rejected offer, or silently reclassifies a new
  proposal as refusal. Check initial-question and exception rules together.
- Confirmation corrections resolved using a stale negotiation index instead of
  the entities and terms actually read back. Trace partial agreements through
  read-back and a correction, including an omitted entity reference. Preserve a
  proposal's selected entities, amounts and dates across clarification turns;
  clarify ambiguity under the source rules rather than silently narrowing scope
  or dropping another proposed term.
- Numeric-only dates and split digits: an incomplete or superseded answer cannot
  consume a security attempt. Wrong answer handling must not re-ask passed questions.
- Calendar off-by-one errors, holidays adjacent to weekends, a Friday holiday,
  distinct deadlines per product, a nonbusiness `now`, and policy weekday semantics.
- Date handling that recognizes only a few spellings of vague periods, resets a
  clarification allowance on a paraphrase, or discards context needed to resolve
  the customer's next exact date. Resolve from source conventions and call inputs;
  do not repair a limitation by guessing an unsupported date.
  Include locale-specific weekday plus ordinal/numeric day-of-month answers to
  a clarification; preserve month/year/period context and distinguish parser
  coverage gaps from true ambiguity before taking a source-defined fallback.
- Helpers that trust the real date, a hardcoded practice date, or fabricated IDs.
- A pre-hook which changes confirmed monetary terms without another confirmation.
- A success claim before the endpoint's documented HTTP-status/body success
  conditions hold, or code assuming a universal success field or mandatory body.
  Distinguish transport-wrapper status from endpoint/business status as the
  contract requires. A retry that duplicates a successful write, a missing
  failed-product note, notes before a later transfer forbids them,
  or a closing code inconsistent with successful promises/transfer/notes.
- A model asked to call a tool absent from the node, missing required request
  fields, tool parameters baked to an old answer, or double close_call paths.
- Python code that crashes or uses unsupported modules, unreachable snippets,
  silently stripped fields, wrong response envelopes, undefined prompt variables,
  a passthrough deadlock, or empty speech after a tool result.
- A required opening that exists only in on_enter. A chat may begin with the
  caller's first message before that action; the initial task must also produce
  the required opening if it is absent from conversation history, without
  repeating it when a simulation already delivered it.
- Example-conversation scenarios that coach the phone agent, preload internal
  success states, invent customer identities, or omit a documented failure branch.
  Test criteria must independently reflect the source policy, not accept whatever
  the candidate happens to do. Check the fixture and source reference for each.

Prefer small, concrete corrections to a wholesale redesign. Local checks must
assert expected results computed independently from the relevant bank rule, not
copy the implementation's answer. Add checks for any concrete code defect fixed.
Also derive adversarial checks from supplied examples and policy boundaries.
Before encoding them in the supported local-check format, trace the entire
node/result/speaking/next-reply sequence with realistic extraction values and
reachable state. Include natural labels, paraphrases and consecutive non-answers;
an isolated hook supplied with an oracle ID can conceal an extraction-contract
failure. Preserve distinctions and outcomes required by the input policy, rather
than importing a preferred bank rule. State whether evidence covers only code
and prescribed extraction values or actual dialogue; do not claim that a local
replay proves the phone model's routing, extraction or speech.

Reject every Python `global` declaration: platform execution need not use module
scope. Helpers must read or mutate explicit dictionary state (`vars` or a local
dictionary passed to them), never assume a snippet-local variable is a module
global. Module-style local execution can conceal this runtime failure.
Technical catch-all handlers must save a short internal diagnostic (exception
type plus safe operation/reason) before fallback routing, excluding secrets,
headers, payloads and caller data. A successful code_exec envelope does not prove
that the body reached its intended outcome when exceptions are caught.
