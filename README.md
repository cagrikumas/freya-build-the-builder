# Build the Builder — Codex compiler

A bank brief and its OpenAPI document go in. A Freya phone workflow, local checks,
test results and a timestamped build trace come out. All bank-specific policy is
derived during the build from the input documents.

## Requirements

- Python 3.10 or newer (standard library only).
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
python3 builder/build.py path/to/bank.md path/to/bank.openapi.json
```

The default slot is the brief filename without its extension. Repeating a build
updates and publishes the same workflow. The builder records model calls,
validations, timestamps, workflow/agent IDs, and exports the saved workflow into
`submission/<slot>.workflow.json`. Each run has its own `traces/<timestamp>-<slot>/`.
The run has a 29-minute deadline, within the event's 30-minute limit.

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

Brief B must be supplied with Brief A. The hidden final briefs are each supplied
with their own OpenAPI file. Do not use the public cases for an unrelated brief.
Use the kit's `tools/run_cases.py` for repeated evaluations (`--reps 3`) and styles
(`--style pieces`, `corrects`, `talkative`, `asks_back`, `in_words`). Only one
simulation may run at a time in the workspace.

The model only returns compilation artifacts. The Python program owns validation,
publication and testing. A second compilation call audits the candidate against
the input policy. Public practice failures can trigger an automatic repair and
retest, within the same deadline. A measured regression restores the earlier
candidate. Phone agents use the unmodified model from the supplied
`freya.py`; only the builder uses Codex.

## Local validation

```sh
python3 -m unittest discover -s tests -v
```

No API keys are needed for validator tests. The checked invariants include bank
endpoint restrictions, request schema consistency, safe code imports, usable
passthrough routes, and expected effects of local hook checks.

## Final submission

Commit the source, each final workflow export and the complete trace directories.
Supply the GitHub URL, exact commit, run command, two workflow paths and two trace
paths using the event's submission instructions. Never edit a generated phone
agent by hand. Never put final-brief rules or values into the builder source.

`notes/competition.md` records the official page and timeline read on 11 October.
No final agents have been submitted yet.
