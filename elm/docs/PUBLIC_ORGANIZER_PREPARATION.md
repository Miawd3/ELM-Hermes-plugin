# r34 public organizer preparation and disabled production execution

## What exists

Authenticated ELM RPC now prepares an exact organizer request from one to four explicitly selected active private-chat source snapshots. It uses the actual host-enrolled organizer slot and requires the current chat's declared organizer preference to match that slot's provider, model and endpoint exactly. It never accepts a caller-supplied endpoint, model, payload or credential. Search execution is not implemented.

The host enforces the full native interactive capability grant on preview, execute and cancel, in addition to current native owner/project eligibility and the existing ELM source fences. A control-only or read-only limited actor is insufficient. Interactive capability is permission, not proof that a human clicked; trusted installed code shares process/renderer authority.

## Public protocol

- `private.curation.organizer.preview {source_ids,max_output_tokens?}`: returns `preview_token`, `job_id`, full `egress_payload` including model, `payload_sha256`, `recipient`, `source_pins`, `expires_in_seconds:300`, `max_output_tokens` (requested1..512, default512), `max_payload_bytes:32768`, `cost_notice`, `notice`, and `production_dispatch_supported:false`.
- Recipient fields are provider, exact HTTPS endpoint, credential mode `host-enrolled-slot`, slot `organizer`, slot version, route digest, and fixed no-redirect/no-retry/no-fallback/no-environment-proxy flags. There is no secret value or secret fingerprint.
- Source pins contain source ID, digest, revision, sensitivity and active state. Full selected source text and declared/native-role metadata are shown in the exact outbound payload. Preview has no external effect and does not grant egress consent.
- `private.curation.organizer.cancel {preview_token}` returns `{cancelled:true}`. A token is owner-bound, expires after300seconds, and may be canceled only before admission. There are at most16 pending receipts per loaded service. Closing/unloading clears them.
- `private.curation.organizer.execute {preview_token,confirm:true,payload_sha256}` is registered but **production-refused before job/attempt writes** because no production server transport is configured. The UI has no enabled send button. The exact hash must match when an internal qualification adapter is installed.

Saving a slot or preference is not egress authorization. Prices are unknown. Token and byte bounds are not a monetary cap, and there is no enforced currency budget. This is one reason production remains disabled.

## Actual host consumer and qualification boundary

The host-owned organizer service consumes enrolled credentials internally. No public plaintext getter was added. r33 encrypts the whole slot object, so metadata inspection decrypts that object inside the host; it would be false to claim preview never decrypts any secret bytes. Only allowlisted metadata leaves the host.

Production `_TRANSPORT_FACTORY` is unset. Isolated tests replace only server-side socket construction with a local test endpoint while retaining the logical enrolled HTTPS recipient. There is no client flag, public test route or arbitrary payload proxy. This tests the same registered handlers, actual encrypted slot/version reads, exact bytes, Authorization-header construction, durable native attempt, and result publication. It does not prove live TLS, real-provider compatibility, pricing, credential validity, or production readiness.

The native attempt record is durably committed in state.db before socket I/O and binds owner, recipient/model/version, exact payload and selected-source fingerprint. At most64 retained attempts per principal are allowed; there is no purge/automatic retry. In-memory one-use receipts disappear on restart, while durable attempted records remain. An unavailable production adapter creates neither attempt nor job.

Before connection and immediately before header construction, the host checks current native ownership and the exact slot version/route. Source/preference freshness is rechecked after durable claim; source/preference state is checked again before result publication. A response observed after slot rotation/revocation is withheld. These are snapshot checks, not an atomic lock across network I/O: revocation cannot retract bytes already dispatched, provider copies, or SDK-independent network state.

Strict single-choice OpenAI-compatible response parsing feeds the existing exact-source proposal validator. Results are retained only as validated untrusted proposals. Individual acceptance creates pending sensitive/source-bound records; final approval is separate. Existing jobs list/get/accept remain the reconciliation surface.

## Uncertainty and retention

The local job manifest and native attempt ledger are separate stores. A failure can leave an attempted job without a sent request, or a completed native transport with no usable result. A postcommit error can also leave a ready job or accepted pending record despite a lost reply. Inspect jobs and never automatically resend. A transport failure after invocation is conservatively uncertain, not evidence that no bytes left.

No native database lock is held over network I/O. The service lock serializes admitted work with close/cancel; it cannot promise cancellation of an already admitted request. Existing transport limitations remain, including no guaranteed absolute wall-clock deadline through all DNS/TLS/header internals. Source withdrawal and credential revocation do not securely erase existing jobs, backups, transcripts, or provider data. No real key or external model call is used in qualification.

The host also withholds a response containing the exact credential value that was actually sent, including ordinary JSON escapes and nested JSON content. The transient comparison value is cleared after the invocation. This prevents direct echoed-key storage in a model-supplied proposal title; it is not a detector for arbitrary transformations, encodings, fragments or covert channels from an untrusted recipient. Revocation/rotation does not change which admitted value is checked for that response.

Execution qualification additionally requires the native SQLite connection to report synchronous FULL or EXTRA and a file-backed journal mode (WAL, DELETE, TRUNCATE or PERSIST). The check occurs before local job creation and again under the attempt transaction lock. NORMAL/OFF or MEMORY/OFF journal mode refuses execution without changing the user's database policy. Preview remains read-only and available. This establishes the configured SQLite synchronization contract, not a guarantee against faulty storage hardware, OS/filesystem failures, or malicious database replacement. Synthetic success fixtures explicitly select FULL for their disposable database.

For the r35 exact budget classification, selectable requested output limit and synthetic TLS qualification, see `ORGANIZER_BUDGET_AND_TLS.md`. Production remains disabled.
