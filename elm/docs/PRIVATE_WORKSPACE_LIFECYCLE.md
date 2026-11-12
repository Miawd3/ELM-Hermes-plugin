# Experimental private-chat record lifecycle

These authenticated RPCs operate only on the explicitly initialized principal-qualified
private-v2 store and current canonical chat. They are not model tools or user-interface
controls. There is no provider auto-recall, project recall, scope expansion, or legacy
store adoption. A candidate desktop review panel now calls these endpoints; see PRIVATE_WORKSPACE_INSPECTION.md. Native browser/Electron visual acceptance remains unverified.

## Correction

`private.correct` accepts `record_id`, `expected_revision`, an authored-field `changes`
object, and `confirm: true`. Scope, identity, approval state and dependencies cannot be
supplied. Every successful correction becomes **pending**, increments its revision, and
invalidates its dependent closure. Reapproval is explicit and revision-checked.
Correction replaces the current authored text; this prototype does not retain version
history. A source/dependency inconsistency is refused, not silently reinterpreted.

## Recoverable deletion

1. `private.delete_preview` accepts a record ID. Its returned token covers the current
   authenticated owner, store, record content/revisions and dependent closure. The preview
   expressly states that bodies will remain privately retained and no purge exists.
2. `private.delete` requires the ID, expected revision, preview token and `confirm: true`.
   Changed ownership, records or closure invalidate the preview.
3. The single atomic manifest replacement moves the current-chat closure into a validated
   `private_trash` envelope and replaces active records with revisioned tombstones. Trash
   records are never eligible for recall. Full text and source metadata **remain on disk
   indefinitely until restoration**. This is not erasure or permanent deletion.

The extension is private-v2-only and checks its schema, checksum, owner scope, store ID,
retained record shapes, dependency topology and exact tombstones. Generic RecordStore
and all old global paths remain unchanged. Existing correctly marked private-v2 stores
receive the additive extension only through a confirmed delete; unrelated roots are never
adopted. There are no archive side files or cross-file commit promises.

`private.trash` lists only current-chat recovery summaries, never retained bodies or
other-chat counts. It accepts `limit` (1–32, default 16) and optional `before` recovery
ID from the preceding page's `next_before`. Each summary gives its recovery ID,
deletion timestamp, count and at most eight record IDs. A restored/missing cursor
requires refreshing the list. This allows reconciliation after a lost or uncertain
delete response without inspecting files or blindly repeating the delete.

`private.restore` requires the returned recovery ID and `confirm: true`. It checks the
current private chat and exact retained tombstones, restores the complete retained closure
as **pending**, advances revisions, and updates internal dependency/source pins together.
An external surviving source that changed or disappeared prevents restoration; retained
payload remains untouched for later resolution. The same commit removes the recovery
envelope once its bodies are active again. Replay fails. Restoration restores no approvals;
reapproval of a source can invalidate restored dependents again. This slice exposes no
dependency-pin repair endpoint, so complex retained provenance may remain non-approvable
until a separately reviewed repair workflow exists. No pins are silently rebased to
changed external content. The response contains IDs/revisions, not all retained bodies.

No permanent purge endpoint exists. Host transcripts, exports and backups are outside
this store's lifecycle. Do not describe recoverable deletion as comprehensive privacy erasure.

## Limits and uncertain outcomes

Active plus retained records share a 512-record limit. The complete serialized manifest,
including tombstones and recovery metadata, is capped at 4 MiB. Full-store processing is
bounded by those caps, not a promise of constant runtime. All reads/mutations retain native
ownership fences and the store lock; no callback is automatically retried. A storage error
after replacement can leave an uncertain outcome: inspect current state before another
explicit action. Failed restoration never discards retained bodies.
