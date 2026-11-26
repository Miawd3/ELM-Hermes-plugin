# Capabilities and limits · 0.2.0-experimental

| Area | Works | Not provided |
|---|---|---|
| Store | Markdown project folder + derived FTS5 index; `setup_profile.py new/adopt`, `manage.py sync/doctor` | Automatic discovery or migration of other stores |
| Recall | Explicit `elm_context` packets with source locators; exact `elm_read` expansion; typed memory (kind, basis, restrictions) | Semantic/embedding search; automatic injection by default |
| Writes | `elm_note` as pending proposal (`proposal-only`) or unverified agent-curated note (`autonomous`) | Automatic extraction from chats |
| Episodes | Opt-in scrubbed local capture, search, exact read, forgetting preview/apply | Secure erasure; complete secret detection |
| Review | Operator CLI: `review_candidates.py`, `inspect_episodes.py`, durable candidate inbox, submission reconciliation | A web/desktop review UI (removed in 0.2.0) |
| Budget | `legacy-estimate` (chars ÷ 4) or `measured` with a pinned local tokenizer | Exact model billing |
| Skills | Six static Apache-2.0 procedures via `ctx.register_general_skill` | Skills generated from your memory |

**Removed in 0.2.0** (needed a patched Hermes host): workspace/project binding, scoped private recall and
records, private sources and imports, local conversation capture RPCs, organizer/curation jobs, model-role
preferences, chat folders, important-message markers, dashboard and desktop pages, skill-update routes.

Hermes API used: `ctx.register_memory_provider`, `ctx.register_general_skill`, `agent.memory_provider`,
`hermes_constants`. Nothing else.
