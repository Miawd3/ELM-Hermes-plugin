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

## Desktop: grant one chat locally

Stock unified Desktop commands currently report only `local`, not a trustworthy Desktop-versus-ACP identity. ELM therefore refuses access until you explicitly grant **one exact session** from a local terminal. This is not one-click activation.

1. In Desktop, send `/elm status` to create/save the chat. An access error is expected before the grant.
2. In a terminal using the **same Hermes profile**, run `hermes sessions list` and copy that chat's full session ID, not its title.
3. Change directory to that profile's `plugins/elm` folder. Using the Python environment that runs Hermes:

```sh
python -m elm_plugin.local_grant "EXACT_SESSION_ID" --allow-session-clients
```

Default: this chat only, 24 hours, no shared user/project scope, no capture, no model calls. Any authenticated client that can operate this **same session** shares the permission, including an ACP client; this is not proof of a human. No other session is enrolled. Do not grant sessions you do not trust.

Use `/elm save reference A test fact`, then `/elm search test`. `/elm off` revokes access and keeps data. To renew or change permissions, rerun the local command with the complete desired options: `--project "MyGame"`, `--user`, `--capture`, `--agent`, `--organizer`, `--hours 24` (maximum 168). Omitted options reset to off. Agent/organizer options permit provider calls and fees; capture saves plaintext. `--revoke` disables a session without renewing it. Read `--help` first.

Desktop settings show current permissions and can switch memory off. They cannot enlarge a unified session's grant. New chats and branches need separate explicit grants. This temporary bridge does not modify Hermes or its policy receipts.

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
- 55 standard-library tests passed, including model scope spoofing, no-default egress, approval, source bounds, gateway refusal and cross-profile storage-factory switching.
- Manually constructed stock command-dispatch/tool-registry/hook integration passed with network blocked; both auxiliary task slots registered.
- Real public `plugin_db` smoke test passed with two disposable profile homes and reopening persisted data.

No live provider request or paid model call was made. Desktop settings JavaScript has identity/socket/profile fencing and shipped contract tests. The older patched candidate's tests and screenshots do not qualify this package.

## Real Desktop follow-up

The pinned GitHub candidate installed in a fresh disposable profile with matching manifest hashes. Its actual unmodified stock Desktop settings page loaded after Capabilities activation. A missing model name initially prevented host session restoration; setting model metadata only, without credentials or inference, allowed a fresh session.

The real unified gateway exposed a command-context limitation that manually constructed dispatch tests missed. After the exact-session local grant implementation was applied to the installed test plugin, real Desktop commands successfully saved and retrieved a synthetic fact with `local_only`, no provider/model; settings loaded; scope expansion was refused; `/elm off` prevented subsequent recall. Screenshots record these actual runs, not a mockup. The host itself was not patched. A second fresh GitHub install of commit `c43d688` matched all manifest hashes. Its final settings page showed the same-session consent note, disabled scope-expansion controls, and working memory-off control. The subsequent off-confirmation wording is separately unit checked. An injected unavailable planner with real stock storage returned deterministic original-query fallback without network access. Automatic model-turn hooks, Windows installation and live search/organizer providers are not yet fully qualified end-to-end. This remains a candidate, not full feature-parity acceptance.
