> ARCHIVAL ONLY. This document describes an earlier, inactive implementation. Do not use its installation, provider, tool or permission claims for the r21 candidate. Relative links may refer to its original location.

> **Recovery candidate r20, not the public release.** Requires the accompanying patched Hermes host. Adds reviewed copying of user-supplied selected-record exports into new private pending/sensitive records, not automatic legacy migration or ownership verification. Real model extraction remains disabled. See [r20 copy contract](docs/DECLARED_EXPORT_IMPORT.md) and checkpoint STATUS.md / TEST_VERIFICATION.md.

> The README below is historical. Its public install links, "no host patches" statements and old capability claims do not describe these unpublished changes. Legacy source is retained for recovery, not active fallback. No live installation, user files or provider settings were changed.

---

# ELM for Hermes: experimental release candidate

**Isolated typed-memory candidate:** validated user/work/reference declarations and explicit stateless intent now reach engine admission, compressed packets and native exact reads. See [the contract, compatibility and limits](docs/TYPED_MEMORY.md). This is not live activation, multi-user identity or semantic DLP. Earlier qualification below is historical; fresh results for these exact bytes belong to the separate structure-evidence report.

Local, project-bound memory retrieval for **supported Hermes integrations**, with inspectable source links and permission-gated notes. This is a self-contained plugin source directory. Copy or install this directory as `elm`, not the surrounding evidence archive.

**Safe defaults:** read-only canonical memory, explicit-tool-only recall, no episode capture. No hosted service, mandatory MCP server, embeddings, model adapter, API key or separately installed ELM engine. The engine ships as Apache-2.0 Python source. No host patches.

This is a limited engineering release, not a general autonomous learning system or a production certification. Its scripted synthetic tests demonstrate storage, retrieval and lifecycle behavior, **not model tool selection or answer quality**. Publication and catalog admission are still separate, unperformed steps.

## Try it without Hermes or a model

Python 3.11+ with SQLite FTS5 is the intended minimum. The included demonstration uses only Python's standard library, explicit legacy-estimate mode and fresh temporary synthetic stores:

```sh
python -B demo.py
```

It prints evidence from synthetic Orion documents, expands an exact source, checks scope across restart, and demonstrates a read-only operator-bridge refusal. No AI answer is generated. No permanent profile is created. Native provider write-gate tests are separate.

## Install and set up a disposable profile

A working Hermes installation is an external prerequisite. The qualified host is Hermes 0.22.7 source commit `b200f5bc60e31588ba2cb60e288029c4a54ba5fa`. The manifest minimum is not a claim that every newer host works. See [validation](VALIDATION.md).

1. Set `HERMES_HOME` to an explicit disposable profile and install/copy this directory to `$HERMES_HOME/plugins/elm/`. Do not copy an old `elm.json`, captured evidence or memory store. Use native Hermes plugin installation when available; the release evidence records the exact tested local Git install route.
2. Prepare the optional pinned tokenizer and local vocabulary as described in [measured budgeting](docs/MEASURED_TOKEN_BUDGET.md). From the installed `elm/` directory, create a new, non-existing store:

```sh
python -B setup_profile.py new --hermes-home /absolute/demo/profile \
  --root /absolute/demo/new-memory --project orion \
  --tokenizer o200k_base --tokenizer-vocab /absolute/assets/o200k_base.tiktoken
```

For a deliberately selected existing healthy store, use `adopt` instead of `new`. Adoption requires a current indexed identified root and project hub; it never repairs or silently syncs an existing store. Guided setup refuses an existing ELM binding or optional settings. It never guesses a root from cwd, environment pointers or source text. Read setup output before continuing.

3. In the **same profile**, select `elm` with `hermes config set memory.provider elm`, check `hermes memory status`, and start a **new conversation**. Selection alone does not configure a store. Native `hermes memory setup` can adopt an existing store; creation is deliberately separate.
4. Check local state at any time:

```sh
python -B manage.py status --hermes-home /absolute/demo/profile
python -B manage.py doctor --hermes-home /absolute/demo/profile
```

Windows accepts explicit paths such as `C:/demo/profile`; these are placeholders, never inferred destinations. The fresh release qualification is Linux only. Earlier Windows evidence is historical, not a fresh qualification of these bytes.

## Everyday use

The provider offers exactly six model-facing tools:

- `elm_context(query)`: compact, project-scoped source-linked packet. New setups default to a 700-token **measured named-encoding** limit over the entire returned JSON, configurable 200–1200, with an explicitly selected local tokenizer. Not full-context/model billing. Historical profiles retain labeled legacy estimates until re-adopted.
- `elm_read(section)`: expand one exact section locator from the packet, with provenance and line range. Not a path reader. Oversize sections are refused.
- `elm_status()`: current binding/readiness, recall mode and optional feature state. Not a complete integrity audit.
- `elm_note(...)`: explicit pending proposal or bounded unverified agent-curated note, only if the chosen write mode permits it.
- `elm_episode_search(query, limit)` and `elm_episode_read(locator)`: separately opted-in search/read of current scrubbed source evidence.

The fixed system instruction asks the agent to call explicit tools for continuity-sensitive tasks. Whether a model actually chooses them is not established by scripted tests. Retrieved content is untrusted, potentially stale evidence; check consequential facts against current authoritative sources.

