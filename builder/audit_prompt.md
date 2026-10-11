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
- Instructions that contradict the brief, especially first questions, negotiation
  counters, offering a floor, refusal versus a proposed value, multi-product order,
  a combined read-back, or routing a hardship/restructuring request incorrectly.
- Numeric-only dates and split digits: an incomplete or superseded answer cannot
  consume a security attempt. Wrong answer handling must not re-ask passed questions.
- Calendar off-by-one errors, holidays adjacent to weekends, a Friday holiday,
  distinct deadlines per product, a nonbusiness `now`, and policy weekday semantics.
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

Prefer small, concrete corrections to a wholesale redesign. Local checks must
assert expected results computed independently from the relevant bank rule, not
copy the implementation's answer. Add checks for any concrete code defect fixed.
