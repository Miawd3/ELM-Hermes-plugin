# Opt-in local conversation capture (r14)

Local capture consent is separate from automatic recall and from any external
model egress. It is disabled by default. This foundation makes no extraction,
embedding, verification, model or network calls and never approves records. It
retains bounded redacted text locally for later human inspection and exact-excerpt
review. It does not provide semantic extraction or declare assistant claims true.

## Native boundary and supported setup

The patched host must expose `local_turn_capture`; ELM must be explicitly selected
as an in-process memory provider. The settings UI neither selects the provider nor
proves every turn will be captured. The hook runs synchronously in the actual
native `finalize_turn`, inside the already authenticated claimed-admission lifetime,
after final-response transforms/surrogate sanitization and successful completion.
It is not legacy `sync_turn`/`sync_all`, which can outlive native authority.

Only successful, completed, nonfailed, noninterrupted, nonpartial primary local
turns are eligible. Vetoed, auxiliary, side-agent, subagent, background/cron/flush,
persistence-disabled, managed-worker, unsupported-author and MoA paths are
excluded. Non-string admitted user inputs and non-text assistant results are
excluded. Attachments are not captured; accompanying string text may be captured. Capture does not need request recall enabled. Unlike r13 model
injection, local final capture does not require a Chat Completions transport or an
explicit model output reserve; it has its own local text-size caps.

The user source is the exact **committed admission text field after native secret
redaction**, not the finalizer's caller-supplied user hint or expanded API prompt.
Only a string is accepted; attachments are not flattened. Assistant text is the
**finalizer-visible response after native secret redaction**, not hidden reasoning,
tool output, `api_content`, system text, delivery confirmation or a claim that
network transport displayed identical bytes. Existing secret redaction is not a
guarantee that all sensitive information is removed; both sources remain sensitive.

The host verifies principal, canonical session, current epoch/generation, serving
state and cancellation. A dedicated synchronous, originating-thread-only finalizer
permit enables capture publication without granting general write authority to
r13's read-only request scope. Core-bound digests of the redacted user and assistant
text plus the actual admission ID/sequence prevent accidental provider-supplied
receipt/text substitution. Copied worker-thread or expired contexts are refused.
This is a trusted in-process plugin contract, not a sandbox against malicious code
or a local filesystem owner. Shutdown waits for an already-admitted bounded local
capture; it does not retract a commit already completed.

## Explicit consent and future admissions

- `private.capture_settings.status {}` returns `enabled`, settings `revision`,
  `max_turns`, `max_utf8_bytes`, this chat's `captured_turns`, nominal
  `remaining_turns`, optional `capacity_reason`, `host_supported`,
  `external_egress:false`, `sensitive:true` and a retention/provenance notice.
- `private.capture_settings.preview {enabled,max_turns?,max_utf8_bytes?}` requires
  a strict boolean; turn cap is 1–32 (default 8), and the **combined redacted
  user+assistant UTF-8 text cap per turn** is 2,048–32,768 bytes (default 16,384).
  Enabling requires explicit private-store setup. Preview writes nothing and
  returns proposed settings, a one-use token, 300-second expiry and notice.
- `private.capture_settings.apply {preview_token,confirm:true}` verifies exact
  native owner, store identity and previous settings revision. Tokens are capped
  at 64 and consumed before one publication attempt; no automatic replay occurs.
  It returns status. Missing/uninitialized storage can report disabled without
  creating a store.

The admission schema has no reliable admission creation timestamp. Consent instead
saves the profile's current admission-sequence high-water mark under the same
native writer fence. A capture must have a sequence strictly greater than this
mark. Already queued or in-flight admissions are excluded, even if they execute
later. Re-enabling or changing settings saves a fresh watermark. This deliberately
avoids retroactive capture and clock comparisons. The watermark is not exposed as
cross-chat activity metadata.

Consent is checked again inside the capture transaction immediately before any
source mutation. Disabled, before-consent, duplicate and known-capacity-refused
turns do not change the private manifest or its revision. Capture failures cannot
turn a successful conversation into a failed one. Supported status callbacks show
a generic skip/not-confirmed notice without captured bodies or paths; clients
without such a callback may not display it. Inspect status/list after uncertainty.

## Atomic retention and provenance

