## Pre-grant help and diagnostics (candidate)

`/elm help` lists commands without reading memory or opening storage. `/elm diagnostics` reports only whether the supplied current-chat identifier and surface look supported. It does **not** inspect the database, verify an active profile/grant, or report enabled settings, memory counts, or other chats. `authorization: not_checked` is not permission to use memory. After granting the exact chat using the CLI in the correct Hermes profile, `/elm status` remains the permission-gated settings check.

These two informational commands do not fix a missing or expired grant. All memory operations retain their existing authorization. Unsupported contexts may read static help but cannot gain memory access. Other denied memory commands retain the existing storage-opening behavior; this change only guarantees non-mutating help/diagnostics and malformed-command parsing.

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

Restart Hermes. In Desktop, open **Capabilities → Plugins**, find **ELM**, and switch it **On**. This Desktop toggle can remain off even after CLI activation. In classic CLI/TUI, type `/elm on`. Current unified Desktop sessions need the explicit one-chat grant below. Settings: **Settings → Plugins → ELM**; model choices: **Settings → Models → Auxiliary**. Do not install the old `elm/` directory for this route.

**Do not apply a host patch.** This candidate uses stock plugin APIs, qualified against Hermes commit `126980e47b826963b26bf57d210106d849322f8a`. This is not full Desktop/Windows or live-provider acceptance. Back up your existing profile first; do not overwrite an older ELM installation. It uses a new database and does not migrate legacy data.

## Desktop: grant one chat from your terminal

Hermes reports Desktop, TUI and editor (ACP) chats all as `local`, so ELM cannot tell which app is asking. It therefore waits until you grant **one exact chat** from a terminal on this computer. The model can never grant access.

1. In Desktop, send any message in the chat (or `/elm status`) so the chat is saved. **Settings → Plugins → ELM** shows the exact command for the focused chat.
2. In a terminal, run it, for example:

```sh
hermes elm grant                 # lists your recent chats; type the number of this chat, then y
hermes elm grant <chat-id>       # or grant an ID directly
hermes -p work elm grant         # for a named profile
```

3. Back in Desktop, select **Refresh** in the ELM settings page, or send `/elm status`.

Default: this chat only, 24 hours, no sharing, no capture, no model calls. Options: `--project NAME`, `--user`, `--capture`, `--agent`, `--organizer`, `--hours N` (max 168), `--yes` (skip the prompt). Renewing replaces all options; omitted ones reset to off. `hermes elm revoke [<chat-id>]` turns ELM off for a chat and keeps its data. `hermes elm sessions` lists recent chats with their IDs.

Any authenticated client connected to that **same chat** shares the grant, including an ACP editor client. No other chat is enrolled; new chats and `/branch` copies need their own grant.

The older `python -m elm_plugin.local_grant ... --expect-home` helper still works but is no longer needed: `hermes elm` runs inside the profile Hermes selected.

## Long chats, deleted chats and automatic recall

- **Compression:** when Hermes compresses a long chat into a new session ID, ELM moves that chat's grant, settings and chat-only memory to the new ID automatically.
- **Deleting a chat** (not archiving) permanently removes its chat-only memories, captured sources and settings. Project and shared user memories stay. Archived chats keep everything. Deletes made from a process where ELM is not loaded can be missed; nothing else is affected.
- **Automatic recall** ignores greetings, acknowledgements and slash commands, searches only meaningful words (common words like "the" or "my" are dropped), requires a note to match enough of them, and does not inject the same note twice in a chat until Hermes compresses it. Explicit `/elm search` and the `elm_memory` tool still match any word.

## Focused-chat memory manager (experimental)

**Windows/Desktop visual verification is still pending. Use a disposable test profile first.**

After an exact-chat grant, open **Settings → Plugins → ELM** with that chat focused. The **Memory in this chat** section lists approved records, drafts needing review, and recoverable Trash. Save a note, approve a draft, move a record to Trash, or restore it to review. No paid model call is needed for these actions.

**Kind is not sharing.** User/project/reference/skill describes the record. The destination beside the save button shows where it will actually go: this chat only, the granted project, or shared user memory in this profile. Without the matching grant, user/project notes stay chat-only. Shared records can be changed by other enrolled chats. This manager does not grant permissions, install skills, search other profiles, or implement native chat folders.

Approval and Trash changes reject records edited since the displayed snapshot. Writes reject changed policy or database identity instead of silently changing destination. Switching chat/profile/connection hides the old manager and discards stale replies. Pages contain at most 12 records; concurrent additions may shift pagination. Refresh when needed. Restore means **pending review**, not automatic approval. Trash does not erase already-delivered model context or copied notes.