### Why explicit-only recall is the default

Stock Hermes wraps background-prefetched memory as “authoritative reference data.” That conflicts with ELM's untrusted-evidence contract. This release therefore returns **no canonical prefetch text and starts no prefetch worker** in `recall_mode: explicit-only`, including old bindings missing the new field. Explicit tools remain available. No host monkey-patch is used.

Advanced `manage.py init/adopt --recall-mode legacy-background` retains historical background behavior with explicit `--budget-mode legacy-estimate` for compatibility testing only. Measured background requires a verified host budget receipt; stock initialization does not provide it. See [delivery contract](docs/MEASURED_TOKEN_BUDGET.md). It reintroduces the host authority-wording risk and is **not recommended for live use**. Guided setup never enables it. Episode evidence is never background-prefetched in either mode.

### Write modes are separate from capture and recall

| Mode | Explicit propose | Explicit remember |
|---|---|---|
| `read-only` (default) | Blocked | Blocked |
| `proposal-only` | Pending, untrusted proposal | Blocked |
| `autonomous` | Pending, untrusted proposal | Bounded leased `agent_curated` note, still unverified |

Non-primary agent contexts cannot write. A model cannot override root/project, mode, actor, authority, acceptance or source-root policy. `autonomous` does not mean unrestricted chat learning. Stable submission IDs and identical payloads are required for retries; timeouts can mean an unknown committed outcome, not failure to save. See [API contract](API.md).

## Optional capture and review workflow

These are **distinct opt-ins**, all off by default. `setup_profile.py --help` describes flags and required dependencies; it fills root/project pins instead of asking you to copy IDs manually. See [guided workflow](docs/WORKFLOW.md) and [capability matrix](CAPABILITIES.md).

- Capture stores bounded scrubbed visible user/assistant pairs in the profile. Scrubbing is incomplete and can retain sensitive text.
- Explicit episode recall exposes current source evidence through tools.
- Exact single-line markers can stage untrusted proposals; with allowed write mode they can submit during lifecycle sealing. This is not general language extraction, and read-only mode is required if review must precede any governance submission.
- Process-local `BatchExtraction` validates locally supplied exact spans, without transport or persistence.
- A separate durable inbox retains quarantined span metadata across restarts.
- A separately enabled operator bridge records an explicit human-supplied interpretation and requires a digest-bound confirmation to submit a **pending** proposal. It never accepts facts.
- Conservative reconciliation can record a proven prior submission. Absence, expired/scrubbed proof and conflicts remain blocked; it never blindly retries.

Lifetime limits include 128 durable inbox rows and 128 review rows, including tombstones. There is no reviewed compaction/migration procedure. Never delete replay barriers to create space or “recover” uncertain operations.

## Security, storage and maintenance

Plugin Python runs with the host user's permissions; it is not a sandbox. Engine operations spawn the same interpreter against bundled source with a restricted environment. Reads use explicit pinned root/project and fail closed on identity/staleness; maintenance `sync` is an explicit operator action. Local lock coordination and profile receipts may be written. Stores may be outside the plugin/profile and are not automatically backed up by Hermes.

No plugin telemetry is sent. Explicit human-requested learning drafts can use the host model route and transmit approved selected source text to that provider. Explicit skill update checks can contact the configured skill sources through Hermes. Retrieved text becomes available to the host conversation and may subsequently be sent to the user's configured model by Hermes. Capture, receipts, source-derived meanings and canonical governance have different retention. Local forgetting is **not complete erasure** of transcripts, backups, canonical proposals, old SQLite pages or previously displayed text. See [SECURITY.md](SECURITY.md).

Three maintenance interfaces are retained: `manage.py`, `inspect_episodes.py`, and `review_candidates.py`. The latter can write expiry/revocation tombstones even on review/list paths; it is not a strictly read-only inspector.

## Provenance and validation

- [Current feature contract](CAPABILITIES.md), [API](API.md), [validation commands and limits](VALIDATION.md).
- [Source provenance](PROVENANCE.md), root `SOURCE_MANIFEST.json`, and `verify_release.py` identify the exact release files.
- `LICENSE`, `NOTICE`, `engine/LICENSE`, and `engine/NOTICE` retain Apache-2.0 attribution.
- `docs/provenance/` contains explicitly historical evidence, not current feature descriptions. Current release documentation takes precedence.

Run `python -B verify_release.py` after extraction to verify the manifest. Detailed test logs and official-validator output are in the separate evidence package so they do not obscure the install tree. No public repository, remote commit, catalog PR, live deployment or model-quality result is claimed.

## Experimental search hardening

This isolated 7 November 2026 candidate adds deterministic retrieval ties and bounded concurrent strict/broad context admission. See [search hardening](docs/SEARCH_HARDENING.md) for exact behavior, scope, concurrency guards, and token-budget limits. It is not deployed and does not claim improved generated-answer accuracy.

## Measured token-budget candidate

The current isolated follow-on adds exact named-tokenizer accounting at the provider boundary without changing search scope or engine subprocess isolation. See [configuration, migration, guarantees and limits](docs/MEASURED_TOKEN_BUDGET.md). The historical search report's estimated-token packet results are not results for this new packing policy.
