# Reviewed reference drafts from authorized records

This deterministic foundation creates a **reference draft**, not a proven
procedure or an installable SKILL.md. It does not call a model, send data to a
provider, register a skill, write to native skill directories, alter prompts,
install packages or execute quoted instructions. There is no automatic pipeline.
A later conversion to an executable/native skill would require a separately
reviewed design and consent.

Choose one explicit private or project wiki lane, then one to four currently
approved records. Existing wiki dependency/source-activity checks apply.
Sensitive approved records can be selected for this human-facing workflow and
remain labeled sensitive. Project access requires the current catalog/binding
and version-2 inspection consent; saving also requires native control/write
capability. Selected material never crosses lanes or principals. Saved project
recipes are additionally restricted to their creator canonical chat, rather than
newly shared with all chats using that project.

## API

`draft.private.*` and `draft.project.*` expose:

- `preview`: `record_ids` (1–4 unique), `expected_snapshot` from the wiki index,
  `title` (trimmed, at most120 UTF-8 bytes), optional `include_evidence` (boolean,
  defaultfalse). Returns the entire deterministic `markdown`, its UTF-8 `sha256`,
  selected IDs, sensitivity, evidence flag, lane, `preview_token`, `draft_id`,
  `expires_in_seconds:300`, retention notice, `installable:false`, and
  `retains_body:false`. Preview writes nothing.
- `save`: `preview_token`, `confirm:true`. Returns `saved:true` and draft summary.
  Confirmation is specifically for retaining the recipe metadata. It is not
  permission to install, execute, export or send selected content elsewhere.
- `list`: no selectors. Returns this chat's `drafts` summaries and lane.
- `get`: `draft_id`. Returns summary plus `available:true`, regenerated Markdown
  and hash, or `available:false` with `reason:references_changed` and **no body**.

Summaries contain ID, title, timestamp, selected record IDs, evidence flag and
sensitivity. No arbitrary profile/root/scope/source path is accepted. Native
transport session fields are not treated as identity. These are authenticated
human-facing RPCs, not a cryptographic guarantee that a human clicked; trusted
clients with the same host capability can invoke them. No model tool is added.

## Rendering and retention

The fixed heading states that this is not an installable skill. All selected
text, titles, classification and optionally declared citations appear as JSON
quoted data, with backticks, dollar signs and angle brackets escaped. This avoids
introducing native skill preprocessing tokens through source text. It does not
make malicious instructions semantically harmless. No source statement becomes
trusted policy or an authenticated user fact. Declared quotes/references are not
fetched. Enabling evidence includes only existing citation objects, never an
additional full captured-source lookup.

Only an immutable recipe is saved: title, IDs, revisions, record digests,
creator/scope/binding metadata, timestamp, sensitivity, evidence flag and output
hash. **No generated Markdown, record body or source body is duplicated.** Titles
and IDs can themselves be sensitive metadata; recipes currently have no purge
endpoint, expiry or automatic eviction. There are at most16 recipes per backing
principal store, counting other chat scopes without exposing their counts.
Original records, sources, transcripts and their existing retention are untouched.

Every body read requires current authorization and exact selected record digests,
approval, dependency closure, and active registered sources. Project binding
changes withhold old recipe bodies. A correction, withdrawal or deletion cannot
be bypassed by reading the old recipe. The recipe remains listed for
reconciliation, but is not a historical body backup. Existing whole-store
validation and4MiB capacity limits remain in force. No hostile-filesystem-owner
or cryptographic audit guarantee is claimed.

## Confirmation and uncertainty

At most16 in-memory preview tokens exist per service, expire after300 seconds,
and are cleared on unload. Tokens retain recipe metadata, not rendered bodies.
They bind exact immutable native owner and wiki snapshot. Another creator cannot
consume a token. A same-owner attempt consumes it before publication and is never
automatically retried; confirmationfalse does not consume it. Native writer
exclusion and the store transaction recheck references before the recipe commit.
Unload serializes with admitted service operations, not a cancellation of an
already admitted write.

The complete generated draft is bounded to16KiB UTF-8. Oversized drafts and known
store-capacity failures are refused before preview confirmation. Source changes
or storage failures can still race afterward. A publication error or lost reply
can occur after a recipe committed. Do not resend blindly: use the preview's
`draft_id` in list/get to reconcile. Tokens are not a durable global deduplication
system; deliberately creating a new preview can create another recipe. Native
uncertain-outcome rules apply. Already displayed material cannot be retracted.