This candidate passed backend and Desktop contract tests, including independent race review. Actual installed Windows/React visual behavior still requires testing. The supplied HTML is a synthetic component preview, not a host screenshot.

## Quick use

Scope-setting slash commands below apply to classic CLI/TUI. For unified Desktop, use the local grant options above.

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

Plugin-owned profile-local SQLite storage; separate `user`, `project`, `reference` and `skill` record kinds and tags; pending/approved/trash states; manual review, edit and restore; source-linked proposals; explicit per-chat project/user scope sharing; opt-in turn capture; local keyword recall; a bounded dedicated search query planner and source organizer through official `ctx.llm`; native model-assignment slots; concise desktop settings; seven original progressively loaded skills.

The planner sends **only the search query**, never the memory database, and returns up to two alternative queries. Scope and local search stay deterministic. Original query is always searched. Failure falls back to local search. At most one plugin completion per explicit agent search, with 192 output tokens and 15-second timeout. Hermes/provider routing may have its own retries and fees. These limits are **not a dollar spending cap**. Automatic per-turn recall never calls the planner.

## Local search ordering

Search ranks permitted records by the number of **distinct query words matched**, then by most recent update. Ranking happens before the result limit, so many recent one-word matches no longer automatically bury an older record matching the whole query. Substring matching (including Unicode and literal underscores), status filters and scope grants are preserved. Unqueried list views remain newest-first.

This is a targeted lexical fix, not semantic confidence: stopwords and keyword-rich irrelevant notes can still misrank. It does not solve paraphrases, long-record packing or prove benchmark improvement. Ranking adds work; the reproducible synthetic latency probe in `tests/search_ranking_probe.py` records that tradeoff. No new model calls or storage migrations are introduced.

## Draft a skill from selected long-term notes

1. `/elm list` to find approved record IDs in this chat's permitted scopes.
2. `/elm draft-skill "Release checks" <record-id> [more IDs]` selects one to four records.
3. `/elm pending` to read the draft; `/elm skill-sources <draft-id>` shows saved source excerpts.
4. Edit and review it. `/elm approve <draft-id>` approves a **memory record only**, not installation or execution.

This deterministic, no-model operation creates a **pending worksheet** with a trigger/procedure/verification scaffold and exact source excerpts, not a polished autonomous skill. It never registers a new runnable skill, writes a skill file, calls a provider or silently turns facts into authoritative instructions. Each excerpt is bounded to 1,200 UTF-8 bytes; truncation is reported. You must finish and test the procedure before manually installing it through your chosen skill manager.

The worksheet and provenance snapshots are saved in the originating chat, including explicitly selected shared-scope excerpts. They are copies, so later edits or withdrawal of the source scope do not erase the draft. Turning ELM off prevents access but keeps its stored data. Do not draft from notes you do not want copied into that chat.

## Official Memory Wiki coexistence

The official `hermes-memory-wiki` catalog plugin (installed ID `memory-wiki`) is separate. Its pinned public contract is read-only: it indexes Hermes session history and `MEMORY.md` / `USER.md`; it does **not** read ELM's database or provide a supported import/sync API. ELM does not create a competing wiki, silently copy records to global prompt notes, or claim synchronization.

