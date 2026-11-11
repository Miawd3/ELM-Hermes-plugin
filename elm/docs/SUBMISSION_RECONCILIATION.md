> Current release document. Run command examples from the installed `elm/` directory. The release README and CAPABILITIES.md define the product-wide contract.

# Conservative uncertain-submission reconciliation

This isolated successor adds `operator-reconcile` to the existing opt-in operator review bridge. It can prove that an exact persisted submission reached canonical governance after a lost response. It never sends a proposal, retries a dispatch, accepts a claim, performs canonical recovery, or changes canonical records. Only the local review outcome can change.

## Use

After an uncertain `operator-submit`, keep the original review ID and plan digest. Run:

```sh
python -B review_candidates.py \
  --hermes-home /absolute/isolated/profile --root-id root_<uuid> --project orion \
  operator-reconcile --review-id review_<uuid> --plan-sha256 <original-sha256>
```

API: `bridge.reconcile(review_id, expected_plan)`. It is an explicit operator operation, not a registered provider/model tool. It requires all existing opt-ins, the original profile/root/project binding, an unchanged live source and full review payload, and an original `submitting`, `unknown`, or `submitted` row. It cannot promote `prepared` to `submitted` merely because an unrelated canonical record exists. No new confirmation grants permission to retry.

The output is content-free: IDs, digests, state, and status observations only. It includes `submission_performed=false`, `acceptance_performed=false`, and `retry_permitted=false`.

## Outcomes

| Classification | Meaning | Local effect |
| --- | --- | --- |
| `matched` | Exactly one canonical v2 proposal has the persisted project/submission ID and verified normalized payload digest. | `submitting` or `unknown` becomes `submitted`. Already submitted stays submitted. |
| `absent_uncertain` | No matching ID was visible in a coherent canonical snapshot. | No state change. Uncertain outcomes remain blocked. |
| `conflict` | The ID was retired, or a visible proposal has another payload/version. | No state change. No resend or correction is inferred. |
| `unverifiable` | A terminal proposal exists, but deleted evidence prevents full payload verification. | No state change. |
| `unavailable` | Lock, identity, journal, or canonical integrity prevents an authoritative observation. | No state change. |

A duplicate/corrupt canonical identity fails the engine's complete canonical validation and is `unavailable`, not absence. Malformed, misbound, timed-out or failed reader responses raise a content-free refusal and preserve local uncertainty.

For already-submitted reviews, subsequent conflict/absence does not erase the historical fact that submission was recorded. The returned classification remains explicit. Ordinary `operator-list` and replay receipts remain historical and do not refresh governance status.

## Why a positive match is defensible

1. The episode database transaction serializes reconciliation with supported submission, forgetting, and revocation, using the same lock order as submit.
2. Existing live-plan validation checks persisted row integrity, exact generated payload, source context, expiry and configuration pin. The supplied plan digest must match.
3. A pinned source-only subprocess runs with isolated Python and the unchanged engine normalizer. Its response is bound to the full request by a checked request hash. This is consistency protection, not authentication against a hostile local administrator.
4. The helper acquires the engine's canonical writer lock with stale-lock recovery disabled. Root ID and root identity hash are checked inside that lock.
5. Every remaining governance transaction journal causes refusal, including a committed journal awaiting cleanup. A prepared transaction may contain apparently complete proposal files that later roll back. Reconciliation never repairs or recovers those journals.
6. The helper reads and validates canonical governance JSON and lifecycle events directly. It never queries, creates, syncs, rebuilds or trusts the disposable SQLite projection.
7. The original payload is normalized with the engine's v2 submission digest domain. Project and submission ID must agree with the retained local identity. Retirement tombstones are checked first. A match requires the canonical payload digest to be independently verified from its evidence and exactly equal to the original normalized payload digest.
8. Only this positive proof records historical submission locally. No branch invokes submission, acceptance or canonical mutation. The temporary writer lock is the only canonical-root coordination write.

The snapshot is coherent at one point under the writer lock, not a promise that governance remains unchanged after return. Another operator may later reject, accept, delete or otherwise change records. Submission proof remains historical. `observed_canonical_status` describes the visible proposal's lifecycle and may also accompany a payload conflict or unverifiable evidence. It alone is not proof of a matching payload. `acceptance_observed_in_governance=true` requires both `classification=matched` and observed status `accepted`. Neither field establishes a current live accepted claim, truth, source identity, or authorization. `accepted_memory` remains false and the bridge performs no acceptance.

## Deliberately unresolved cases and architectural blockers

**Absence cannot prove non-execution.** An original dispatcher might still be paused before acquiring the canonical lock. A timeout or missing row cannot fence that worker. This version has no engine-enforced operation cancellation/fencing contract, so absent outcomes never become safe to resend. A later exact match may resolve them. Do not change IDs, reset tombstones, recreate a profile, or manually mark prepared as a recovery shortcut.

**Scrubbed reviews cannot prove payload equality.** Existing tombstones retain submission/review IDs and a plan hash, but not an independently comparable canonical normalized payload commitment. Revoked, expired, configuration-changed or source-changed reviews therefore remain blocked. Reconciliation does not restore forgotten text or match by ID alone. Broad post-forgetting reconciliation would require a separately reviewed, privacy-conscious durable commitment and migration design; it is not implemented here.

A canonical retirement tombstone records replay identity without full payload proof. Evidence deletion can similarly prevent full equivalence proof. Those are not classified as safe matches. A busy/stale lock or unfinished journal requires normal independent governance inspection/recovery by its operator. This feature does not unlock or recover automatically.

## Verification and non-goals

All examples and test stores are synthetic. No live/canonical deployment, model call, external transmission, or production readiness claim. The reconciliation implementation leaves canonical engine behavior unchanged. This release separately changes the provider default to explicit-only canonical recall, as described in the release README. Existing source/authentication, meaning, exact-quote and forgetting limitations still apply.

`test_submission_reconciliation.py` tests new developer cases. Independent adversarial cases are in `audit/reconciliation_safety/`. `native_reconciliation.py` runs fresh stock-Hermes processes across real abrupt exits before dispatch, after canonical commit, and before local reconciliation persistence. See ../VALIDATION.md for commands and the separate release evidence archive for final results.
