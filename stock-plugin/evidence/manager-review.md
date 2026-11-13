# Focused-chat manager candidate review

Baseline: published ed488b9 stock-plugin source. Experimental candidate, prepared for publication after tests and independent review. Actual Windows/Desktop UI remains unverified.

## Scope
SDK-only settings component, authenticated exact-session slash route. No host/core patches, new grants, remote model calls, public publishing, or cross-profile memory access.

Adds 12-item approved/pending/trash views; explicit approved save with actual destination; review/approve; two-step recoverable trash; restore-to-review. Record kind and destination/sharing are separate labels. Shared record impact and copies retained elsewhere are disclosed. No editing, full-text UI search, source browser, bulk operations, native folders or permission wizard claimed.

## Safeguards / independent review
Independent reviewer found and verified fixes for changed-content approval, snapshot revocation race, database identity replacement, and StrictMode effect remount. Snapshot JSON is materialized under BEGIN IMMEDIATE, with expiry recheck; writes validate policy revision, persistent database identity and record version under the write transaction. Client uses captured gateway/socket and owner checks; old replies suppressed. Shlex quoting round-trips multiline text, apostrophes and backslashes. Untrusted memory rendered as plain React text, not HTML.

99 Python tests and four JS suites pass. Independent scripts additionally exercised concurrent WAL revocation writer serialization, malformed/cross-session denial, replacement identity, stale publication and StrictMode remount. They use local synthetic data and mock hooks, not real React renderer or Windows host.

## Limits
No real host checkout or installed GUI available in this workspace. Chromium preview capture failed with socket Operation not permitted; no screenshot is claimed. manager-component-preview.html is generated from actual component element output with synthetic records; host theme/layout remains unverified.

A grant remains shared by authenticated clients of that exact session. This is not human-only authorization. Existing local filesystem/DB authority is outside the isolation boundary. Already returned data cannot be withdrawn; an identical restored historical DB snapshot is not detectable. Immediate SQLite snapshot lock adds short contention. Other slash commands retain existing semantics. Pagination can shift on concurrent edits. No performance or benchmark improvement claimed.

## Windows acceptance checklist
1. Update candidate in disposable profile; Desktop ELM enabled; no core patch.
2. Ungranted chat shows locked setup only; no rows/counts/destinations.
3. Grant exact chat, Refresh. Save each kind with chat-only grant: all remain this-chat destination.
4. Explicitly regrant project/user; verify previews then shared destination and other enrolled chat behavior.
5. Review draft, approve; Trash confirmation, restore returns to Needs review.
6. Edit a reviewed record from another enrolled chat then approve stale view: operation must fail and clear list.
7. Change grant/project after preview: stale save must fail, not redirect.
8. Switch chat/profile/connection during load; no stale data or writes appear in new owner.
9. Revoke/expire grant, refresh: no data; saved records survive regrant/restart.
10. Test empty states, 13+ records pagination, narrow window, long text, theme contrast and keyboard controls. Supply actual host screenshots before visual approval.
