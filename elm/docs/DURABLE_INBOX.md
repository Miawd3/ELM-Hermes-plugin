> Current release document. Run command examples from the installed `elm/` directory. The release README and CAPABILITIES.md define the product-wide contract.

# Durable quarantined-span inbox

2026-11-06. Additive isolated candidate, synthetic qualification only. No live deployment, model call, external transmission, or real user data was used. The installed directory is `elm/`.

## Delivered change

The earlier `BatchExtraction` API remains process-local and unchanged. The new `DurableCandidateInbox` persists its own bounded pending and validated batches in the existing profile-scoped episode database. It reuses the same strict JSON and exact-span validation, but replaces the process-local batch registry with transactional durable state. It is deliberately a **review inbox**, not a canonical-memory queue.

The inbox itself has no accept, submit, ratify, or confidence-to-truth action. A separate opt-in operator review bridge can submit a manually interpreted, digest-confirmed pending proposal; see OPERATOR_REVIEW_BRIDGE.md. It does not call the existing marker proposal dispatcher. It is not registered as a provider/model tool. Existing deterministic marker proposals are a separate inherited workflow; their earlier submission/inspection behavior is not changed by this inbox.

A citation proves only that an exact Unicode-code-point slice matches the current stored scrubbed source. It cannot prove semantic entailment, attribution, speaker authentication, event-time validity, truth, or permission to act. Negation, quotation, hypotheticals, instructions, and prompt injections can contain matching substrings. All candidates remain `quarantined_candidate`, with truth, attribution, and entailment `not_evaluated`, and acceptance/authorization false. Full selected messages are reconstructed for contextual review; surrounding conversation is not promised complete.

## Explicit opt-in

Capture, explicit recall, and offline batch extraction must already be enabled for the same profile/root/project and batch author. Add this separate profile-local configuration only through a trusted operator:

```json
{
  "format_version": 1,
  "enabled": true,
  "root_id": "<current pinned root ID>",
  "project": "<current pinned project>",
  "author_id": "<same caller-recorded user author as batch extraction>"
}
```

File: `elm_candidate_inbox.json`. The API and CLI do not enable settings, create a profile, adopt a root, or create an episode database. Opening an enabled handle does not create inbox tables. The first successful preparation creates one optional table in the already existing scoped episode database. Configuration/root/scope must remain valid; configuration bytes for capture, recall, batch, and inbox are pinned per durable record.

Enabling local storage is not authorization to send sources to a model or any service. No model adapter or transport is supplied.

## Durable API

```python
from elm_plugin.candidate_inbox import DurableCandidateInbox, CandidateInboxControl

inbox, reason = DurableCandidateInbox.from_recall(existing_explicit_recall)
request = inbox.prepare([verified_source_locator], request_key="operator-job-001")
# Supply a manually prepared bounded JSON response. No model call happens here.
result = inbox.validate(request["batch_id"], supplied_json_text)
inventory = inbox.list_batches()
review = inbox.review(request["batch_id"])
inbox.close()  # Closes this handle; committed durable rows remain.

# A fresh process/handle can list, review and replay the same committed batch.
# Explicit local revocation also works after capture/recall/batch/inbox opt-out:
CandidateInboxControl(explicit_profile_home, pinned_binding).revoke(batch_id)
CandidateInboxControl(explicit_profile_home, pinned_binding).revoke()  # All batches.
```

The unchanged batch response format is `ELM-BATCH-EXTRACTION/1`; its source aliases and strict fields are described in `BATCH_EXTRACTION_CONTRACT.md`. All source IDs, offsets, exact quotations, kinds/topics/interpretations, unknown fields, duplicate keys, JSON depth and byte bounds are checked with the inherited validator. Labels remain unverified source-derived data.

A request key is a 1–128-character ASCII operational identifier matching `[A-Za-z0-9_.-]+`; avoid putting private text into it. The database stores a scoped hash, not the plain key. Hashing is not anonymization.

- Identical key and ordered locator list return the same request/batch ID while sources/configuration remain live.
- Reusing a key with a different source list is refused.
- Successful identical raw response bytes replay the same candidate IDs, with current evidence revalidation. Whitespace-only response changes are also refused.
- Invalid attempts persist across restarts. Three attempts exhaust a batch; no repair/model retry occurs.
- Failed, revoked, and validated records all consume the lifetime capacity. There is no eviction or key-recycling API.
- `close` does not revoke durable records. Use `revoke`/`revoke-all` when withdrawal is intended.

## Operator CLI

`review_candidates.py` is separate from the existing strictly read-only marker inspector. This new workflow may **write revocation/expiry tombstones while reading**. It does not initialize missing profiles/stores or mutate canonical/governance data.

All commands require explicit scope:

```sh
python -B review_candidates.py \
  --hermes-home /absolute/disposable/profile \
  --root-id root_... --project orion list
```

Replace `list` with:

- `prepare --locator <verified locator> --request-key operator-job-001 --include-source-text`
- `validate --batch-id <batch ID> --include-source-text` with manually supplied response JSON on stdin
- `review --batch-id <batch ID> --include-source-text`
- `revoke --batch-id <batch ID> --confirm-revoke`
- `revoke-all --confirm-revoke`

The source-text flag is mandatory for prepare/validate/review because their output contains complete selected source messages and quotations. List is a content-free batch inventory; it does not show topics, locators, authors, or source bodies. Sources are still revalidated. Error JSON does not echo response bodies or database text. There is no inbox `accept` or direct `submit` command. The separate operator bridge has `operator-submit` and `operator-reconcile`; see OPERATOR_REVIEW_BRIDGE.md.

