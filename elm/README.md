# ELM Wiki for Hermes · 0.2.0-experimental

Memory kept as **reviewable local Markdown files**: a project folder of notes, decisions and claims, with a
derived SQLite FTS5 index. The model reads bounded, source-linked evidence packets and can expand one exact
source section. Everything stays on disk where you can open, edit or delete it with any editor.

**Experimental and unsupported.** It works on stock Hermes and uses only public plugin API, but nobody
maintains it. For the maintained ELM plugin (notes in a local SQLite file, auto mode, `/elm private`,
memory-aware routing), install [`elm`](https://github.com/Miawd3/ELM-Hermes-plugin/tree/main/stock-plugin).
The two are separate: different provider names (`elm-wiki` vs `elm`), different stores, different tools.

## What changed in 0.2.0

The 0.1.0 candidate needed a patched Hermes host (`hermes_cli.plugin_memory`, `projects_db`, organizer and
transport modules). None of that exists in stock Hermes, so its workspace mode, scoped private recall,
review dashboard, chat folders, organizer jobs and skill-update routes are **removed**. What remains is the
original file-based provider, its operator CLI and six starter skills. No private Hermes imports remain
(`tests/test_public_api_only.py` enforces this).

## Install and set up

1. Install: `hermes plugins install "https://github.com/Miawd3/ELM-Hermes-plugin.git#elm"` (or from the
   catalog entry `elm-wiki` once listed), or copy this folder to `$HERMES_HOME/plugins/elm-wiki/`.
   Then `hermes plugins enable elm-wiki`.
2. Create a store from the installed folder. Use explicit absolute paths; nothing is guessed from the cwd.

   ```sh
   python -B setup_profile.py new --hermes-home /abs/profile --root /abs/elm-memory \
     --project myproject --budget-mode legacy-estimate
   ```

   `adopt` instead of `new` binds an existing healthy ELM store. The default `--budget-mode measured` needs
   `tiktoken` and a local vocabulary file ([measured budgeting](docs/MEASURED_TOKEN_BUDGET.md));
   `legacy-estimate` (characters ÷ 4) needs nothing.
3. Select it and start a new chat:

   ```sh
   hermes config set memory.provider elm-wiki
   hermes memory status
   ```

Check the store any time with `python -B manage.py status --hermes-home /abs/profile` (also `doctor`,
`sync`, `context`, `read`, `history`). More flows: [guided workflow](docs/WORKFLOW.md).

## Tools the model gets

| Tool | Does |
|---|---|
| `elm_context(query)` | Bounded, project-scoped packet of source-linked evidence (default 700 tokens, 200–1200) |
| `elm_read(section)` | Expand one exact section from a packet locator; oversize sections are refused |
| `elm_status()` | Binding, readiness, recall mode and optional feature state |
| `elm_note(...)` | Pending proposal, or unverified agent-curated note, only if the write mode allows it |
| `elm_episode_search` / `elm_episode_read` | Only when episode capture is opted in: search/read scrubbed local turn text |

## Defaults

- **Read-only** store; `proposal-only` and `autonomous` write modes are explicit opt-ins.
- **Explicit-only recall**: nothing is injected automatically. Hermes labels prefetched memory
  "authoritative reference data", which conflicts with ELM's "untrusted evidence" contract, so background
  recall (`--recall-mode legacy-background`) is opt-in and not recommended.
- **No episode capture**, no network calls, no model calls, no telemetry, no dependencies (tokenizer optional).
- Six static starter skills (`source-research`, `documentation-lookup`, `debugging-recovery`,
  `verification`, `delegation`, `creative-continuity`) register through Hermes's native skill registry.

Try it without Hermes: `python -B demo.py` (synthetic data in a temp folder, prints retrieved evidence).

See [capabilities](CAPABILITIES.md), [security](SECURITY.md), [validation](VALIDATION.md) and
[provenance](PROVENANCE.md). Apache-2.0.
