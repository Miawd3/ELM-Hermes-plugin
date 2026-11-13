# ELM for stock Hermes — candidate

## Install

Use a fresh disposable Hermes profile for this candidate. In **Plugins → Install from repository**, paste:

```text
https://github.com/Miawd3/ELM-Hermes-plugin.git#stock-plugin
```

Or run:

```sh
hermes plugins install "https://github.com/Miawd3/ELM-Hermes-plugin.git#stock-plugin"
hermes plugins enable elm
```

Restart Hermes. In Desktop, open **Capabilities → Plugins**, find **ELM**, and switch it **On**. This Desktop toggle can remain off even after CLI activation. Open a saved local chat and type `/elm on`. Settings: **Settings → Plugins → ELM**; model choices: **Settings → Models → Auxiliary**. Do not install the old `elm/` directory for this route.

**Do not apply a host patch.** This candidate uses stock plugin APIs, qualified against Hermes commit `126980e47b826963b26bf57d210106d849322f8a`. This is not full Desktop/Windows or live-provider acceptance. Back up your existing profile first; do not overwrite an older ELM installation. It uses a new database and does not migrate legacy data.

## Quick use

- `/elm save user I prefer short answers` saves a fact you explicitly supplied.
- Ask the model to use `elm_memory` to propose facts or search saved records.
- `/elm pending`, then `/elm approve <id>` reviews a model proposal.
- `/elm project MyGame` explicitly shares project facts with other local chats enrolled in `MyGame`.
- `/elm user on` explicitly shares user facts with other local chats that enable user memory.
- `/elm capture on` saves completed text turns locally. Off by default.
- `/elm agent on` permits query-planning calls; `elm_memory` with `use_agent=true` or `/elm agent-search <query>` uses the dedicated search planner. Off by default.
- `/elm organizer on`, then `/elm organize <source-id>` sends that selected captured source to the organizer. It creates exact-excerpt drafts for review, not approved facts.
- Desktop **Settings → Plugins → ELM** provides concise active-chat controls.
- Choose separate models in **Settings → Models → Auxiliary → ELM Search / ELM Organizer**.
- `/elm off` stops access/capture in this chat. It keeps saved data.
- `/elm help` lists all commands.

## What is implemented

Plugin-owned profile-local SQLite storage; separate `user`, `project`, `reference` and `skill` record kinds and tags; pending/approved/trash states; manual review, edit and restore; source-linked proposals; explicit per-chat project/user scope sharing; opt-in turn capture; local keyword recall; a bounded dedicated search query planner and source organizer through official `ctx.llm`; native model-assignment slots; concise desktop settings; six original progressively loaded skills.

The planner sends **only the search query**, never the memory database, and returns up to two alternative queries. Scope and local search stay deterministic. Original query is always searched. Failure falls back to local search. At most one plugin completion per explicit agent search, with 192 output tokens and 15-second timeout. Hermes/provider routing may have its own retries and fees. These limits are **not a dollar spending cap**. Automatic per-turn recall never calls the planner.

## Privacy and limitations

This is local personal-profile memory, **not a multi-user authorization system**. CLI, TUI and Desktop sessions are supported; gateway chats, ACP, background/script calls without a valid local session are refused. The host provides the session ID; model arguments cannot choose it or grant access. New chats, branches and rotated transcript segments need fresh `/elm on` permission. This deliberately fails closed rather than guessing session ancestry.

Without explicit sharing, records stay in their originating chat. Turning on a project or user scope grants that enrolled chat access to that scope's approved records and review operations. Use different Hermes profiles for different people. Capture is plain text and is not guaranteed secret redaction; do not enable it for sensitive credentials. Reads sent into your chat are then subject to Hermes's ordinary transcript/provider handling. Hook recall is not an ephemeral request-only channel.

List views support offsets (`/elm pending 12`, `/elm sources 20`); source text supports offsets (`/elm source <id> 4000`). Lists are live, so concurrent changes can reorder them. Organizer processes the first 4,000 characters of each role per selected source and explicitly reports truncation. It makes one completion request, max 1,600 output tokens, 30-second timeout. Scope revision is pinned across model calls and rechecked before retrieval/commit; changing a setting aborts the pending operation. No claims of a hard monetary budget or mid-flight provider cancellation.

No existing patched-store files are read, deleted or automatically migrated. New storage is `<profile>/plugin-data/elm/stock-v1.sqlite3` and survives plugin update/removal. Keep the previous complete source/data backup. No automatic migration is safe until ownership/scope mappings are reviewed.

## Not in this stock package

- Native chat folders, important-message timeline markers and whole-message bubble labels/styles depended on host patches. They are **not** advertised as stock plugin features.
- Own wiki: removed. The official Hermes Memory Wiki remains independently installed; there is no automatic ELM-record sync.
- Autonomous/background organization, skill creation from long-term data, embeddings and benchmark improvements: not implemented here. Organization is an explicit user action on a selected source; review is required.
- Self-updater: not included. Updates use Hermes's normal plugin manager; no startup core modification.
- ELM does not build a second model picker. It registers two official auxiliary slots, configured through Hermes’s existing model settings. Host-owned routing, credentials and trust checks remain in force.

## Verification

Pinned unmodified Hermes source `126980e47b826963b26bf57d210106d849322f8a`:

- Official `hermes plugins validate`: all checks passed; no private-import/core-override warning.
- Official Plugin Doctor: runtime discovery, import and registration passed (1 tool, 2 hooks).
- 43 standard-library tests passed, including model scope spoofing, no-default egress, approval, source bounds, gateway refusal and cross-profile storage-factory switching.
- Real stock runtime command-dispatch/tool-registry/hook integration passed with network blocked; both auxiliary task slots registered.
- Real public `plugin_db` smoke test passed with two disposable profile homes and reopening persisted data.

No live provider request or paid model call was made. Desktop settings JavaScript passes syntax checking and 19 owner/status guards plus 6 shipped UI contract checks (connection/socket swaps, focused-owner mismatch, stale responses). It uses the captured gateway socket and explicit profile/session; it never falls back to a different source. No visual acceptance is claimed. No full Desktop/Windows walkthrough of this newly scoped package has been performed. The older patched candidate's 176/74 tests and screenshots **do not qualify this new package**.

## Real Desktop follow-up

The pinned GitHub installation succeeded in a fresh disposable profile; installed files matched the source manifest. In an unmodified stock Desktop build, enabling ELM through Capabilities registered its settings page, and the page correctly refused configuration without a saved local chat.

A no-provider session could not be established in this environment: the host logged `storage_unavailable / invalid policy`, followed by `Gateway ticket bootstrap failed` on unrelated APIs. This does **not** establish that ELM caused those failures. Saved-session controls, search and model-selection behavior remain unverified in the actual Desktop UI. No paid provider calls were made.
