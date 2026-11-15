# Changelog

## 0.2.1-preview — 2026-11-14

- **Fix:** long chats kept their ELM access and private notes when Hermes compression moves them to a new session ID (`post_compaction`).
- **Fix:** deleting a chat now deletes its private notes, captured text and settings; archiving keeps them (`on_session_delete`).
- **Fix:** automatic recall no longer fires on greetings/acknowledgements/slash commands, ignores common words, needs enough matching words, and doesn't repeat a note already added to the chat.
- **Fix:** database setup runs once instead of taking a write lock on every read.
- **Fix:** Desktop settings showed the runtime chat handle instead of the saved chat ID used for grants.
- **Fix:** messages with images are handled for recall and capture.
- **New:** `hermes elm grant | revoke | sessions | doctor`. Replaces the `python -m elm_plugin.local_grant --expect-home` routine (still supported).
- Requires Hermes 0.23.1 or newer.
- New user README, tester guide (`TESTING.md`); full technical notes moved to `docs/DETAILS.md`.

## 0.2.0-stock-candidate — 2026-11-13

First stock-plugin candidate: scoped local memory, review flow, exact-chat local grants, search planner and organizer slots, Desktop settings, memory manager, inline cards, seven skills.
