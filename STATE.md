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
- **Unpushed branch:** `elm-stock-fixes-20261114` (this session had no push access). Testers install from `main`, so it must be merged to `main` before sending TESTING.md to anyone.

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

## Not verified yet

- Real Windows Desktop run of 0.2.1 (needs: restart Hermes, `hermes elm grant`, save + recall, compress a chat, delete a chat).
- `hermes plugins validate`: all 16 checks pass, no warnings, against Hermes 0.23.1 source in a sandbox (ruamel.yaml replaced by a PyYAML stand-in). Re-run on a real install: `hermes plugins validate %LOCALAPPDATA%\hermes\plugins\elm`.
- `hermes elm sessions` against a real `state.db` (unit-tested with a stub; it degrades to `hermes sessions list`).

## Next steps (agreed direction)

1. Owner runs TESTING.md once on Windows Desktop (computer use is not available to Claude), then merge to `main` and send to testers.
   Unverified behaviours most likely to differ live: whether Desktop's delete is a real delete (`reason='delete'`) and whether `/compress` fires `post_compaction`.
2. Decide grant model: keep terminal-only, or allow `/elm on` + in-chat confirmation (`ctx.ask_choice`).
3. Move recall/storage into the `MemoryProvider` slot (`memory.provider: elm`) for prefetch, `on_pre_compress`, `on_session_end`, recall indicator.
4. Agent routing as a `DelegationProvider` plugin + routing/orchestration skill.
5. Important-messages panel (plugin) + small generic Desktop SDK contribution for per-message actions/jump.
