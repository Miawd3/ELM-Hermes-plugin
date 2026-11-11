# Capture text filter correction

This isolated 7 November 2026 follow-on fixes false rejection of ordinary plain text such as `Metadata:` and `Here is the data:`. The original measured-budget candidate is unchanged. This copy is not deployed.

The capture filter now recognizes a standalone case-insensitive `data:` scheme, a non-whitespace URI header, and its required comma. Real inline data URIs remain refused, including empty payloads, omitted media types, percent-encoded parameters, and apostrophe/backtick MIME token characters. Ordinary labels are preserved exactly. Malformed or truncated URI-looking prose without a valid header/comma is not classified as inline media. This is not general DLP or proof that all sensitive content is removed. Hidden/structured content and existing source restrictions are unchanged.

## Capture gap visibility

The existing scoped SQLite capture database gains one additive `capture_gap_events` row. It stores only a saturating count of observed refused append attempts and the latest fixed reason code. It does not store rejected text, source IDs, author IDs, or timestamps. These counts survive later successful turns, session sealing, and restart. A repeated rejected attempt increments the count again; it is not a count of distinct lost messages. The row has no retention expiry or reset API.

`EpisodeCapture.status()` and the provider's existing capture status expose `capture_gaps`, including `known_refused_attempts`, `last_reason`, `counter_saturated`, and `recording_failed_this_instance`. The provider's transient `last_event` remains separate. `complete_capture_certified` is always false: zero recorded refusals never proves every host message was received or captured.

Recording is best effort and gated by the current capture configuration and root identity. Withdrawal does not authorize a diagnostic write. Missing/failed storage or an instance never receiving a hook can leave unrecorded gaps. The in-memory recording-failure flag does not survive process restart. Initialization adds the row to a compatible schema-2 database without changing stored source evidence; it does not reconstruct historical refusals. Incompatible schemas remain refused. Capture refusal still rejects the whole pair, with no transcript backfill or automatic retry.

## Verification limits

New offline URI/gap tests, inherited host-independent capture-core bodies, guided setup, retrieval hardening, tokenizer-budget checks, and the offline demo were run. The pinned Hermes checkout is absent in the current executor, so the full runner and native integration could not be rerun. Historical qualification in other documents applies to the parent candidate, not these modified bytes. See the separate fix evidence package for exact tests, source hashes, independent review, and any skips.

No live profile, canonical user store, model call, private conversation, deployment, or source-deletion behavior was involved in this correction. No complete-erasure or generated-answer improvement is claimed.
