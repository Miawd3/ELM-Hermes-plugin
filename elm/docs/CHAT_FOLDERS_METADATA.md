# Logical chat folders (r25 bounded candidate)

These folders organize chat rows only. They are not filesystem directories, native
Projects, a working directory, memory scope, a sharing grant, or a transcript copy.
No existing legacy folder tree is searched or adopted. The native sidebar integration
is separately qualified; this document describes the backend contract.

## Authority and persistence

The accompanying patched host provides `hermes_cli.plugin_chat_folders`. An active,
authenticated, in-process, canonical local chat is required. Background/unbound work,
unadopted history and hosted-process calls are unavailable. A profile/principal-qualified
`state_meta` key stores labels, canonical membership, creation incarnation and revision.
No message body, title cache, cwd, git data, project selection or memory consent is stored
or changed. No model tool, prompt instruction or external API is registered.

Each read revalidates native receipt ownership and the complete reset/compression lineage
of every returned member, plus its root started_at and native retirement fence. Invalid,
deleted, foreign or unresolved members are omitted, not adopted or automatically repaired.
Their metadata remains and counts against capacity; `unavailable_members` is only the
count in this authenticated namespace. The sidebar must intersect returned IDs/aliases
with its actual authorized rows and retain native connection/profile navigation. Folder
membership is never authorization to read a chat. A valid local-filesystem owner can
still alter SQLite; this is not a tamper-proof audit or a plugin sandbox.

There is no write on an empty `status` read. A mutation commits only this metadata key in
one explicit state.db writer transaction, with no callback retries. The authenticated
actor needs session:read, and mutations also session:control. Native ownership and scope
lifetime are checked inside the transaction and after commit. Project catalog eligibility
is deliberately not consulted: filing does not read project memory, and an unavailable
selected project does not prevent organizing the chat. Existing canonical binding receipt
integrity is still validated.

## RPC protocol

All names are under the plugin namespace, for example `plugin.elm.chat_folders.status`.
The host's transport `session_id` is accepted but never treated as a new authority hint.
Other extra fields, including profile/root/chat selectors, are rejected.

- `chat_folders.status {}` is a local_read RPC. It returns `version`, `revision`, opaque
  `scope_key` and `context_key`, `current_session_id`, `current_aliases`,
  `current_folder_id`, `folders:[{id,label}]`,
  `members:[{session_id,aliases,folder_id}]`, `unavailable_members`, `undo_available`.
- `chat_folders.create {label,expected_revision,expected_context,confirm:true}` creates
  one empty logical folder and returns fresh status. Duplicate exact labels are refused.
- `chat_folders.file {folder_id,expected_revision,expected_context,confirm:true}` files
  only the bound current canonical chat. `folder_id:null` unfiles it. A no-op is refused
  without changing revision or undo state.
- `chat_folders.undo {expected_revision,expected_context,confirm:true}` reverses only the
  latest filing change when it belongs to this same current chat/incarnation. Any
  intervening namespace mutation makes an old request stale; undo is not a redo stack.
  Creating a folder clears the previous undo. Undo never deletes a chat or folder.

Every successful mutation returns fresh status. `expected_context` binds the full current
native owner snapshot, including epoch/revision/lineage and explicit memory binding;
`expected_revision` binds the folder namespace. Do not reuse a staged action after a
scope switch. Confirmation is a trusted-client protocol, not cryptographic proof that a
human clicked. A response lost or a context retirement after commit may report
`chat_folders_uncertain`: refresh and inspect status; never blindly repeat the mutation.

Limits: 32 folders, 256 memberships including unresolved retained entries, 80 Unicode
characters per nonblank trimmed label, no control/format/surrogate characters, 128 KiB
serialized metadata and response. There is no delete, rename, arbitrary nesting,
collection hierarchy, automatic pruning, legacy migration or drag/drop API in this
slice. Capacity refusal never deletes metadata or chats. The single namespace revision
conservatively serializes concurrent edits across chats of the same principal/profile.

The display toggle is separate, default-off presentation state. Disabling/unloading the
plugin removes its UI/API availability, not chats or persisted folder metadata. Active
handler completion is serialized before plugin unload; uncertain already-committed work
still requires inspection. Stock hosts without the additive capability register none of
these RPCs instead of falling back to a global legacy store.