If desired, install the official plugin separately with `hermes plugins install hermes-memory-wiki --enable`, then enable Memory Wiki in Desktop Capabilities. Its route is `/memory-wiki`. [Official contract inspected](https://github.com/NousResearch/hermes-official-plugins/blob/e7a218f26db88426ab3e7376f0e000b6e356f5e7/memory-wiki/README.md).

**Important:** ELM facts printed or recalled into ordinary chat can appear in Memory Wiki's history views. ELM's scope grants do not restrict an independently installed plugin reading Hermes history. This is transcript indexing, not ELM database sync.

## Optional inline presentation

**Settings → Plugins → ELM → Inline answer cards** enables app-wide visual cards (off by default). Choose Accent or Plain; the page includes a clearly labelled display example. The `rich-answers` skill documents `::elm-answer{kind="question" title="One choice" text="Which option?"}` with fixed Progress, Update, Answer, Final and Question labels. These are **model-provided labels**, not proof that work completed. Text is bounded and escaped; cards cannot run commands, grant permissions or add model-controlled buttons.

The focused chat can show a small **ELM settings shortcut**, separately toggleable. It opens this plugin's settings only; it is **not a memory-active badge**. These are supported inline transcript and session-row additions, not native whole-message bubbles, folders or importance markers. Visual preferences do not enable memory or model calls.

Actual stock Desktop checks confirmed the row shortcut navigates to ELM settings, its toggle hides it, and enabling cards shows the labelled preview; style selection worked. Real model-generated transcript cards have not been tested with a live provider.

## Privacy and limitations

This is local personal-profile memory, **not a multi-user authorization system**. Classic CLI/TUI and trusted legacy Desktop contexts use explicit chat permission. Unified `local` contexts require the out-of-band exact-session grant above; authenticated clients accessing that same session are indistinguishable. Explicit remote/ACP surfaces and missing sessions are refused, but **ACP exclusion is not guaranteed within a granted unified session**. Model arguments cannot choose the session or issue a grant. New chats, branches and rotated transcript segments need fresh permission. Do not treat local filesystem access as a sandbox against other software running as you.

Without explicit sharing, records stay in their originating chat. Turning on a project or user scope grants that enrolled chat access to that scope's approved records and review operations. Use different Hermes profiles for different people. Capture is plain text and is not guaranteed secret redaction; do not enable it for sensitive credentials. Reads sent into your chat are then subject to Hermes's ordinary transcript/provider handling. Hook recall is not an ephemeral request-only channel.

List views support offsets (`/elm pending 12`, `/elm sources 20`); source text supports offsets (`/elm source <id> 4000`). Lists are live, so concurrent changes can reorder them. Organizer processes the first 4,000 characters of each role per selected source and explicitly reports truncation. It makes one completion request, max 1,600 output tokens, 30-second timeout. Scope revision is pinned across model calls and rechecked before retrieval/commit; changing a setting aborts the pending operation. No claims of a hard monetary budget or mid-flight provider cancellation.

No existing patched-store files are read, deleted or automatically migrated. New storage is `<profile>/plugin-data/elm/stock-v1.sqlite3` and survives plugin update/removal. Keep the previous complete source/data backup. No automatic migration is safe until ownership/scope mappings are reviewed.

## Not in this stock package

- Native chat folders, important-message timeline markers and whole-message bubble labels/styles depended on host patches. They are **not** advertised as stock plugin features.
- Own wiki: removed. The official Hermes Memory Wiki remains independently installed; there is no automatic ELM-record sync.
- Autonomous/background organization, automatic runnable-skill generation/installation, embeddings and benchmark improvements: not implemented here. Selected-memory skill worksheets are explicit drafts, described above. Organization is an explicit user action on a selected source; review is required.
- Self-updater: not included. Updates use Hermes's normal plugin manager; no startup core modification.
- ELM does not build a second model picker. It registers two official auxiliary slots, configured through Hermes’s existing model settings. Host-owned routing, credentials and trust checks remain in force.

## Verification

Pinned unmodified Hermes source `126980e47b826963b26bf57d210106d849322f8a`:

- Official `hermes plugins validate`: all checks passed; no private-import/core-override warning.
- Official Plugin Doctor: runtime discovery, import and registration passed (1 tool, 2 hooks).
- 0.2.0: 55 standard-library tests passed, including model scope spoofing, no-default egress, approval, source bounds, gateway refusal and cross-profile storage-factory switching. 0.2.1: 132 tests pass, including compaction rotation, chat deletion, recall relevance and the `hermes elm` CLI; the host smoke test passes against Hermes 0.23.1 source (`3b42157`).
- Manually constructed stock command-dispatch/tool-registry/hook integration passed with network blocked; both auxiliary task slots registered.
- Real public `plugin_db` smoke test passed with two disposable profile homes and reopening persisted data.

No live provider request or paid model call was made. Desktop settings JavaScript has identity/socket/profile fencing and shipped contract tests. The older patched candidate's tests and screenshots do not qualify this package.

## Real Desktop follow-up

The pinned GitHub candidate installed in a fresh disposable profile with matching manifest hashes. Its actual unmodified stock Desktop settings page loaded after Capabilities activation. A missing model name initially prevented host session restoration; setting model metadata only, without credentials or inference, allowed a fresh session.

The real unified gateway exposed a command-context limitation that manually constructed dispatch tests missed. After the exact-session local grant implementation was applied to the installed test plugin, real Desktop commands successfully saved and retrieved a synthetic fact with `local_only`, no provider/model; settings loaded; scope expansion was refused; `/elm off` prevented subsequent recall. Screenshots record these actual runs, not a mockup. The host itself was not patched. A second fresh GitHub install of commit `c43d688` matched all manifest hashes. Its final settings page showed the same-session consent note, disabled scope-expansion controls, and working memory-off control. The subsequent off-confirmation wording is separately unit checked. An injected unavailable planner with real stock storage returned deterministic original-query fallback without network access. Automatic model-turn hooks, Windows installation and live search/organizer providers are not yet fully qualified end-to-end. This remains a candidate, not full feature-parity acceptance.
