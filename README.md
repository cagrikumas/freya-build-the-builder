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

The model only returns compilation artifacts. The Python program owns validation,
publication and testing. A second compilation call audits the candidate against
the input policy. Public practice failures can trigger an automatic repair and
retest, within the same deadline. A measured regression restores the earlier
candidate. Phone agents use the unmodified model from the supplied
`freya.py`; only the builder uses Codex.

Folder builds can run a one-turn opening check using a synthetic customer from
the documents, then end the chat. Empty speech, unresolved placeholders and
missing required opening phrases fail it. One automatic repair is allowed;
the original smoke check cannot be weakened. This is a startup check, not a
claim of passing the hidden policy evaluation.

When the case supplies example conversations and usable test customers, the
compiler also derives simulated-customer scenarios and independent success
criteria from those documents. The builder runs them with the event's fixed
phone model, saves the conversations and can automatically repair observed
failures. The repair must preserve the original scenarios and local checks.
An inconclusive or worse retest restores the previous workflow. Calls with no
assistant speech or no completed judgment remain inconclusive, not policy
failures or passes. These internal checks are not the official hidden score.
The trace explicitly records when the remaining time is insufficient to test;
use a longer `--max-seconds` budget when appropriate before the event deadline.

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
4. Produce the current single-case form (keep it outside tracked files):

```sh
python3 builder/package_submission.py --team cagrikumas \
  --repo https://github.com/cagrikumas/freya-build-the-builder \
  --final traces/COMPLETED-final \
  --mock-url https://your-mock.your-subdomain.workers.dev \
  --name 'Your Name' --email 'you@example.com' > private/submission.json
```

Send the reviewed form to the event address before the deadline. The repository
remains private during preparation; organiser clone access must be settled before
submission. No final agent or submission has been sent.
