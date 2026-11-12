> ARCHIVAL ONLY. This document describes an earlier, inactive implementation. Do not use its installation, provider, tool or permission claims for the r21 candidate. Relative links may refer to its original location.

# Security and disclosure: experimental release

## Local trust boundary

This is Python source, not a sandbox, signed binary or production certification.
A plugin executes with the host user's permissions. The tested stock transport
is in_process. Another same-user process can replace files or race checks; the
candidate does not defend against that adversary. Stores and profiles must be
explicitly chosen and locally controlled. No path is adopted from source text.

Provider reads/writes are bound to a profile, root, project, permission mode and
root-identity digest. Source metadata is caller supplied and unverified. Neither
exact citation, marker syntax nor retrieved text establishes fact validity,
authenticated identity, authority or user authorization.

## Data storage and movement

The plugin makes no model, telemetry or network calls. Canonical engine operations
use the host interpreter in an isolated subprocess environment with explicit
root/project flags; episode operations instead use the profile-local SQLite
store directly. No mandatory service, credential discovery or external model
extraction exists. Explicit query text may be visible to local process inspection.

Capture is separately opted in and then persists eligible scrubbed visible
user/assistant message pairs. It may retain sensitive contents not recognized by
pattern scrubbing. Message/episode/author metadata and replay hashes also persist.
Retention expiry does not erase every local derivative. Explicit markers can be
staged and, in allowed binding modes, submitted as pending governance proposals.
Submission persists source-derived rationale/evidence in the canonical/governance
store beyond the local episode deletion boundary. Configuring read-only mode
blocks canonical proposal submission but does not disable opted-in local capture.

Explicit notes, receipts, governance records and backups have their own retention.
An adopted root outside the profile is not automatically covered by inherited
backup_paths(). Offline batch inputs/results are caller-owned in-memory data;
callers can copy or display them. The batch API does not transmit or persist them.
No encrypted-at-rest, comprehensive DLP or secure deletion guarantee is made.

## Retrieval, inspection and mutations

Episode evidence is available only through explicitly opted-in search/read tools;
it is never automatically injected into background recall. Source text is
untrusted data. Inspection is read-only, refuses WAL/sidecar recovery, and shows
source text only with its explicit flag and current capture/recall settings.
Serialized control/markup escaping is not universal prompt-injection protection.
Canonical prefetch is disabled by default (explicit-only), including legacy bindings without a recall_mode. It starts no background query/worker in that mode. The optional legacy-background mode reintroduces the upstream authoritative-wrapper trust mismatch and is not recommended for live use. No host patch or production-readiness claim is made.

Submitted local candidates remain visible without implying acceptance. Inspection
does not read current governance outcomes. Acceptance, deletion of governance,
trusted source-root configuration and supersession are not model-facing controls.
Default canonical mode is read-only; proposal-only permits pending proposals,
and autonomous also permits bounded leased unverified explicit agent-curated notes.
Primary-session and configuration/identity guards remain in place.

Operator forgetting requires an exact scoped locator and the reviewed preview
plan digest. It removes linked local source pairs and scrubs local proposal
copies, including late-result protection. Canonical/governance records, host
transcripts, backups, old SQLite pages and prior returned copies are not erased.
Same-UID replay metadata remains. New IDs carrying equivalent text are not a
semantic erasure filter. Unknown dispatch outcomes remain blocked after restart
or forgetting and require separate outcome review, not blind retry.

## Supply chain and qualification

The engine is byte-identical to the submission-reconciliation input archive. engine/SOURCE_MANIFEST.json preserves historical upstream provenance only; the root SOURCE_MANIFEST.json binds the current complete release. See PROVENANCE.md for the source chain. Historical source-test reports are not current acceptance evidence.
No bytecode, databases, credentials, actual user transcripts or environments are
included. Tests used only disposable synthetic stores and pinned stock Hermes.
No live profile, user corpus or host checkout was changed. See VALIDATION.md and the separate release evidence for checks and qualification limits.

Report vulnerabilities privately to the repository owner. Do not include actual
memory stores, secrets, chats or credential-bearing output in a public report.

## Durable review inbox boundary

The optional durable inbox persists only bounded source locators, offsets,
unverified labels, state, and hashes. It never persists source text/quotes or
canonical payloads and cannot submit or accept. Labels remain sensitive derived
content. Every disclosure revalidates current source evidence and configuration;
revocation and forgetting scrub derivatives. Optional inbox corruption must not
block source cleanup: cleanup quarantines and scrubs the whole inbox, retaining
a permanent admission-blocking marker. Digests are unkeyed and do not defend
against hostile local file/database ownership. Opt-out is observed on operation,
not continuously; explicit revoke-all provides a durable withdrawal boundary.
Logical deletion does not erase SQLite remnants or previously returned copies.

## Explicit operator review bridge

A separately enabled operator-only bridge now persists bounded operator meanings
and generated pending-proposal payloads. These are sensitive local derivatives,
not source-copy fallbacks. Exact citation never fills semantic fields. Explicit
meaning, project scope, temporal assertion, context, attribution, uncertainty and
a digest-bound confirmation are required before the existing local proposal-only
engine call. No provider/model tool registration, acceptance or network transport
is added. Source withdrawal/expiry/forget scrubs these local derivatives; canonical
proposals survive. Unknown outcomes remain durably blocked with no blind resend or
reconciliation shortcut. See docs/OPERATOR_REVIEW_BRIDGE.md for limits and workflow.

## Conservative submission reconciliation

The operator-only `operator-reconcile` command observes canonical governance under the engine writer lock and records submission only for an exact persisted ID/payload match. It never resends or accepts. Absence, conflicts, incomplete transactions, and missing or scrubbed payload proof remain blocked. See docs/SUBMISSION_RECONCILIATION.md for proof assumptions, privacy limitations and unresolved recovery cases.

## Host/model boundary

The plugin does not make network or model calls. Explicit tool results and opt-in legacy prefetch are nevertheless supplied to Hermes; the host can include them in a later request to its configured model provider. “Local” describes ELM storage/processing, not a guarantee that host use keeps all returned text offline.

Guided setup refuses existing settings and does not roll back data on partial failure. Older explicit manage.py init/adopt and native save_config can replace a binding; inspect before using them. No malicious-local-user path-race defense is promised. Default capture retention is three days, checked during operations, not by a deletion daemon. Lifetime durable review/inbox tombstones are bounded with no compaction procedure; do not delete replay barriers.

## Named-tokenizer boundary

Measured context packing occurs in the provider process using local hash-verified vocabulary and optional pinned tiktoken. The database child remains `-s -S` with restricted environment; no site-package bootstrap or credentials are added. The internal packing-input response transfers scoped candidate text to the provider, never directly to a model. Local tokenizer files/packages must be trusted; hashes do not sandbox Python/native code. Counts cover declared successful text surfaces only. Stock background lacks a verified spill-budget receipt and fails closed in measured mode; explicit retrieval remains available. See [details](docs/MEASURED_TOKEN_BUDGET.md).
