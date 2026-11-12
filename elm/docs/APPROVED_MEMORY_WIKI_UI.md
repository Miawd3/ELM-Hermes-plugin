# Approved memory wiki: read-only human inspection (r28)

Open ELM's **Approved memory wiki** settings page. Choose **Current-chat private memory** or **Consented project memory**, then explicitly **Refresh approved index**. Selecting a scope alone does not fetch anything.

The index contains bounded approved, currently eligible record metadata. Sensitive titles and metadata may appear after refresh. Filter loaded titles/domains/topics locally; this is not a full-text or whole-store search. **Load next metadata page** uses the same pinned snapshot. Select one record to read its body. **Read bound citation evidence** performs a separate request for that selected record's declared citations, quoted excerpts, and recorded digests. It does not fetch full captured sources or follow links.

Approval is a workflow state, not a guarantee of factual truth. Declared citations are not newly verified external quotations. Native captured references retain their backend exact-span checks; a digest establishes captured-data identity, not truth. Sensitive human inspection does not authorize model recall or external transmission.

## Authenticated boundaries

Only these read-only routes are used:
- `plugin.elm.wiki.private.index/page/evidence`
- `plugin.elm.wiki.project.index/page/evidence`

Every call uses the current saved chat. Project access requires current version-2 consent; selection alone grants nothing. Index pagination, page, and evidence use the backend's opaque snapshot key; page/evidence also bind the selected record and revision. The backend evaluates current approval, sources, dependencies, and ownership atomically. Changes cause explicit refresh rather than automatic retry.

The controller clears the view on scope/owner/connection changes, checks socket/activation identity, rejects stale rendered handlers and late replies, and clears inspection data on errors. Scope switches never automatically migrate, approve, copy, or reclassify memory. No writes, global wiki scans, catalog fallback, embedding calls, or model requests occur.

## Verification limits

Actual plugin registration and controller tests use a synthetic SDK transport. The real WikiPage React component is rendered in SSR with synthetic scoped records and adapter data; `wiki-preview.html` is not an installed-app screenshot. Existing backend tests independently cover the read routes. Full native application end-to-end acceptance is not claimed. No production host UI source modification was needed for this settings contribution.

The view is a point-in-time response, not continuously revalidated authorization. A later server-side change does not automatically retract already displayed text. A new read checks the snapshot again; local scope changes clear the view immediately. No background polling or continuous revocation guarantee is claimed.
