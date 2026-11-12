# Explicit project consent and lifecycle prototype

This is a separate principal-qualified store, not a broader mode of private-v2.
No legacy data is adopted and no private record is promoted or copied. Native
project selection alone grants no record access. The catalog has no principal
ACL: this prototype never shares records across principals.

## Versioned permission boundary

A stored consent without `policy_version` is read as version 1. Existing version
1 grants retain only filtered recall, pending creation and explicit approval.
They do **not** acquire human inspection, correction, deletion or restoration
rights merely because the plugin was upgraded.

A newly previewed and explicitly confirmed grant writes version 2. Its notice
authorizes full human inspection, including pending and sensitive content,
correction, recoverable deletion and restoration, as well as the original
recall/create/approve rights. These rights cover contributions in the exact
same-principal project generation, including contributions from other chats.
Each chat must independently consent. Revoking a contributing chat does not
remove its contributions or revoke other chats' independent consent.

`project.status` exposes `consent_version`, `reconsent_required`, effective
`permissions`, stored `consent_granted`, effective `project_read_authorized`,
`consent_revision`, `selected_project_id` and `project_binding_revision`.
Stored grant status alone is not authorization. Status returns no record counts,
titles or other-chat consent revisions.

## Consent protocol

- `project.consent.preview {action:"grant"|"revoke"}` is read-only and writes no
  files. Its cryptographic one-use token expires after 300 seconds and is bound
  to exact current ownership/binding, immutable store identity and prior consent.
  Grant discloses fresh-store initialization if needed and the expanded rights.
  At most 256 previews are retained. Unload discards unused previews.
- `project.consent.apply {preview_token,confirm:true}` consumes the token before
  one native publication attempt. Never replay automatically after an uncertain
  result: inspect status and obtain a fresh preview. Admission holds the workflow
  lock through the attempt; unload waits for already-admitted operations.
- Durable consent does not expire with its preview. Its revision increases on
  grant/revoke. Version 1 requires an explicit new grant to obtain version 2.

## Record RPCs

All routes resolve authenticated host context, enforce current exact consent
inside the record-store transaction, and refuse caller-selected root, principal,
profile or scope. `session_id` is a host-authenticated transport field, not plugin
permission. Reads use the native read fence; mutations use its publication fence.

Version 1 or 2:

- `project.create {title,text,sources,...}` accepts bounded authored fields like
  `private.create` and always creates a pending record. Dependencies cannot be
  authored through this API. Source labels are declarations, not verified facts.
- `project.approve {record_id,expected_revision,confirm:true}` approves a pending
  record. Optional `expected_consent_revision` is strictly checked when supplied.
  The r11 UI always supplies it. Omission preserves the r10 trusted-current-consent
  client protocol, not proof that the client reviewed this consent generation.
- `project.recall {limit:1..20}` returns approved-only records, excluding sensitive
  and user-inferred data under the existing recall policy. Output is untrusted
  memory data, capped at 32 KiB. No provider or model-tool registration occurs.

Version 2 only:

- `project.list {limit?,state?,before?}` returns active record summaries, not text
  or sources. Limit is 1–32, default 16. State is `all`, `pending`, `approved` or
  `invalidated`. `next_before` paginates fresh snapshots; stale cursors require
  refresh. Responses are capped at 32 KiB.
- `project.get {record_id}` returns one complete active record, including pending
  or sensitive content, plus recall eligibility. It refuses responses above
  64 KiB instead of truncating review evidence. Trashed bodies are excluded.
- `project.correct {record_id,expected_revision,changes,expected_consent_revision,
  confirm:true}` accepts authored-field changes only. The result is pending;
  dependent records are invalidated. Previous text is replaced without version
  history. Scope and dependency changes are not accepted.
- `project.delete_preview {record_id}` returns the exact affected dependent
  closure, a preview token, `expected_revision`, `consent_revision`, and explicit
  retained-content/no-purge terms. The token pins owner/binding, consent, store
  identity and the complete affected records. It is not a new permission grant.
- `project.delete {record_id,expected_revision,preview_token,
  expected_consent_revision,confirm:true}` rechecks the preview and moves the
  closure into recoverable trash in one manifest transaction.
