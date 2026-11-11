> Current release document. Run command examples from the installed `elm/` directory. The release README and CAPABILITIES.md define the product-wide contract.

# Explicit operator review bridge

This isolated experimental successor adds an **opt-in, operator-only** path from a quarantined exact span to an existing ELM **pending governance proposal**. A quote is evidence, not meaning. The bridge never derives a claim from extractor labels, accepts memory, supersedes claims, authenticates speakers, or invokes a model or external service.

## Two different review boundaries

1. Inbox validation proves that selected characters match current stored scrubbed source bytes. It does not prove attribution, entailment, intent, truth, or authorization. The candidate stays quarantined even if its labels say “assertion” or “preference.”
2. The operator must supply all eight semantic fields below, inspect the current full selected source messages and exact generated payload, then explicitly confirm that review's digest. Only that second action calls the pinned local engine's existing `proposal-submit`. Existing governance determines later acceptance or rejection separately. The bridge has no acceptance command.

The review is a durable interpretation, **not a verification of that interpretation**. A malicious or mistaken local operator can still write a false meaning. No NLP entailment evaluator or operator authentication is claimed.

## Explicit configuration

All existing capture, recall, batch extraction and durable inbox opt-ins must remain enabled and correctly scoped. The profile binding must be `proposal-only` or `autonomous`; even in autonomous mode this bridge only uses `proposal-submit`, never `remember-submit` or acceptance.

Add `elm_operator_review.json` to the isolated profile only when the operator intends to enable this path:

```json
{"format_version":1,"enabled":true,"root_id":"<exact pinned root ID>","project":"orion","operator_id":"local_operator"}
```

The operator identifier records an assertion by the trusted local caller, not an authenticated person. It is created only by an explicit operator choice, including guided setup with --review-bridge. Opening an enabled bridge creates no new tables. Missing/disabled bridge configuration observed by its constructor revokes existing interpretations. Whole-file digests pin all relevant configurations, the profile/root/project binding, extractor author and review operator.

## Local CLI workflow

Invoke `review_candidates.py` with an explicit absolute `--hermes-home`, exact `--root-id` and `--project`. Use the existing `prepare`, `validate`, and `review` operations to obtain a validated batch and candidate ID first. Those operations still cannot submit.

Supply the following **complete operator-authored object** on stdin to `operator-prepare --batch-id BATCH --candidate-id CANDIDATE --request-key REVIEW_KEY --include-source-text`:

```json
{
  "subject": "speaker:synthetic_human",
  "predicate": "preference.color",
  "object": "does not prefer red",
  "scope": "project:orion",
  "valid_from": "2026-11-06T00:00:00Z",
  "context": "The full message negates the selected words. A later occurrence is quoted speech.",
  "attribution": "Caller-observed sender only; source identity is not independently authenticated.",
  "uncertainty": "This interpretation may describe one situation rather than an enduring preference."
}
```

No field defaults from a quote, label, capture date or inferred author. Fields must be nonempty, bounded single-line strings; scope must exactly equal `project:<bound project>`, and valid_from must be an explicit timezone-aware ISO timestamp. The timestamp is an operator assertion, not established event validity. Unknown/extra fields, including authority and acceptance fields, are refused.

The returned review includes `review_id`, `plan_sha256`, `operator_semantics`, `proposal_payload`, and live full source context. A selected `prefer red` can appear inside `I do not prefer red`; the example supplies a negated interpretation instead of laundering the excerpt into a positive preference.

- `operator-inspect --review-id REVIEW --include-source-text`: revalidate and display the exact durable plan plus current source context.
- `operator-list`: revalidate reviews and return a content-free outcome inventory.
- `operator-submit --review-id REVIEW --plan-sha256 DIGEST --confirm-reviewed-meaning-scope-and-context`: explicitly confirm the reviewed meaning, scope and context and submit the fixed payload to local governance.
- `operator-revoke --review-id REVIEW --confirm-revoke`, or `operator-revoke-all --confirm-revoke`: scrub local interpretations even after opt-out. These do not delete pending governance proposals or accepted claims.

