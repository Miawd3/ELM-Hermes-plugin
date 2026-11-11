> Current release document. Run command examples from the installed `elm/` directory. The release README and CAPABILITIES.md define the product-wide contract.

# Local operator inspection prototype

This separate CLI inspects the existing isolated candidate. It is not deployed, is not a model/provider tool, and makes no model or network calls. It does not initialize a store, alter settings, capture a turn, stage or submit a proposal, accept a fact, expire a row, or delete anything.

## Operator workflow

Supply the exact profile home, adopted root ID, and project. The home must already exist and be an absolute non-symlink path. Nothing is inferred from the current directory or a live user profile.

From the installed `elm/` directory:

```sh
python -B inspect_episodes.py --hermes-home /absolute/synthetic/profile \
  --root-id root_12345678-1234-4234-8234-123456789012 --project orion status
```

`status` returns capture settings, retention/size limits, binding mode, recall/batch settings, counts of unexpired/expired stored message rows, and proposal-state counts. Queue-pending, reviewable, and submitted-with-unchecked-governance counts are separate. It never includes message/proposal bodies or the configured author ID. Message counts are physical rows filtered by expiry, not validated claims or a semantic inventory. Disabled capture returns settings-only status without opening evidence storage. Missing storage is reported, never created. This command does not change an opt-in or opt-out setting.

```sh
python -B inspect_episodes.py --hermes-home /absolute/synthetic/profile \
  --root-id root_12345678-1234-4234-8234-123456789012 --project orion \
  candidates --limit 20
```

`candidates` lists active and submitted-unverified durable explicit-marker proposals. This includes queued, blocked, submitting, unknown, revoked-unknown and submitted outcomes. Local submission is not governance resolution: submitted proposals remain visible because their current governance outcome is not checked. `--include-resolved` additionally includes locally revoked and revoked-submitted tombstones; this flag name refers only to local queue history, never accepted truth. Limit is 1–64; total matched and omitted counts are explicit. Each record exposes only a validated candidate ID, scoped source locator, local queue state, bounded citation status and an unverified conflict hint. It does not print payloads, rationale, topics, excerpts or result bodies.

Citation states:

- `live_exact_marker_citation`: stored payload/evidence equals a freshly reconstructed exact marker citation against live, integrity-checked paired evidence. This is not a truth, semantic entailment, or identity claim.
- `stale_or_mismatched_candidate`: source exists but the candidate no longer exactly matches the current source/configuration contract.
- `unavailable_expired_missing_or_unlinked`: current paired evidence cannot support inspection; retained proposal copies are not an alternate source.
- `not_checked_recall_disabled`: candidate metadata only; recall opt-in is absent.
- `revoked_local_evidence`: a local revocation tombstone, not proof that every copy was erased.

```sh
python -B inspect_episodes.py --hermes-home /absolute/synthetic/profile \
  --root-id root_12345678-1234-4234-8234-123456789012 --project orion \
  evidence --locator 'elm-episode://<scope>/<episode-id>/<message-id>'
```

`evidence` returns metadata for one exact scoped source. It requires capture and recall to remain enabled. Add `--include-source-text` only when the operator wants the stored scrubbed text displayed locally. It may still contain sensitive information. No text is displayed by default. Sources are integrity-checked as complete current pairs, including the partner row, and revalidated before return. Source expiry at the final observation boundary blocks disclosure.

All results are one JSON object on stdout. Unicode/control/angle-bracket escapes preserve values as inert serialized text. Do not insert decoded fields into HTML, a shell, or a model instruction channel without that consumer's own safe handling. The output does not execute source instructions. Exit 0 means an inspection completed, not that evidence was true or a candidate was accepted. Exit 2 is a sanitized refusal/failure without source contents, filenames or SQL error details.

## Settings and opt-out

The existing files `elm.json`, `elm_episode_capture.json`, `elm_episode_recall.json` and `elm_batch_extraction.json` remain the authority. The inspector validates/pins them but never edits them. Capture must be enabled to inspect queue/source storage. Recall must also be enabled for source metadata/text and live citation checks. Status labels optional settings as settings, not as proof that a running host has loaded them. Existing instances refuse any observed configuration or identity change; start a new command to read the changed state.

This inspector enumerates the durable explicit-marker queue only. The separate process-local BatchExtraction candidates disappear at restart. A separate DurableCandidateInbox now persists span selections; use review_candidates.py for that inventory. This CLI clearly reports that it cannot enumerate them; it does not invent a persistent batch queue. Review those through the existing `BatchExtraction.review` API in the owning process.

## Read-only and disclosure boundaries

The implementation opens existing SQLite storage with `mode=ro`, `query_only`, and a read transaction. It refuses SQLite WAL mode and any `-wal`, `-shm` or `-journal` sidecar before opening. It never attempts recovery/checkpointing. A busy/WAL refusal requires the operator to resolve the writer/storage state outside this CLI; the tool does not change database mode. The CLI disables bytecode generation before package imports, including a plain `python inspect_episodes.py` invocation. Use `python -B` for reproducibility.

Scope is pinned to explicit home/root/project and root-identity hash, with database schema/scope checks. Configs use bounded, duplicate-rejecting JSON. Output is capped at 65,536 serialized UTF-8 bytes; oversized evidence is refused rather than silently truncated. Strict checks fail closed when source or partner integrity fails, even if that damage belongs to another current source in the same scope. No attempt is made to repair or migrate an old store.

These are bounded local checks, not protection against a hostile process with concurrent filesystem replacement privileges. Revalidation is not an atomic lease covering later use. Already displayed or saved snapshots cannot be revoked. Counts are point-in-time observations, not a continuous monitor.

## What this does not prove or erase

- Exact source citation is not truth, entailment, speaker authentication, or authorization. Caller-supplied speaker/timestamp metadata stays unverified. Capture time is not event time.
- `submitted` reports a local queue outcome. It does not prove the canonical store accepted a fact. The inspector does not read or rewrite canonical claim/governance contents.
- Expiry and forgetting do not erase host transcripts, backups, canonical/governance records, SQLite pages or already returned copies. This command performs no deletion at all.
- Pattern-based scrubbing is not a comprehensive sensitive-data detector. Opting in to source text can reveal sensitive contents on the local terminal.
- No model quality, semantic precision/recall, production readiness, or universal prompt-injection immunity is claimed.

## Python API

```python
inspection = EpisodeInspection(home, root_id=expected_root, project=expected_project)
inspection.status()
inspection.candidates(limit=20, include_resolved=False)
inspection.evidence(exact_locator, include_source_text=False)
```

The object is read-only. `clock` is injectable for deterministic tests, not offered as a CLI override. A locator is a scoped identifier, never an authorization token. Programmatic callers should serialize with `episode_recall.encoded` to preserve the CLI's escaping behavior.
