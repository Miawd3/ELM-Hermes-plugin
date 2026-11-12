# r20: reviewed declared-export copy, not automatic legacy migration

## Ownership boundary

Legacy `WorkspaceService._ensure_scopes` creates profile-wide `personal` and project-keyed workspace scopes. Those labels do not establish the current authenticated principal's ownership of historical content. This milestone therefore does not enumerate, open, search, adopt, modify or delete any legacy root, record store, cache, index or file. There is no source path, URL fetch, sidebar inference or old-store selector.

Instead the person supplies a small selected-record JSON export directly and explicitly declares the right to copy every supplied item. This is a user declaration, not verified historical ownership, authorship or native authority. Current destination authority still comes only from the native authenticated memory context. No principal/project membership is imported from the export.

## Supported input

`private.import.preview({export_text, ownership_declared:true})` accepts at most 65,536 UTF-8 bytes of JSON received by the API:

```json
{
  "format": "elm-selected-records-v1",
  "records": [
    {
      "id": "old_record_1",
      "title": "Selected note",
      "text": "Exact selected text",
      "sources": [{"ref": "declared-document-label"}],
      "scope_id": "personal",
      "revision": 3,
      "state": "approved",
      "sensitive": false,
      "domain": "work",
      "kind": "reference",
      "basis": "source_document",
      "topic": "facts"
    }
  ]
}
```

The wrapper is an explicit selected-export format, not an entire legacy manifest. Each of 1–8 rows must have id/title/text/sources. Optional fields are exactly scope_id, revision, state, sensitive, domain, kind, basis, topic, created_at, updated_at and dependencies. These include the standard legacy authored-record shape. Unknown fields (including tags, grants, root/profile selectors or model instructions) are refused, never silently dropped. IDs must be unique within a batch. Duplicate JSON keys, nonfinite values, malformed types and unsupported fields are rejected.

Only empty/absent dependencies are supported. `record:` and `elm-snapshot-v1:` source references are rejected: this slice cannot prove or transfer their dependency/private-source ownership. There is no graph migration or hidden link repair. Sources must number 1–7, leaving room for an added declared-export provenance reference. Source dictionaries retain only the native ref/optional quote/sha256/revision shape. Those inherited values remain user-supplied claims, not verified documents or captured-source proofs. No URL is visited.

Each new title is at most 512 UTF-8 bytes, text at most 8,192 bytes, and combined source metadata at most 8,192 ASCII-escaped JSON bytes under the existing private authored-record limits. Retained original claims are capped at 4,096 serialized bytes per row and checked before issuing a preview. Unsupported larger/linked records require a different explicit migration design, not truncation.

## Full preview and normalization

Preview returns complete normalized `candidates`, parallel `original_claims`, raw-received `export_sha256`, logical `canonical_sha256`, opaque `batch_id`, destination `{kind:'current_private_chat', context_key}`, the ownership/copy notice, any `existing_receipt`, and a 300-second one-use `preview_token`. No destination path, raw principal or caller-selected namespace is exposed.

Every candidate is a **new private-chat reference**, with domain `reference`, kind `reference`, basis `source_document`, topic `facts`, state `pending` and sensitivity **true**. Legacy approval, inferred/user-fact classification, sensitivity false and old scope never become present authority. Original ID, scope, revision, state, sensitivity, timestamps and classification labels remain explicit unverified historical claims in the preview/receipt. Title/text and inherited source metadata are copied exactly, with an added `declared-export-v1:<canonical-hash>:<index>` reference that points to this declared batch, not a native captured-source registry.

The UI/client must present the complete old-to-new downgrade and current private destination before confirming. No approval or declassification occurs. Separate private record review/approval is still required; sensitivity remains true unless later changed through an independently explicit editing workflow. This API is a trusted authenticated client protocol, not proof a human physically clicked a checkbox.

The raw digest covers UTF-8 of the string received by this API, not original disk/PDF/clipboard bytes before any client normalization. Canonical JSON sorts object keys and ignores whitespace/key order, while retaining all supplied values and array order. Hashes establish content consistency, not authorship, ownership or tamperproof signatures.

## Atomic copy and idempotence

`private.import.apply({preview_token, confirm:true})` revalidates the exact native owner snapshot and destination store, then creates new UUID records and a receipt in one private-manifest transaction. Existing records are never overwritten. The receipt and candidates cannot be partially committed through the supported transaction; a postcommit failure can nevertheless report uncertainty after both already exist.

Batch identity hashes the canonical export and the authenticated destination chat. An identical logical export into that same chat returns its existing receipt without creating more records, even after restart or with different JSON whitespace/key order. The same input in another chat has an independent batch identity and reveals no other-chat receipt. Changing any supplied value or array order creates a different reviewed batch and can intentionally make another copy; this is exact-batch idempotence, not global semantic deduplication.

A consumed preview cannot replay. A fresh preview of an already imported canonical batch reports `already_imported:true`; apply returns `applied:false` and the existing receipt. The first raw export digest remains in that historical receipt. If two independently confirmed equivalent previews race, the final transaction still checks the same batch key. There is no automatic retry on publication failure.

## Reconciliation and retention

- Apply returns `{applied, already_imported, receipt}`.
- `private.import.list({limit?,before?})` returns current-chat-only `receipts` and `next_before`, default/max 16. List summaries omit original claims.
- `private.import.get({batch_id})` returns the complete current-chat receipt.
- Receipts include batch ID, creation time, both source digests, ordered new `record_ids`, parallel `original_claims` (get/apply only), and declaration `user_declared_right_to_copy`.

After a lost/uncertain response, inspect the known batch ID or list receipts before doing anything else. Record IDs provide direct reconciliation. Blindly altering/repeating a batch is not recovery. Receipt validation requires every mapped destination record to exist in this same private chat as an active record or native tombstone, so supported correction/delete/restore remains possible without losing import history.

There are at most 64 retained receipts per principal store, 16 outstanding previews and 1 MiB total serialized preview retention; each preview payload is at most 128 KiB. The existing 512 active/retained-record cap and exact 4 MiB private-manifest cap include copied records and receipts. Bounds are rechecked at publication; filling storage after preview can still refuse the copy. No eviction, purge, erasure, legacy backup or automatic export is implemented. Original supplied JSON is not stored as a separate raw blob; the copied content and bounded historical receipt remain local plaintext. Existing private filesystem checks are not a hostile-filesystem sandbox.

No legacy data or user files are accessed by qualification tests; all fixtures are synthetic. No model calls, network fetches, provider changes, real credentials or external publishing are involved.

Receipt linkage validation is deliberately not a tamperproof audit: after legitimate record corrections, current bodies need not reproduce the original canonical export. A malicious filesystem owner could rewrite otherwise valid same-chat records/receipts together. There is no signature, immutable external journal or hostile-local-owner guarantee. The supported API preserves historical claims and destination linkage; it does not prove that arbitrary valid on-disk edits never occurred.
