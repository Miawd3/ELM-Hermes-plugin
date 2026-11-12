# Experimental authenticated workspace selection backend

Requires the matching recovery host patch. This is a backend API, not a shipped visual panel.
Unpatched hosts skip registration; existing workspace-provider compatibility is not implied.

- `plugin.elm.workspace.status`: canonical authenticated local read, no record/index reads.
  Reports stored project selection, revision, setup presence and principal-qualified hashed
  namespace proposals. Always says workspace_read_authorized=false and record_access=not_connected.
- `plugin.elm.workspace.project.preview`: ordinary authenticated control RPC; exact project_id
  or null to unbind. Returns a secret one-use preview_token and 300-second redemption lifetime.
  Target eligibility is checked on apply, not claimed at preview time.
- `plugin.elm.workspace.project.apply`: preview_token plus confirm=true. No caller home,
  principal, root, scope or alternative target fields. Host transport session_id is allowed
  but never treated as an authority source. Captured owner equality and native CAS required.

Tokens are process-local, capped256, and invalidated by restart/close/reload. Foreign owners
cannot consume another owner's token; changed same-owner snapshots invalidate a stale token.
Redemption consumes before mutation. Concurrent retries cannot execute the same token twice.
Expiry is checked on redemption, not cancellation of an already admitted operation. Close
serializes after admitted binding completes. In-flight effects can still be uncertain.

A successful bind followed by status rendering failure returns applied=true and refresh_required,
not an instruction to retry. Any generic failed RPC may also follow a committed change; inspect
current state and obtain a fresh preview rather than replaying. No durable receipt/deduplication.
Hosted plugins register status only; preview/apply are in-process only.

Selection does NOT authorize workspace memory reads, approve/share records, migrate old scopes,
change read policy or enable provider recall. Legacy WorkspaceService/REST/provider paths remain
unchanged and unqualified. Their profile-global personal/project namespaces must not be silently
adopted as principal-scoped memory. Future recall needs a separate eligibility and consent check.
