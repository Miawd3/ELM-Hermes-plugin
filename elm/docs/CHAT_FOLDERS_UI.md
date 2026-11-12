# Folders for chats: candidate UI boundary (r25)

This is metadata-only grouping of chats, not a file browser or native workspace move. It does not change working directories, repositories, native projects, ELM project bindings, or memory consent.

## Actual integration

The ELM **Folders for chats** settings page uses authenticated current-chat status/create/file/undo calls. Create a folder, then separately confirm filing the current chat. Unfile and undo are also separately confirmed. Each action pins the reviewed revision and exact context; uncertain outcomes require explicit refresh, never automatic replay.

The sidebar display toggle is off by default. It is a local Desktop display preference shared across profiles, not an authorization grant. Explicit refresh supplies a bounded metadata snapshot to the native `sidebar.chatFolders` contribution. Scope changes, request errors, mutations in progress, plugin unload, or disabling the toggle remove the contribution. It does not automatically fetch history or refresh membership.

The native sidebar intersects metadata with already-loaded real session rows. Rows must carry their own exact connection and profile tags; a global session-ID hint cannot supply missing ownership. Untagged, ambiguous, foreign-source, or stale rows are omitted. Therefore an empty display does not establish an empty folder. Recents, Projects, search, and archived views retain their normal behavior; folder copies appear only in the main non-search, non-project, non-archived list.

Folder copies use the real native section and session-row components, in a new opt-in navigation-only mode. Plain, modifier, and middle clicks pass through the same current-owner and fresh-row guard. Context menus, action buttons, dragging, sorting, and separate virtualization routes are disabled for these copies. Existing native rows retain their full controls. The current native session row is supplied to native resume routing rather than resolving a raw ID through global hints.

## Limits

- Flat, one-level folders; create, file current chat, unfile, and latest eligible filing undo.
- No rename, delete, nested folders, batch moves, drag-and-drop, or complete historical folder listing.
- At most 32 folders and 256 member lineages from the backend. Frontend also conservatively refuses snapshots containing more than 256 aliases in one lineage; it does not truncate them.
- Manual refresh, not realtime synchronization. A backend revision change rejects stale mutations. Local native source changes invalidate navigation.
- Folder metadata stores no chat titles or transcript bodies. Display titles remain the native row's data.
- Requires the patched SDK/native host and authenticated ELM bridge, not stock-host compatibility.

## Evidence

Controller tests exercise explicit review, stale context, revision checks, and uncertain response reconciliation. Native integration tests exercise actual registry/owner filtering and section callback boundaries. Real native row/action tests exercise navigation-only gestures, hidden menus, and refreshed callbacks. Existing real section tests cover unchanged native behavior. No full installed-application end-to-end acceptance is claimed.

`chat-folders-settings-preview.html` is actual settings-component SSR with a synthetic adapter and data. It is not a native screenshot, and does not depict or simulate the native sidebar navigation.
