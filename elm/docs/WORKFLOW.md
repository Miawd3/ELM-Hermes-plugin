# Guided profile workflow

Run commands from the installed `elm/` directory. No command here calls a model. These dependency-free examples explicitly select legacy estimates; for the new measured default, replace `--budget-mode legacy-estimate` with explicit tokenizer and local vocabulary settings from [measured budgeting](MEASURED_TOKEN_BUDGET.md). Use explicit disposable paths for first qualification; do not point a demo at a live store.

## Minimal retrieval

```sh
python -B setup_profile.py new --budget-mode legacy-estimate --hermes-home /absolute/demo/profile \
  --root /absolute/demo/store --project orion
```

These examples: `mode=read-only`, `recall_mode=explicit-only`, explicit legacy budget 700 estimated tokens, all optional capture/review flags off. `adopt` uses an existing healthy identified/current store and requires the selected project hub. Both guided flows refuse any existing ELM settings and leave Hermes provider selection unchanged. They validate path overlap, symlinks and optional dependencies before creating data.

Setup prints the exact profile-bound POSIX selection command and next steps. Review it, select `elm` in that same Hermes profile, then start a new conversation. On Windows use the equivalent environment-variable syntax for your shell rather than pasting a POSIX assignment.

Guided setup publishes the binding last and never replaces configuration files. Failures preserve partial files/store for inspection instead of deleting data. A partial setup cannot be blindly replayed over those files. Inspect the error and explicit paths. A crash-held `.elm-setup.lock` needs deliberate operator inspection. This is not a transactional rollback or malicious-filesystem defense.

The older `manage.py init/adopt` and native provider setup are explicit configuration replacement/re-adoption APIs; they do not share the guided command's no-overwrite guarantee. Use them deliberately only after reviewing the current binding and optional configuration. All changes need a fresh provider instance/new conversation.

## Opt in to captured evidence only

```sh
python -B setup_profile.py new --budget-mode legacy-estimate --hermes-home /absolute/demo/evidence-profile \
  --root /absolute/demo/evidence-store --project orion \
  --capture --episode-recall
```

Capture's default retention is 259200 seconds (3 days), checked during operations, not by a background deletion daemon. Capture is bounded and attempts pattern scrubbing, not comprehensive DLP. Read-only canonical mode does not turn capture off. Episode recall requires capture and a budget of at least 256. Pinned root/project IDs are filled automatically.

## Optional durable manual review

```sh
python -B setup_profile.py new --budget-mode legacy-estimate --hermes-home /absolute/demo/review-profile \
  --root /absolute/demo/review-store --project orion --mode proposal-only \
  --capture --episode-recall --batch-extraction --inbox --review-bridge \
  --author-id synthetic_human --operator-id synthetic_operator
```

This enables a local manual pipeline, not extraction by a model. Supply a bounded exact-span response locally, then an explicit interpretation and digest-bound submit confirmation. Source author/operator IDs are caller observations, not authenticated identities. See [span validation](BATCH_EXTRACTION_CONTRACT.md), [durable quarantine](DURABLE_INBOX.md), [operator review](OPERATOR_REVIEW_BRIDGE.md), and [reconciliation](SUBMISSION_RECONCILIATION.md).

Opt-ins do not enable dependencies implicitly. `--batch-extraction` needs `--episode-recall`; `--inbox` needs `--batch-extraction`; `--review-bridge` needs `--inbox` plus operator ID and a write-capable binding. A missing dependency refuses setup before writes.

## Optional marker proposals

Add `--marker-proposals --author-id synthetic_human` to a capture-enabled setup and explicitly choose `--mode proposal-only` (or autonomous). Guided setup refuses marker proposals in read-only mode to avoid a staging-only configuration surprise. The lower-level API does support read-only staging, without submission; see detailed capture tests.

Only exact single-line markers such as `Preference: answer_style = concise` are eligible. Ordinary sentences are not automatically extracted. Unknown author, assistant text, quoted/fenced/redacted markers and multiline instructions are refused. Eligible markers seal and can be submitted as **pending** governance proposals on lifecycle hooks before an operator inspects them. If governance submission must wait for manual review, do not enable marker proposals; use the separate manual bridge.

## Inspect and forget

```sh
python -B inspect_episodes.py --hermes-home /absolute/demo/profile \
  --root-id root_UUID_FROM_SETUP --project orion status
python -B inspect_episodes.py --hermes-home /absolute/demo/profile \
  --root-id root_UUID_FROM_SETUP --project orion candidates
python -B manage.py episode-forget-preview --hermes-home /absolute/demo/profile \
  --locator EXACT_SCOPED_EPISODE_LOCATOR
python -B manage.py episode-forget --hermes-home /absolute/demo/profile \
  --locator EXACT_SCOPED_EPISODE_LOCATOR --confirm-plan REVIEWED_PLAN_SHA256
```

Review the preview before applying. Changed state invalidates the digest. Local paired evidence and associated derivatives are scrubbed; canonical proposals, accepted claims, host transcripts, backups, SQLite remnants and already returned copies remain outside this boundary. Replay tombstones remain. See [operator inspection](OPERATOR_INSPECTION.md) and SECURITY.md at plugin root.

To withdraw durable inbox/review data, use their explicit revoke commands. Unobserved temporary config changes cannot be detected; opt-out alone is not evidence that durable rows were scrubbed. Unknown submission outcomes remain blocked across revocation, expiry and restart. Do not delete tombstones, change IDs or reset profiles as a retry mechanism.