The prepare/inspect commands disclose source and operator text only with the explicit source-text flag. Submit and list return content-free receipts. Do not save CLI output into uncontrolled logs: already returned copies are outside local forgetting.

## Durability, duplicates, correction, and uncertainty

- A request key is scope-bound and stored only as a hash. Repeating the same prepare request across processes returns the same review/submission ID. Changing meaning, source or correction target under that key is refused. Revoked keys and IDs cannot be reused.
- The digest binds the full supplied semantics, exact pending payload, source fingerprint/validated response, configuration pin, review/candidate IDs, expiry, and correction target. A digest from another plan does not authorize this one. Confirmation must be the literal boolean true in the API or the explicit CLI flag.
- Before dispatch, the bridge commits `submitting` durably. It then reacquires the source database write lock, revalidates everything, and holds that lock across the local engine call. Source forgetting/revocation cannot interleave with that guarded call.
- A successful replay returns the recorded submission receipt without another engine call. This receipt is historical, not a fresh query of current governance status; `current_canonical_status` is `not_inspected`. Another operator may subsequently accept/reject/defer the proposal outside this bridge. The bridge itself performs no acceptance.
- A crash after intent but before dispatch, after a canonical commit but before local outcome persistence, an exception, or an unconfirmed result stays `submitting`/`unknown`. No automatic or explicit blind resend occurs. Other new submissions and new review admission are blocked by unresolved outcomes; revocation preserves `revoked_unknown` and does not clear that block.
- **This successor adds conservative `operator-reconcile`.** An exact authoritative canonical payload match can record historical submission without resending. Absence, conflict, retired IDs, unavailable state and missing payload proof stay blocked. See **SUBMISSION_RECONCILIATION.md** for the command, proof boundaries and deliberately unresolved cases. Do not reset local tombstones, recreate a profile, or choose a new ID as a purported safe retry.
- To correct a still-unsubmitted interpretation of the same candidate, use a new key and `--replaces-review-id OLD`. The old local draft is atomically revoked, the new plan gets a new digest, and fresh confirmation is required. Source meaning is not edited in place.
- To correct an already-submitted interpretation, explicitly revoke its local review and prepare a new independent interpretation with a new key and confirmation. The old canonical proposal **remains**. Review both records in existing governance; this bridge performs no canonical correction, deletion, rejection or supersession.
- There is deliberately no deduplication of equal meaning under unrelated new keys. Operators must not treat a new key as an uncertain-outcome recovery mechanism.

## Withdrawal and forgetting scope

Inbox revocation, observed source/configuration withdrawal, source expiry, and linked-pair forgetting scrub dependent local review semantics and generated payloads. The reviewed forgetting digest includes dependent review state, so adding a review or recording an outcome after preview invalidates that old preview. Source forgetting reports dependent review count/submission IDs and whether a canonical outcome needs separate review.

Local replay tombstones retain review/submission IDs, request/plan hashes, timestamps, outcome state, and correction ID. Existing source replay metadata is also retained. Expiry and forgetting remove usable text through normal SQL; this is not secure erasure. Optional review corruption does not block source cleanup: cleanup removes unreadable review derivatives and installs a permanent whole-bridge blocked marker, preserving uncertainty rather than trusting corrupt state.

**Not complete deletion:** canonical governance proposals and accepted claims, host transcripts, logs, backups, prior returned objects/exports, old SQLite pages, and unknown external derivatives are not erased. Existing governance is a separate scope. Source identity and content hashes are not authentication. A hostile filesystem/database owner can recompute unkeyed digests or replace the whole store. A temporary config edit restored entirely between observations cannot be detected. In-flight canonical effects cannot be retroactively prevented.

## Bounds and delivery status

128 lifetime review rows per profile, including tombstones. Review lifetime cannot exceed its source inbox batch or 24 hours. Payload sensitivity is fixed to restricted. Only the local pinned engine receives an explicitly confirmed payload. The bridge adds no provider/model schemas and does not change canonical engine code. The release separately adds an explicit-only recall configuration default. All qualification data are synthetic. This archive was not installed into a live profile and makes no production-readiness claim.
