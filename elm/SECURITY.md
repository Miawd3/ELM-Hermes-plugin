> Current release boundary: [rc40 status](../RELEASE_STATUS.md) and [test report](../TEST_REPORT.md). Milestone details below describe individual contracts; they are not claims of a live organizer/search agent or stock-host support.

# Security and disclosure: scoped candidate r21

## Trust and authority

The plugin and host patch are trusted Python running with the host user's permissions, not a sandbox. Native authenticated actor/profile/canonical identity and current lineage/catalog checks gate scoped reads/writes. Client roots, sidebar selection, declared source metadata and model output do not grant authority. Known symlink/identity checks are defense-in-depth, not protection against a malicious filesystem owner or introspecting same-process plugin.

Project bindings are selections, not ACL grants. Project records remain principal-qualified; explicit versioned per-chat consent is required. Catalog archive/restore and mutable row fingerprints have the exact limitations in the project contract. No cross-principal project-sharing authority is inferred.

## Stored and transmitted data

Fresh private/project manifests, source snapshots, recovery envelopes, import receipts and validated curation proposals are local plaintext. Sensitive sources remain sensitive in exact excerpts; approval does not automatically declassify them. Retention is bounded with refusal/stop-new behavior, not silent eviction. Trash retains recoverable bodies; there is no complete purge/erasure promise for files, transcripts, exports, backups, caches or already displayed/sent data.

Local capture is separately opted in, uses finalizer-visible redacted text and can retain sensitive information that pattern redaction misses. Source roles are provenance, not endorsement or semantic truth. User-supplied export ownership is declared, not verified; the importer never opens legacy roots.

Request recall is a separate opt-in that can place eligible private records in an ordinary model request. This can increase paid input tokens and expose them to the user's configured model and host logging/telemetry. Disable/revoke affects subsequent native admission, not already-built/sent packets or SDK-internal retries. No claim of “never logged” or exact token/currency accounting is made.

Production curation remains disabled. Synthetic credential/loopback tests do not read real keys or establish a live route. Internal transport interfaces are not public permissions. The active plugin has no automatic model extraction, legacy draft fallback, plugin telemetry or automatic URL/file ingestion.

## Confirmation, uncertainty and recovery

Explicit client confirmations are not cryptographic proof of human review. Preview tokens bind bounded state and expire, but postcommit errors can occur after changes persist. Use record/job/import/trash receipts to reconcile; do not blindly repeat actions. Durable attempted-send markers are never permission to resend. Cross-store job/ledger persistence is not an atomic transaction or exactly-once remote execution.

Stop and preserve the isolated profile/checkpoint when a marker, lineage, store identity or ledger is missing/corrupt. Do not delete replay barriers, reinitialize an old destination or run legacy adoption/repair to make a refusal disappear. See [candidate recovery](docs/CANDIDATE_INSTALL.md#recovery-and-rollback).

## Qualification limits

Pinned Linux synthetic/clean-loader tests do not establish all-platform compatibility, actual browser acceptance, hostile adversary resistance, semantic correctness, real-provider safety or production readiness. No public security certification is implied. Preserve source/hash evidence and report issues privately to the project owner; do not publish private user data or credentials in diagnostics.
