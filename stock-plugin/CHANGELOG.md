# Changelog

## 0.3.0-preview — unreleased

- **New:** ELM can run in Hermes's memory-provider slot (`memory.provider: elm`, or `hermes memory setup elm`).
  Recall then goes through Hermes's memory prefetch, with the **🧠 ELM — recalled N memories** indicator,
  capture through `sync_turn`, and compression through `on_session_switch`. Same grant rules as before;
  subagents, cron and messaging chats never recall. The general hooks step aside in this mode, so a note
  is never injected twice. Without the setting, ELM works exactly as in 0.2.1.
- **New:** memory-aware agent routing, Hermes delegation backend `elm` (`delegation.backend: elm`).
  Name agents (model routes or Hermes profiles) under `delegation.backends.elm.agents`; the model may
  pick one per `delegate_task` task, otherwise ELM picks the agent that did best on similar past tasks,
  then `default`, then the parent's model. Remembers only agent, goal keywords, success and duration,
  only for chats with ELM on; purged with the chat. `hermes elm routes` shows agents and results.
  Database schema 3 (adds three routing tables; existing data untouched).
- `hermes elm doctor` shows whether ELM is in the memory slot, and counts routing outcomes.

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
