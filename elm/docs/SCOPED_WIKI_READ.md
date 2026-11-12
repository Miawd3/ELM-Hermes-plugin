# Scoped human-facing wiki reader

This is a read-only presentation of existing approved records, not a generated
encyclopedia, a crawler, a new memory provider, or a source of new permissions.
Choose private chat or project explicitly. Project reading requires the current
exact native binding, an eligible catalog row, and existing version-2 inspection
consent for this chat. Selection alone does not grant project access. Private
reading remains current principal/current canonical chat only. Nothing is copied
between those stores or read from legacy/global wiki directories.

The six authenticated local-read RPCs are `wiki.private.index/page/evidence` and
`wiki.project.index/page/evidence`. They are human-facing, not model tools, and
are never automatically injected into model context. Local-read authorization
is a host caller capability, not cryptographic proof that a human clicked.
An authorized client can call these endpoints. Displayed text is untrusted data,
not executable instructions or a new grant for external disclosure.

## Protocol

- Index: optional `limit` (1–32, default16), `before`, `expected_snapshot`.
  Pagination requires the prior snapshot. Returns metadata `records`,
  `snapshot_key`, `next_before`, and `truncated`. No bodies or citation quotes.
- Page: `record_id`, `expected_snapshot`. Returns the full selected record
  **without** its `sources`, plus `source_count`. No partial/truncated body is
  returned. Sensitive approved records are included and must remain visibly
  labeled; this human view is deliberately not the narrower model-recall filter.
- Evidence: the same two parameters, invoked separately on explicit selection.
  Returns `record_id`, `record_revision`, and the record's declared `sources`
  citation objects, including declared reference strings and any already-bound
  quotes/digests. A reference can contain a URL or path; it remains inert text.
  The reader never dereferences it, fetches attachments, or returns the full
  captured source snapshot.

All replies include `lane`, `snapshot_key`, `inspection_only:true`, and
`content_role:untrusted_memory_data`. Evidence additionally declares
`source_content:citation_quotes_only`. A reference without a quote remains a
reference, not fetched or verified evidence. Existing registered snapshot quotes
have byte-consistency checks; those do not prove authorship or semantic truth.
Manually declared citations remain unverified claims.

## Freshness and eligibility

Every endpoint resolves current native ownership and performs its entire read
inside the native read fence and one existing store transaction. Only approved
records whose entire tracked dependency closure is current, approved, and
same-scope are visible. Withdrawn registered sources and denied dependencies
exclude their descendants. Pending, invalidated and trashed records never become
wiki pages. Foreign and unavailable selected IDs have the same unavailable error.

The opaque snapshot covers exact owner/binding, store identity, current-scope
records, current-scope captured-source lifecycle/digests, and project consent.
It does not expose a global store revision or other-chat activity. Any covered
change requires a fresh index; a snapshot string is not authorization. No locks
are held by the UI between requests, and already returned/displayed data cannot
be retracted. Clear stale pages/evidence on scope, connection or snapshot change.

Index responses are capped at32KiB and selected page/evidence at64KiB serialized
JSON. Existing store count/4MiB load limits still apply; no fixed-latency claim is
made. Reads create no records, grants, sources, indexes, caches or setup state.
The reader serializes unload against admitted reads. It inherits the existing
trusted-local-filesystem assumptions and does not sandbox hostile local edits.
