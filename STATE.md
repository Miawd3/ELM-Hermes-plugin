# ELM for Hermes — current state

Short handoff for the next session. Keep this file current instead of adding new receipt files.

## What is live

- **Product:** `stock-plugin/` (plugin id `elm`, version 0.2.1-preview, requires Hermes >= 0.23.1). No Hermes core changes.
  User docs: `stock-plugin/README.md`; tester guide: `stock-plugin/TESTING.md`; technical notes: `stock-plugin/docs/DETAILS.md`.
  `elm/` + `integration/host.patch` are the archived patched-host prototype; do not develop there.
- **User machine (Windows, Hermes 0.23.1 `3b42157`):** 0.2.1 was copied directly into
  `%LOCALAPPDATA%\hermes\plugins\elm` and `desktop-plugins\elm` on 2026-11-14.
  The previous install (GitHub `0b50a49`) plus the (empty) database are backed up in
  `plugin-data\elm\backup-before-0.2.1-20261114\`. `.install-metadata.json` still says
  `0b50a49`: running `hermes plugins update elm` before this branch is pushed would replace 0.2.1 with GitHub `main`.
- **Branch pushed:** `elm-stock-fixes-20261114`, draft PR https://github.com/Miawd3/ELM-Hermes-plugin/pull/1 (not merged; owner decides).
  Testers install from `main`, so it must be merged to `main` before sending TESTING.md to anyone.
- **0.3.0-preview (2026-11-14):** branch `elm-0.3-provider-routing`, draft PR https://github.com/Miawd3/ELM-Hermes-plugin/pull/2
  stacked on #1. Adds the memory-provider slot (`memory.provider: elm`, `elm_plugin/memory_provider.py`,
  `serving.py`) and memory-aware routing (`delegation.backend: elm`, `elm_plugin/routing.py`, schema 4).
  An independent privacy review found 10 defects; all fixed with regression tests (175 tests).
  Live-verified on `elmtest`: recall indicator, elm_memory in memory-slot mode, routing learns only in
  granted chats, purge on delete. Remaining low-risk notes: route_task reads the calling chat via
  `HERMES_SESSION_ID` (os.environ fallback if a context var is unbound); shared Desktop sessions capture
  every participant's turns (same as hook mode); a locked DB can delay route_task by the busy timeout.
- **Released 2026-11-14:** PR #1 and #2 merged to `main` (`005f52c`); tags `v0.2.1-preview` (`99d5f7b`) and
  `v0.3.0-preview` (`005f52c`). Fresh clone of main: 175 tests + 4 JS checks pass, manifest matches;
  `hermes plugins validate --install-deps` passes; installing from GitHub at that sha works.
- **Catalog submitted:** https://github.com/NousResearch/hermes-agent/pull/155965 (one file,
  `plugin-catalog/elm.yaml`, pinned to `005f52c`; copy in `catalog/elm.yaml`), from the fork
  `Miawd3/ELM-hermes-agent`, branch `plugin-catalog-add-elm`. Waiting for CI (fork workflows may need a
  maintainer's approval) and a Nous maintainer's review. Any change to ELM after this needs a new sha in
  that entry (a new reviewed PR); bump `version` with it.
- **Default profile** still runs 0.2.1 copied by hand (`.install-metadata.json` says `0b50a49`).
  Now safe to update: `hermes plugins update elm` (pulls main = 0.3.0-preview). Not done yet.
- **Test profile:** `elmtest` (DeepSeek `deepseek-v4-flash`, `memory.provider: elm`, `delegation.backend: elm`
  with agents quick/careful) runs the 0.3 build; the default profile still runs 0.2.1. Delete with
  `hermes profile delete elmtest`.

## Architecture (stock plugin)

General Hermes plugin: `elm_memory` tool, `/elm` slash command, `hermes elm` CLI,
hooks `pre_llm_call` (automatic recall), `post_llm_call` (opt-in capture), `post_compaction`
(session-ID rotation), `on_session_delete` (purge chat-only data), two auxiliary model slots
(`elm_search`, `elm_organizer`), 7 skills, Desktop settings page + inline cards + row shortcut.
Storage: `<profile>/plugin-data/elm/stock-v1.sqlite3` via `plugins.plugin_storage.plugin_db`.
Unified Desktop/TUI/ACP chats report `local`, so they need `hermes elm grant` (one exact chat, expiring).

## 0.2.1 changes (this branch)

1. Compression could rotate a chat to a new session ID → ELM lost its grant and chat memory. Fixed with
   `stock_session_alias` + `post_compaction`.
2. Deleted chats kept private memory. Now purged on `on_session_delete` (not on archive).
3. Automatic recall matched stopwords and re-injected the same notes every turn. Now: trivial prompts
   skipped, stopwords dropped, coverage threshold, per-chat dedupe (cleared on compaction).
4. Every DB open re-ran DDL and took a write lock. Now schema setup is gated by `PRAGMA user_version`.
5. `hermes elm grant|revoke|sessions` replaces the PowerShell/`python -m ... --expect-home` routine
   (legacy helper still works). Desktop shows the exact command using the stored session ID.
6. Multimodal turns now captured/recalled from their text parts.
7. `hermes elm doctor` (versions, paths, counts only) for bug reports; local-chat denials now include a `hint` with the grant command.
8. User README rewritten for outside testers; TESTING.md checklist (17 steps) + report template; CHANGELOG.md.

## Verified on the owner's Windows PC (2026-11-14, Claude Code)

- Unit tests: 136 Python OK with Hermes's Python 3.14 (after a test-only fix: 21 tearDown errors from open
  SQLite files, also present on `main`); 4 Desktop JS checks pass.
- Real `hermes plugins validate` on the installed plugin: all checks pass. `hermes elm doctor`: Storage ok, schema 2.
- Live, `elmtest` profile, driven through the gateway like Desktop (`elm-test-mcp/run_checklist`, 12/12):
  ungranted chat refused with grant hint; CLI grant; `/elm save`; automatic recall with DeepSeek answered
  4411 with no tool calls; trivial "thanks" gets a normal reply; other chat refused; `/elm off` blocks;
  re-grant keeps notes; `hermes sessions delete` purges chat-only notes (1 → 0) via `on_session_delete`.
- Real compression (10 → 8 messages): grant stays on, the note is still searchable, and the model still
  answers 4411 afterwards. Deleting a compressed chat also purged its note and grant.
- Test fact is now "The test lighthouse has 4411 steps" (was a "door code", which DeepSeek refused to
  repeat as a credential). With this wording DeepSeek sometimes also calls `elm_memory` itself; automatic
  recall still injects the note (3 of 6 terms match, 3 needed), so that is the model double-checking.

## Not verified yet

- Compression that **rotates** the session ID (the `stock_session_alias` path): Hermes 0.23.1 compressed in
  place in the gateway test, so the ID never changed. Still unit-tested only.
- Desktop delete button itself (HTTP `DELETE /api/sessions/{id}`); it fires the same state-layer hook as the CLI delete.
- UI steps 2, 12, 13 (settings page, memory manager, inline cards) in Hermes Desktop.
- `hermes elm sessions` against a real `state.db` (unit-tested with a stub; it degrades to `hermes sessions list`).

Test-helper fixes (in `Documents\Hermes\workspace\elm-test-mcp`, not in this repo): the gateway has no
`session.delete` RPC (use `hermes sessions delete`); `prompt.submit` with `finite`/`unattended` is refused;
a new connection must `session.resume` a chat before submitting prompts.

## Next steps (agreed direction)

1. Owner spot-checks UI steps 2, 12, 13 in Desktop on `elmtest`, then merge to `main` and send TESTING.md to testers.
2. Decide grant model: keep terminal-only, or allow `/elm on` + in-chat confirmation (`ctx.ask_choice`).
3. Move recall/storage into the `MemoryProvider` slot (`memory.provider: elm`) for prefetch, `on_pre_compress`, `on_session_end`, recall indicator.
4. Agent routing as a `DelegationProvider` plugin + routing/orchestration skill.
5. Important-messages panel (plugin) + small generic Desktop SDK contribution for per-message actions/jump.
