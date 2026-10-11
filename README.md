# Build the Builder — Codex compiler

A folder of bank documents and a deployed mock URL go in. A Freya phone workflow, local checks,
test results and a timestamped build trace come out. All bank-specific policy is
derived during the build from the input documents.

## Requirements

- Python 3.10 or newer (standard library only), `curl`, and Poppler (`pdftotext`, `pdftoppm`).
- Node.js 22+ and Cloudflare Wrangler for the final bank-service mock.
- An authenticated Codex CLI. The builder uses the locally selected Codex model;
  `BUILDER_MODEL` can explicitly select a model. No Claude dependency.
- A Freya workspace API key and one stable mock-bank team key.

Put the following in `env.sh` (excluded from Git), or set environment variables:

```sh
export FREYA_API_URL=https://staging-app.freyavoice.ai
export FREYA_API_KEY=fak_your_key
export FREYA_BANK_TEAM_KEY=your_stable_secret_at_least_16_characters
```

## One command

```sh
python3 builder/build.py path/to/case-folder https://your-mock.your-subdomain.workers.dev
```

Folder mode reads Markdown/text, Word `.docx`, PDF, Excel `.xlsx`, and images.
It preserves tables, sheet/cell labels, and attaches PDF pages and embedded
images for visual interpretation. Unknown file types fail explicitly. The
mock may publish its contract at `/openapi.json`; otherwise the builder derives
OpenAPI from the service documents. Every phone tool targets the supplied mock.

The default folder slot is `final`; practice uses the brief filename. Repeating a build
updates and publishes the same workflow. The builder records model calls,
validations, timestamps, workflow/agent IDs, and exports the saved workflow into
`submission/<slot>.workflow.json`. Each run has its own `traces/<timestamp>-<slot>/`.
Builds have a local 60-minute deadline. `--max-seconds` changes that local limit.
The earlier short model-call timeout was insufficient for some full builds.
The updated final rules no
longer list the earlier 30-minute cap; the submission deadline remains binding.

`--offline` skips Freya operations but still calls Codex to compile the documents.

## Public practice

```sh
python3 builder/build.py \
  build-the-builder-v3/build-the-builder/briefs/brief-a.md \
  build-the-builder-v3/build-the-builder/tools/openapi.json \
  --slot practice-a --practice A

python3 builder/build.py \
  build-the-builder-v3/build-the-builder/briefs/brief-a.md \
  build-the-builder-v3/build-the-builder/briefs/brief-b.md \
  build-the-builder-v3/build-the-builder/tools/openapi.json \
  --slot practice-b --practice B
```

Brief B must be supplied with Brief A. The final is one different case in a
folder, not two hidden Markdown briefs. Do not use the public cases for it.
Use `python3 builder/practice.py <agent_id>` for repeated evaluations (`--reps 3`) and styles
(`--style pieces`, `corrects`, `talkative`, `asks_back`, `in_words`). Only one
simulation may run at a time in the workspace.

This wrapper runs the unchanged kit scorer with `workspaceId` attached to Freya
requests. Explicit workspace context and curl transport were added after staging
requests timed out; organisers have also confirmed a platform incident.
An interrupted public build can be tested without regenerating its unchanged
workflow using `builder/practice.py --publish-generated <workflow.json> --slot
<practice-slot> --brief A --out <results.json>`. Such recovery is recorded as a
practice run and cannot be used as a final builder trace.

Practice runs also save `<results>.session.json`. If a platform status request
fails after starting a simulation, `python3 builder/practice.py --resume-session
<results>.session.json` resumes scoring the original calls; it does not create
another simulation. Recovery currently supports single-repetition evaluations;
it refuses to report one recovered run as several independent repetitions.

Computed questions are spoken through fixed TTS entry with deterministic reply routing;
primitive extraction fields carry caller facts without JSON serialized inside strings.
The model only returns compilation artifacts. The Python program owns validation,
publication and testing. A second compilation call audits the candidate against
the input policy, with static syntax/schema diagnostics from the draft. Public practice failures can trigger an automatic repair and
retest, within the same deadline. A measured regression restores the earlier
candidate. Phone agents use the unmodified model from the supplied
`freya.py`; only the builder uses Codex.

Folder builds can run a one-turn opening check using a synthetic customer from
the documents, then end the chat. Empty speech, unresolved placeholders and
missing required opening phrases fail it. One automatic repair is allowed;
all post-audit repairs preserve the original smoke check, scenarios and existing
local checks (new local checks may be appended). An unsuccessful smoke repair
restores the prior workflow. This is a startup check, not a
claim of passing the hidden policy evaluation.