Each successfully captured admission creates exactly two existing private source
snapshots and one capture receipt in the same atomic manifest replacement:

- user source: submitted/admitted role, never an inferred user endorsement;
- assistant source: finalized assistant role, never relabeled as a user fact.

Both are forcibly `sensitive:true`. There is no nonsensitive capture setting or
automatic declassification. Snapshot `native_capture` metadata is server-generated:
`admission_id`, `role`, `phase:"finalized_before_delivery"`, and
`representation:"secret_redacted_native_text"`. Manually supplied source author
and reference labels do not acquire this native provenance. Complete receipt and
source consistency is validated on every private-manifest load/save.

A receipt keyed by native admission ID makes repeated finalization or uncertain
commit retries idempotent: the first successfully retained snapshot is kept, never
overwritten or duplicated by a later callback for that admission. Captured source
text is immutable through supported APIs. SHA-256 covers the UTF-8 encoding of the
stored **redacted representation**, not original wire/file bytes or delivery proof.
It checks consistency, not authorship, truth or tamper-proof history.

## Human inspection and curated extraction

`private.capture.list {limit?,before?}` returns `turns` summaries, `truncated` and
`next_before`. Limit is 1–32, default 16. Each current-chat summary includes
`capture_id`, `created_at`, `user_source_id`, `assistant_source_id`, their respective
UTF-8 byte counts and phase. It exposes no bodies, raw profile/principal, private
scope key or global admission sequence. A lost capture response can therefore be
reconciled by inspection rather than blindly replaying a write.

The existing private source interface provides the rest:

1. `private.source.get {source_id}` explicitly reveals one source, including its
   native role metadata. Ordinary private source listing also includes captures.
2. `private.excerpt.preview` selects an exact quote with explicit occurrence when
   ambiguous; it returns native source-origin metadata for captured sources.
3. `private.excerpt.apply` requires confirmation and creates a **pending** exact
   excerpt. Source sensitivity is inherited and cannot be lowered while preserving
   the captured citation. There is no automatic approval, semantic interpretation
   or external extraction. Sensitive records remain excluded from automatic recall.
4. `private.source.withdraw` uses explicit revision/confirmation and retains text.
   It invalidates tracked linked active records/dependents. Existing captured-source
   receipts remain intact. Restoring records linked to a withdrawn source is refused
   without losing their retained archive.

All source/ref/span/quote and lifecycle rules in `PRIVATE_SOURCE_CONTRACT.md` still
apply. Removing a captured-source citation through explicit manual authorship does
not retain a verified captured-provenance claim. Nothing here provides an external
model-extraction consent or promotes private records into project stores.

## Capacity and failure limits

`max_turns` counts this chat's lifetime retained captures, including withdrawn
sources; it is **not a rolling time window**. Lowering a cap does not delete old
text. The principal store also allows at most 32 capture receipts, 64 total source
snapshots (including manual/withdrawn snapshots), 512 capture-settings entries,
512 active-plus-retained records and the existing 4 MiB serialized full-manifest
cap. Each captured turn consumes two source slots. All text, receipts, settings,
trash and provenance metadata count toward the shared manifest cap.

Capture stops admitting new snapshots when a limit is reached; there is no silent
eviction, compaction, purge or deletion of reviewed/retained sources. Nominal
`remaining_turns` is not a reservation of shared source/byte capacity. Status can
report `retained_turn_cap`, generic `store_capture_capacity` or `source_cap` without
disclosing another chat's counts. A final full-manifest size failure may be reported
only as capture not confirmed; no partial role/source pair is committed.

Oversized turns are skipped entirely, not truncated. The native handoff additionally
refuses an unredacted user+assistant input above 65,536 UTF-8 bytes before expensive
redaction; redacted text must then fit the configured combined per-turn cap. Native
secret-redaction failure also refuses capture.

Disabling is prospective, not erasure. Capture/source withdrawal does not redact
ordinary native transcripts, already returned model context, assistant output,
exports, backups or logs; unlinked copies and restatements are not tracked. A failed
or uncertain settings/withdrawal write is not proof it took effect. Read status and
source/capture lists before deciding whether a fresh confirmed action is needed.
The native authority fence and external manifest do not form a cross-database
atomic commit, and platform-specific durability is not strengthened by this feature.
