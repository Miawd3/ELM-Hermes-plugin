# Experimental consented project memory review

The opt-in unified Desktop plugin now has two separate native SDK routes: `/elm-private-review` and `/elm-project-review`. Opening one never silently changes the other's scope. The project page uses only the existing authenticated `SDK.host.request` transport and reconstructed backend contracts. No native sidebar behavior or host settings are changed.

## Exact binding and explicit permission

Refresh first. The page shows the exact ELM project binding ID/revision and the current chat's consent revision, policy version and effective authorization. Native sidebar placement, a stored old grant, and a selected project are not permission by themselves.

The expandable binding controls accept an existing exact native project ID. They do not create projects or guess a project from its name. **Preview exact binding** and **Confirm binding** use `workspace.project.preview/apply`. Binding does not grant consent, import records or enable provider recall. There is no native project-picker integration in this slice; an existing exact project ID is required.

**Preview project consent** retrieves the exact server-authored permission notice and target project; a separate confirmation applies it. Policy 2 explicitly includes human inspection of pending/sensitive records and correction, deletion and restoration across independently consenting chats of the same principal and project generation. The page does not claim cross-principal collaboration.

Older policy-1 grants retain their existing backend permissions but do not authorize these new inspection/edit controls. The page withholds all record bodies and offers explicit re-consent. It never upgrades a grant automatically.

**Preview revoke consent** and confirmation withdraw this chat's consent. They do not erase its contributions or revoke other chats' independent permissions. If an archived/deleted binding blocks the native read fence, the page can still show owner-only binding metadata. Use **Preview unbind**, confirm, then refresh and separately preview/confirm revocation. No fence is bypassed and no automatic unbind/revoke chain runs.

## Review and lifecycle

With effective policy-2 consent, the project panel uses `project.list/get` for metadata and explicit record reveal, including human-only sensitive inspection. It exposes full inert provenance metadata, pending approval, corrections, deletion preview and affected IDs, retained trash, and pending-only restoration. Manual pending-record creation is added in r12; see CAPTURE_AND_CREATION_UI.md.

Corrections replace current text and withdraw approval. Deletion retains full bodies and is not erasure. Restoring does not restore approvals. All project lifecycle calls use the consent revision captured with the reviewed record, trash list or deletion preview, not a newly substituted revision. Public model recall still applies its sensitive/inferred-user exclusions and remains separate from human inspection.

## Snapshot and stale-action protections

Profile, connection, focused runtime/stored session, gateway instance/state and activation epoch retain the private panel's intent guards. Every project content operation additionally rechecks binding and policy status. An opaque backend `context_key` pins the native owner, store and complete consent snapshot; every list/get/trash/deletion-preview reply must match the reviewed status. Native binding IDs/revisions from the separate status calls must agree. Mixed snapshots are withheld.

The displayed data is a **snapshot until refreshed**, not a live authorization indicator. The SDK currently exposes no qualified project-consent change signal. External changes are detected on the next explicit refresh or action. Refresh clears project bodies first. Context changes and failed operations clear record detail, staged confirmation and access display; late replies cannot repopulate a new context. Final clicks bind the exact rendered owner, record revision and staged confirmation object. Backend authorization remains authoritative.

No mutation is retried automatically. Lost results require inspection and explicit reconciliation. If a mutation is uncertain and the project remains unreadable, the UI may stay blocked; it does not guess whether consent applied or bypass the native fence. Existing direct binding/reconciliation tools remain a separate operational path.

## Evidence and limits

The r11 baseline verified twenty-five controller tests: eleven private-panel regressions plus fourteen project cases covering no implicit reads, policy-1 withholding, separate binding/consent, unavailable projects, exact staged consent revisions, mixed snapshots, changed context keys, stale confirmations and no sidebar-derived permission.

Real React SSR renders the actual project component with a synthetic SDK/state adapter. Preserved HTML covers record review, grant confirmation and re-consent. Checks verify sensitive human detail, policy-1 body withholding, full provenance, token nondisclosure, hostile text escaping and stale-context suppression. The controls and theme in these previews are approximations; they are not installed Hermes screenshots.

The prior sandbox-enabled Chromium launch was blocked by execution-environment socket restrictions. This slice does not bypass those restrictions or claim new browser/native Desktop acceptance. No paid model/API calls, live installations, public publication, migrations or automatic assistant recall were performed.

## r12 extension
Manual pending-record creation is now available with an explicit review/confirmation and the displayed consent revision pinned on `project.create`. See CAPTURE_AND_CREATION_UI.md. Source snapshot/excerpt controls remain private-only; they do not appear in this project page.