When the case supplies example conversations and usable test customers, the
compiler also derives simulated-customer scenarios and independent success
criteria from those documents. The builder runs them with the event's fixed
phone model, saves the conversations and can automatically repair observed
failures. The repair must preserve the original scenarios and local checks.
An inconclusive or worse retest restores the previous workflow. Calls with no
assistant speech or no completed judgment remain inconclusive, not policy
failures or passes. These internal checks are not the official hidden score.
The full conversation evidence is retained in the run. Both public-practice and
folder-mode automatic repair receive
a bounded projection of speech, tool outcomes, routing and validation errors;
repeated code and large snapshots are omitted, with any truncation recorded.
The trace explicitly records when the remaining time is insufficient to test;
use a longer `--max-seconds` budget when appropriate before the event deadline.
Remote gateway/connection failures during these checks are recorded as
inconclusive, and an already validated workflow is still exported. An opening
outage skips the larger simulation. No policy repair is based on that outage;
workflow validation and authentication errors still fail normally.
Document evaluations have a separate deadline that reserves time for restoring
the previous workflow and exporting it. A timed-out simulation retains its ID
in the trace; do not start another simulation until its state is resolved.
Repeated customer fixtures run in separate sequential batches; each batch can
run up to three distinct fixtures concurrently. All original scenarios, criteria,
results and simulation IDs are preserved across those batches.

Malformed compiler JSON can be recovered with `--resume-compile <failed-run>`.
The builder verifies the original input hashes, exact prompt, artifact manifest
and full model session before importing the unchanged evidence. Syntax repairs
are bounded and cannot change string tokens or literal values.

For measured runtime failures, `--refine-run <completed-run>
--repair-feedback <evidence.json>` imports an immutable completed run and asks
the model to repair its generated artifact. The prior model sessions and new
repair session are retained together. All existing local checks, smoke checks
and customer scenarios remain fixed. No generated agent is edited by hand.

For a cold rebuild from only the released case folder, use
`python3 builder/build.py {case_folder} {mock_url} --max-seconds 5400`.
This 90-minute ceiling accommodates compilation, independent audit and live
evaluation. It is different from the shorter incremental refinement budget:
the final refinement imports the verified completed v2 run and uses its original
sessions together with the new live-failure evidence. The actual invocation and
deadline are recorded in that run's trace. A cold rebuild may produce a different
valid workflow because it invokes the models again.

## Local validation

```sh
python3 -m unittest discover -s tests -v
```

No API keys are needed for validator tests. The checked invariants include bank
endpoint restrictions, request schema consistency, safe code imports, usable
passthrough routes, and expected effects of local hook checks.

## Final submission — updated event format

The official page changed on 11 October: one Turkish case, one exported workflow,
one builder trace, and a bank-service mock hosted on Cloudflare Workers. The case
opens at 17:00 UTC / 20:00 Istanbul; submission closes at 20:00 UTC / 23:00 Istanbul.
The mock must remain available until results are announced.

1. Read the released `BRIEF.md` and `README.md`. Implement and test the mock from
   its service contract and synthetic customer records; deploy it first.
2. Run the generic builder on the unedited case folder and mock URL. Never write
   final-case rules into builder source or edit the generated phone agent.
3. Commit the frozen source, final workflow export and complete trace directory.
   Each compiler call archives its own complete Codex session, with credentials
   redacted. `full-session.jsonl` combines those records and all build milestones
   into the required single trace attachment. The summary `trace.jsonl` alone
   is not the final session attachment.
   The completed build records hashes of every trace artifact, the builder,
   the platform client/reference documents, and the input files. The packager
   rejects changed or missing artifacts and requires the source, export and
   complete trace to match the bytes in HEAD. Older runs without the manifest
   must be rebuilt for final submission.
4. Produce the current single-case form for review:

```sh
python3 builder/package_submission.py --team cagrikumas \
  --repo https://github.com/cagrikumas/freya-build-the-builder \
  --final traces/COMPLETED-final \
  --mock-url https://freya-bank-mock-cagrikumas.freya-hackathon-bank-mock.workers.dev \
  --commit-ref final-submission-20261011 \
  --name 'Your Name' --email 'you@example.com' > private/submission.json
```

After review, commit the exact manifest as `submission/submission.json`, create
the named immutable tag at that commit, and push the commit and tag. Verify all
three committed attachments with:

```sh
python3 builder/package_submission.py --verify submission/submission.json
```

The Submit page updated at 17:00 UTC requires an email to
`yavuz@freyavoice.ai` before the deadline with three attachments: the reviewed
`submission.json`, exported workflow, and full coding-agent session trace.
It also requires those same files in the repository at the named commit.
The manifest above is initially private for review; its final repository reference
and organiser clone access must be settled before submission. Repository access and final email delivery are handled separately after
reviewing the exact submission artifacts.


## Selected event submission

The selected completed run is `traces/20261011T193910Z-final` (workflow v4).
It passed 94 local checks, platform validation, the opening check and two live
HTTP warning/error scenarios. These are internal tests, not the hidden score.
See `results/20261011-final-tests.md` and raw results for broader measured
performance and remaining limitations. The later v5 refinement timed out
before producing or applying a patch; its failed trace is retained as evidence
and is not the submitted trace. The exported v4 phone agent was not hand-edited.

The final live priority group completed with 11/12 passes and one failure,
with no inconclusive grades. The remaining failure concerns a corrected-card
PDF request. Raw results and earlier failures remain in the repository.
