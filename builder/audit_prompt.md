Independently audit this generated phone workflow against ALL the supplied bank
documents and the tool API. Return JSON:
{"approved": true or false, "issues": [specific defects], "patches": [JSON edits if needed]}

If approved, patches is empty. Otherwise return precise JSON Patch operations:
each has op (add, replace, remove), path (a JSON Pointer into the candidate), and
value (except remove). Use /checks/- to append a check. Replace an entire code
string if fixing it. Do not return a rewritten full artifact. The builder applies
these edits deterministically and validates the resulting artifact. Keep edits
small enough to leave time for platform validation and practice tests.
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
  a fresh answer, or an exception fallback entering account dialogue before both
  identity and lookup succeeded. Trace a failed answer followed by the corrected
  answer across actual nodes, not only through isolated code hooks.
- Instructions that contradict the brief, especially first questions, negotiation
  counters, offering a floor, refusal versus a proposed value, multi-product order,
  a combined read-back, or routing a hardship/restructuring request incorrectly.
- Extraction descriptions whose valid outputs the evaluator cannot consume.
  Trace ordinary spoken names and unambiguous aliases through entity resolution;
  do not substitute internal IDs unavailable to the extractor. Check every enum,
  especially empty/none/unclear/non-answer, against source-defined clarification,
  attempt and termination rules. The extraction model does not see the dialogue
  prompt or arbitrary runtime variables.
- Counters initialized as though an entry question already ran, or counters that
  never advance when a repeated unclear reply takes a different taxonomy branch.
  Trace both caller-first and agent-first starts, actual speaking steps, delayed
  routes, result-only re-entry and the next fresh reply. Apply the input policy's
  authorization conditions to an exception, not just the presence of its label.
- A clarification or repeated offer loop that bypasses a source limit, loses a
  proposal, repeats an already rejected offer, or silently reclassifies a new
  proposal as refusal. Check initial-question and exception rules together.
- Numeric-only dates and split digits: an incomplete or superseded answer cannot
  consume a security attempt. Wrong answer handling must not re-ask passed questions.
- Calendar off-by-one errors, holidays adjacent to weekends, a Friday holiday,
  distinct deadlines per product, a nonbusiness `now`, and policy weekday semantics.
- Date handling that recognizes only a few spellings of vague periods, resets a
  clarification allowance on a paraphrase, or discards context needed to resolve
  the customer's next exact date. Resolve from source conventions and call inputs;
  do not repair a limitation by guessing an unsupported date.
- Helpers that trust the real date, a hardcoded practice date, or fabricated IDs.
- A pre-hook which changes confirmed monetary terms without another confirmation.
- A success claim before the bank's ok response, a retry that duplicates a successful
  write, a missing failed-product note, notes before a later transfer forbids them,
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