The pre-existing `inspect_episodes.py candidates` remains the deterministic marker proposal inspector. It does not include this inbox. Its old process-local limitation applies to the unchanged `BatchExtraction`, not the new durable API.

## Storage and concurrency

The optional `span_candidate_inbox` table lives alongside captured evidence so source deletion and candidate scrubbing can share one SQLite transaction. Rows persist only:

- IDs and scoped request-key hashes;
- state, bounded attempt count, created/expiry timestamps;
- source locators and a complete selected-source manifest fingerprint;
- a configuration pin and successful raw-response digest;
- source aliases, integer offsets, and unverified kind/topic/interpretation labels;
- an unkeyed record-integrity digest.

No source text, quote, full request, raw response, accepted fact, or canonical payload is copied into the inbox. Labels are still source-derived information and are scrubbed on revocation. Selected source messages/quotes are rebuilt from live capture evidence every time.

`BEGIN IMMEDIATE`, unique request-key hashes, and `synchronous=FULL` serialize preparation, validation, source forgetting, and capture expiry on the same database. No external action occurs inside these transactions. A crash before commit rolls back; a crash after commit can replay stable IDs. Database busy errors are surfaced rather than automatically retried. This is scoped durable idempotence, not global exactly-once processing or a guarantee against database replacement/restoration.

Unkeyed digests detect inconsistency, not hostile local database ownership. A process able to rewrite all rows/hashes, replace files, restore backups, or change the code is outside the integrity boundary. Every actual disclosure still checks exact current source identity/content/metadata through the inherited recall path.

## Revocation, retention, and forgetting

Records expire at the earlier of the earliest selected source-pair expiry and 24 hours after preparation. Source/configuration checks occur before disclosure and at its final boundary. Missing/deleted paired evidence, expiry, source changes, author/scope mismatch, changed configuration pins, or backward clock movement before creation prevent candidate disclosure. Active inbox operations durably revoke rows upon observed source/configuration invalidation; restoring the old bytes afterward does not revive those revoked rows.

Observed inbox/batch opt-out through `from_recall`, or capture/recall opt-out through the CLI, revokes existing rows without enabling anything. Existing handles also revoke on observed configuration withdrawal. `CandidateInboxControl` provides explicit revocation when all opt-ins have been removed. If no operation runs while settings are temporarily removed and their exact bytes are later restored, that unobserved history cannot be inferred. For a durable withdrawal boundary, run `revoke-all`; no background watcher is supplied. Passing `None` instead of recall has no profile identity and cannot revoke an unknown profile. Other constructor failures, such as malformed configuration, do not by themselves establish a durable withdrawal; use `CandidateInboxControl.revoke()` with a valid pinned binding when cleanup is needed without constructing an enabled inbox.

Capture expiry scrubs expired inbox rows in the same transaction as source cleanup. `EpisodeForget.preview` includes all related inbox state in its plan digest; validation or another inbox change makes an old preview stale. `apply` revokes the whole batch if any selected source is in the paired-UID forgetting closure, and scrubs every label/locator/fingerprint/response digest in that batch atomically with source deletion. Unrelated batches remain available. A forgotten source cannot be resurrected by a late response, replayed key, or persisted selection copy.

If an inbox record is corrupt, normal reads fail closed. Optional derivative corruption must not block source expiry, explicit forgetting, or revocation: those cleanup paths scrub the unusable inbox and create a permanent whole-inbox blocked marker. There is no reset/re-enable API for that marker. Corrupt forgetting preview is read-only and explicitly reports the wider whole-inbox cleanup; apply requires the corresponding unchanged plan. This fallback sacrifices the unusable inbox to preserve source retention/deletion guarantees. Physical SQLite corruption preventing any write is not repairable by this contract.

Logical revocation retains minimal replay tombstones. This is not secure erasure: SQLite remnants/journals, backups, host transcripts, canonical records, caller caches, displayed outputs, saved files, or model contexts are not erased. Already returned copies cannot be recalled. The result is a point-in-time disclosure, not a lease authorizing future action. System clock integrity and malicious local file replacement remain outside the guarantee.

## Bounds

Inherited source/request/response/result bounds remain: 1–8 selected sources, each at most 8,192 stored UTF-8 bytes; whole request and response 32,768 bytes; result 65,536 bytes; 32 candidates; 1,024 Unicode code points per quote; JSON depth 8; 3 attempts. The durable lifetime registry is 128 records per profile scope including tombstones, not 8 process-local records. Retention is capped at 24 hours and source-pair expiry, whichever is earlier. The database does not retain source text in this table, but existing capture sources have their own independent bounds.

## Verification and remaining work

`test_candidate_inbox.py` covers restart, retry persistence, concurrent replay/conflicts, fabricated/tampered source/selection data, source deletion, opt-out/revocation, expiry, stale forgetting plans, and no canonical writes. `audit/test_inbox_independent.py` independently tests adversarial boundaries and the two review findings repaired in this revision. `native_candidate_inbox.py` runs actual stock-provider capture and CLI operations in fresh processes, including abrupt exits before and after commit, eight racing CLI preparations, restart review, forgetting, and opt-out revocation. The inherited suite is included under tests/regression/ with source-path adaptations; its safety assertions remain in place. The release additionally tests new setup and default recall behavior.

See root VALIDATION.md and the separate release evidence for exact counts, hashes, exits and native evidence. No semantic-model accuracy, extraction recall/precision, speaker authentication, remote transport security, graphical human approval UX, production readiness, or universal prompt-injection immunity is claimed. A separate opt-in operator interpretation-to-pending-governance bridge exists now; see OPERATOR_REVIEW_BRIDGE.md. No actual model adapter is included.
