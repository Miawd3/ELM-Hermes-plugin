# Separate search and organizer model preferences

This slice restores **selection intent**, not operational model routing. Each
current canonical chat can save two independent declared preferences:

- **search**: a future model-assisted query/retrieval role; not a web-search
  engine setting and not today's deterministic scoped record recall.
- **organizer**: a future extraction/curation role; not permission to organize,
  rewrite or approve records, and not today's deterministic reference drafts.

Both remain unavailable for dispatch. Saving does not change Hermes's ordinary
chat model, auxiliary task configuration, provider credentials, fallback policy,
recall/capture consent, project binding or any other chat's preferences. Null
means unset, **not** inherit the ordinary model or silently fall back. There is
no profile-wide/global default in this slice. Native profile and principal
ownership isolate the current-chat metadata.

## Why plain declared fields

Native `agent/plugin_llm.py` gates provider/model overrides through plugin trust
flags and delegates to `agent/auxiliary_client.py`, which includes provider
fallback and retry handling (`_ladder_provider_fallback`). It is not an exact
recipient-pinned, no-fallback egress contract. Existing native model pickers
request model options on mount; this workflow does not invoke that catalog or
assume discovery is free of provider/credential activity. No native credential
or model resolver is called. Previously qualified local-only transport tests do
not establish a configured production credential route.

The three fields are therefore unverified declarations, not available-provider
choices: `provider`, `model`, and `endpoint`. No model, network, DNS, secret-store,
API-key lookup or capability probe occurs. The app must display
`dispatch_supported:false` and `external_egress_enabled:false`, including after a
successful save. It never enables the ordinary LLM facade as a fallback.

## API and confirmation

All methods are under `model_preferences`:

- `status {}` returns `initialized`, `setup_required`, per-chat `revision`
  (zero when unset), opaque `context_key`, `roles:{search,organizer}`, both false
  capability flags, `scope:current_chat`, `reason:routing_unavailable`, and notice.
  A missing private store is reported without creating it. An existing validated
  principal store counts as initialized even if this chat has no metadata scope.
- `preview {role,selection,expected_revision,expected_context}` accepts one role
  and either null or the exact three-field selection. Existing explicit private
  setup is required. The result has `preview_token`, `expires_in_seconds:300`,
  role, canonical proposed `selection`, `previous_selection`, notice and the
  false capability flags. A no-op is refused. Preview stores no preference.
- `apply {preview_token,confirm:true}` saves that one role and increments only
  the current chat's settings revision. A confirmed save may create only this
  chat's metadata scope inside an existing validated principal store; it never
  creates/adopts a missing root or requires an unrelated record. Returns `saved:true,status` directly
  from the committed candidate, without a second fallible status read.

Sixteen in-memory previews are allowed per service; they expire after300 seconds
and unload clears them. A foreign chat cannot consume the original chat's token.
The owning attempt consumes it before native publication, which rechecks exact
owner, store and settings context in the same transaction. Stale settings,
changed native authority or replay refuse. Confirmationfalse does not consume.
A lost reply or postcommit fence error may leave the preference saved: refresh
status to reconcile, never blindly retry. Unload serializes with admitted calls.

## Input and storage limits

Provider labels are1–64 ASCII letters/digits/dot/underscore/hyphen, beginning with
an alphanumeric character. Model identifiers are1–128 of those characters plus
slash and colon. Endpoint strings are at most256 ASCII characters and require
HTTPS, a valid ASCII hostname, and optional port1–65535. No userinfo, query,
fragment, backslash, whitespace/control character, percent escape or IPv6 literal
is accepted. Host case and explicit port spelling are canonicalized in preview.
The current narrow path allowlist is:

- `/chat/completions`
- `/v1/chat/completions`
- `/api/v1/chat/completions`
- `/openai/v1/chat/completions`

This is a declared-input grammar, **not** proof that any endpoint/provider/model
works. Other protocols/endpoints, effort settings and production adapters are
not supported here. Known credential-looking patterns are refused, but arbitrary
strings cannot be guaranteed secret-free. **Never paste credentials or secrets.**
No key fields are accepted. Validation errors use fixed messages, not rejected
URL or identifier contents.

Preferences are plaintext metadata within the existing principal-private
manifest, with a maximum512 chat entries and its existing4MiB total cap. Preview
checks known capacity before confirmation; final publication checks again.
Clearing a role saves null and a newer revision, not secure erasure of previous
filesystem pages, backups or displayed values. No record bodies are included.
Malformed extensions fail closed rather than being adopted or silently repaired.

Existing native read/publication authorization applies. These human-facing RPCs
are not a cryptographic proof of human interaction. If an unavailable selected
project blocks the native memory fence, explicitly unbind it through the existing
workflow before changing these settings; the preference layer does not bypass
that guard.

Future execution still requires a separate reviewed recipient/credential
contract, exact selected payload and role, costs/budgets, current consent and
source freshness, durable attempt handling, and no unapproved fallback. This
checkpoint claims no paid-model quality, retrieval accuracy, provider coverage,
price estimate, actual API call, or operational organizer/search integration.

## r32 readiness diagnostics

`status` and the `apply.status` result additionally return `routing_readiness`, with independent `search` and `organizer` entries. Each contains `selection_saved` (only whether a declaration exists), `dispatch_supported: false`, and fixed `blockers` codes. These diagnostics do not probe credentials, endpoints or model catalogs, and saving either role cannot make them ready.

Common blockers are `credential_route_dispatch_binding_unavailable`, `production_pinned_dispatch_unavailable`, `explicit_egress_execution_unavailable`, `provider_compatibility_unverified`, and `enforceable_cost_bound_unavailable`. Search also reports `search_result_contract_unavailable`. These describe the current implementation, not a live provider health check. There is no operational routing improvement in r32; see `MODEL_ROUTING_PRODUCTION_AUDIT.md` for the source audit and required future implementation.

In r33 the pinned host has dedicated enrollment software, but these preference diagnostics do not query it, inspect keys, or establish whether a slot is configured. The renamed blocker means no production dispatch binding consumes an enrolled slot. Stock hosts do not acquire that capability from this plugin.