- `project.trash {limit?,before?}` returns current-generation recovery summaries,
  not bodies. Limit is 1–32, default 16. A summary includes recovery ID, deletion
  time, count and at most eight record IDs, with truncation/pagination indicators.
  This permits recovery-ID rediscovery after a lost deletion response.
- `project.restore {recovery_id,expected_consent_revision,confirm:true}` restores
  the exact retained closure pending-only. It removes its recovery envelope
  atomically after restoring active bodies. The response contains IDs/revision
  metadata, never a bulk dump of restored text. Approval is still required.

New mutations require the consent revision from the reviewed response, not an
automatically refreshed revision. Revoke/regrant invalidates a staged mutation
or deletion preview even if the selected project and records are unchanged.

## Read/UI coherence

`project.status`, `list`, `get`, `trash` and `delete_preview` return a common opaque
`context_key` over exact native ownership/binding, store identity and normalized
consent. The latter four also return `consent_revision`. The UI compares response
keys to the captured status before displaying content or staging changes, and
clears content on mismatch. It compares native workspace selection ID/revision
against project status rather than assuming separately read snapshots agree.
Keys are consistency indicators, not transferable authorization tokens.

The Desktop project review contribution is documented in `PROJECT_REVIEW_UI.md`.
RPC/UI intent is not cryptographic proof a human clicked: trusted authenticated
clients can call these routes. No automatic provider recall, migration,
cross-principal grants or permanent purge is provided.

## Isolation, revocation and catalog changes

Consent pins canonical chat, principal/profile, exact project ID, binding revision
and catalog row fingerprint. Records belong to principal+project+fingerprint,
not the creating chat. Independently consenting chats in that exact generation
can inspect and, under version 2, correct/delete/restore each other's contributed
records. No record or dependency can cross project-generation scopes.

Unbind/rebind invalidates prior exact binding consent, even for the same project.
Rename/color/path changes conservatively invalidate its fingerprint: rebind and
reconsent can select a fresh empty generation. Old records and trash are retained,
not deleted or migrated. This does not promise normal rename continuity; see
`RENAME_CONTINUITY_DESIGN.md` for design-only future work.

The native host checks current catalog eligibility, not immutable event history.
Archive then restore to an identical full row can restore eligibility of a
still-granted unchanged binding. This is not historical revocation. Explicit
revoke remains revoked. If archived/deleted/missing catalog blocks the host
fence, explicitly native-unbind first, then preview/apply revoke. Unbound revoke
locates only this authenticated chat's stored consent; clients cannot select
another chat/project target. Unbind already denies reads. Canonical session reuse
remains subject to native incarnation/tombstone guarantees, not a new eternal
identity guarantee from this plugin.

## Retention, limits and failure boundaries

Separate `elm-project-workspace-v1` storage has an immutable namespace/store
marker. Consent, active records, metadata tombstones and validated `project_trash`
recovery envelopes commit in one atomic manifest replacement. Envelopes bind
store identity, exact scope, full retained records, tombstone revisions and digest.
Deletion retains full bodies until restoration, with no permanent purge endpoint.
Restoration removes the duplicate retained envelope in the same commit. All
restored records remain pending; approving an upstream source can invalidate a
restored dependent due to revision changes. Dependency repair is not exposed,
so complex restored graphs may remain non-approvable. No stale approval revives.

Limits are 512 active-plus-retained records, 512 scope generations, 512 chat
consent entries and 4 MiB of serialized manifest including tombstones, envelopes
and consent metadata. Validation and exact serialized-size checks precede save.
No automatic compaction, adoption or repair occurs. Known symlink paths are
refused, but this is not a sandbox against hostile filesystem replacement.
Reads create nothing. Initial grant failure may leave an incomplete fresh root,
which is never silently adopted.

External publication can report uncertain outcomes. Store commit and native
validation are not a cross-database atomic transaction. Query state after an
uncertain result instead of replaying writes. Lock order is native catalog,
native state, then external store. Callbacks must not reenter host authority or
workflow locks. Native file/directory durability behavior is platform-dependent;
this prototype does not promise stronger cross-platform crash atomicity.
