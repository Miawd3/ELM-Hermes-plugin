# Private captured sources and reviewed exact excerpts

This r12 foundation captures explicitly submitted PRIVATE-chat text and creates
human-reviewed exact excerpts as pending records. It is not a semantic extractor,
model invocation, document parser, web fetcher or verification service. No paid
calls, external URL fetching, legacy adoption or project-source sharing occurs.

## What integrity means

SHA-256 covers the UTF-8 encoding of the text received and stored by this API.
It does not cover original PDF/DOCX/file bytes, clipboard content before a client
changed it, transport JSON, or a live URL. The backend neither normalizes Unicode
nor changes newlines. A browser paste may already have normalized content before
sending it. Reference and author fields are user declarations, never fetched or
authenticated. A matching digest proves internal captured-text consistency, not
semantic truth or authorship. Supported APIs never edit captured text; this is
not a tamper-proof audit against an owner modifying the local filesystem.

Every snapshot belongs to the current canonical private chat inside the existing
principal-qualified private store. Snapshot text, metadata and records use one
manifest and the same native ownership and store locks. Source operations never
read another private chat or project generation. No arbitrary paths are accepted.

## RPC contract

All names below start with `private.`. Unknown authority/root/scope fields are
refused; host-authenticated `session_id` remains a transport field.

- `source.preview {title,text,reference?,author?,sensitive?}` validates submitted
  text and returns `preview_token`, `sha256`, UTF-8 byte count, Unicode codepoint
  count, sensitivity, expiry and a capture notice. Reference/author default to
  empty strings. Sensitivity defaults to **true** and is user-declared, not
  detected; explicitly selecting false is part of reviewed capture.
- `source.apply {preview_token,confirm:true}` returns a source summary directly:
  `source_id`, `title`, `sha256`, `revision`, `content_revision`, `state`,
  `sensitive`, `utf8_bytes`, `codepoints`, `created_at`.
- `source.list {limit?,before?}` returns `sources` summaries, `truncated` and
  `next_before`. Limit is 1–32, default 16; only this chat's sources appear.
  Both active and withdrawn sources are listed, so a successful capture can be
  reconciled after a lost response without re-capturing automatically.
- `source.get {source_id}` returns `source` summary plus full `text`, `reference`
  and `author`, marked `content_role:"untrusted_source_data"` and
  `verification:"captured_bytes_only"`. It never silently truncates the source.
- `excerpt.preview {source_id,quote,occurrence?,title?}` finds an exact substring
  of the active snapshot. If more than one overlapping match exists, omission
  of `occurrence` is rejected as ambiguous. An explicit occurrence is a positive
  one-based integer; booleans, zero and unavailable occurrences are rejected.
  The browser supplies no offsets. Returned `start` and exclusive `end` are
  Python Unicode-codepoint offsets, explicitly `offset_unit:"unicode_codepoints"`,
  not JavaScript UTF-16 offsets. No trimming or Unicode normalization occurs.
  The preview includes exact quote, digest, source state revision, occurrence,
  pending candidate and a new confirmation token. Candidate title defaults to
  the source title. Exact future record fields/provenance are validated before
  issuing the token, so known oversized evidence fails before confirmation.
- `excerpt.apply {preview_token,confirm:true}` returns a standard pending record
  directly. Its text is the exact quote, kind/domain are `reference`, basis is
  `source_document`, and sensitivity is inherited from the captured source.
  It is not auto-approved or injected into provider/model context.
- `source.withdraw {source_id,expected_revision,confirm:true}` changes source
  state and invalidates tracked linked active records plus their transitive
  record dependents in the same manifest transaction. It returns source summary,
  affected IDs, `retained_bytes:true` and `purge_available:false`.

Preview tokens are cryptographic, one-use, expire after 300 seconds, and pin the
exact native owner and immutable store identity. Excerpt previews additionally
pin source state revision and captured digest. A foreign chat cannot consume
another chat's token. Tokens are consumed before the single write attempt;
uncertain outcomes never restore them or trigger automatic retries. Unload clears
unused tokens and waits for admitted operations. A supported private store must
already be explicitly initialized; source previews create nothing.

## Provenance and eligibility

Captured references use the distinctive reserved scheme
`elm-snapshot-v1:<source_id>:<start>:<end>`. Their record source entry contains the
exact quote, captured SHA-256 and `revision:1`. `content_revision` is always 1:
captured content does not change. Source `revision` is a separate state/CAS value,
1 while active and 2 after withdrawal. If a reserved citation supplies a revision,
it must be content revision 1, including after withdrawal; invented versions are
refused. Omission is accepted only when all other exact citation checks pass.

Every private manifest load/save validates reserved references in active AND
retained records against the same-chat registry, span, quote and digest. Generic
manual create/correct cannot forge cross-chat citations, false hashes or lower a
sensitive snapshot's sensitivity while retaining that citation. Ordinary manually
declared references, including old `snapshot:` strings, remain declared-only.
A pre-existing collision with the new reserved `elm-snapshot-v1:` scheme fails
closed rather than being silently reinterpreted. New project create/correct
reject this PRIVATE reserved scheme without looking up private data; ordinary
project references are unchanged. There is no private-to-project copy operation.

A successful withdrawal makes tracked linked records ineligible. Approval and
recall refuse withdrawn snapshot references. Restoration of a recovery envelope
containing such a reference also refuses atomically and keeps the retained
archive intact. Human inspection still permits reconciliation of retained source
text. Source withdrawal is not source erasure, transcript redaction or an
universal claim retraction: it cannot invalidate arbitrary unlinked manual copies,
restatements, already-returned context, transcripts, exports or backups.

Later explicit manual correction may author different record text. A valid source
citation then proves only its captured quote, not that the corrected statement is
an exact excerpt or true. Removing the citation removes that captured-source
claim. Ordinary explicit approval remains a separate human action.

## Bounds and failure behavior

- At most 64 retained snapshots, **including withdrawn** snapshots.
- Source text at most 65,536 UTF-8 bytes; title 512 bytes, reference 2,048 bytes,
  author 512 bytes. Excerpt quote at most 8,192 UTF-8 bytes and title 512 bytes.
- Existing private record rules also cap the entire serialized source-metadata
  array at 8,192 bytes with ASCII JSON escaping. Citation overhead and escaping
  can make the effective quote bound lower. Preview refuses, never truncates.
- Source list responses are capped at 32 KiB; get returns the full source or
  refuses above 512 KiB, allowing for JSON escaping of captured UTF-8 text.
- At most 64 outstanding source/excerpt previews and 8 MiB aggregate serialized
  preview payload; source and excerpt previews share that budget.
- Existing private-store bounds still apply: 512 active-plus-retained records
  and 4 MiB of serialized manifest, now including all captured sources. Capacity
  may be reached before the nominal snapshot count/text caps. There is no eviction,
  compaction, automatic adoption, repair or permanent purge.

Writes validate the complete proposed manifest and exact serialized size before
replacement. Even withdrawal can be refused if its revision/timestamp metadata
would exceed capacity: a failed response is not proof the source was withdrawn.
Read back source state and affected records after any failed or uncertain write.
Never silently retry capture, excerpt creation or withdrawal. The native fence
and external manifest are not a cross-database atomic commit; platform-specific
file durability and known-symlink defenses do not establish a hostile-filesystem
security boundary.

The r12 manual project creation UI supplies `expected_consent_revision` from its
reviewed project status. The backend checks it when provided; omission remains
accepted for r10 trusted-current-consent client compatibility, not proof of a
reviewed consent generation. No project source permissions were added.
