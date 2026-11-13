# Stock-Hermes plugin candidate

A **no-host-patch candidate** is now available in [`stock-plugin/`](stock-plugin/), with a scoped search agent, opt-in organizer, model choices, approval workflow, starter skills and concise settings. [Install and limits →](stock-plugin/README.md)

It is a separate candidate, not full parity with the earlier patched UI: native chat folders, timeline highlighting and whole-message styling are not provided. Automated stock API tests pass; full Desktop/Windows and live-provider acceptance remain pending. Earlier source and history below are preserved unchanged.

---

# ELM · Keep the knowledge. Bring what matters.

## Install first

**This is an experimental source release, not a drop-in plugin for stock Hermes.** It requires our included host patch on one pinned Hermes revision. Pasting this repository URL into stock Hermes is not a supported installation route.

1. Prepare a **new, disposable** Hermes checkout at `126980e47b826963b26bf57d210106d849322f8a` and apply [`integration/host.patch`](integration/host.patch).
2. Copy the complete [`elm/`](elm/) directory into `<fresh HERMES_HOME>/plugins/elm`. The repository root is not the plugin.
3. Start the patched host using its own setup instructions; enable the optional ELM Desktop extension and configure ELM from an authenticated saved chat.

[Exact steps and boundaries →](elm/docs/CANDIDATE_INSTALL.md) · [Release status →](RELEASE_STATUS.md) · [Test evidence →](TEST_REPORT.md)

## Memory with boundaries

ELM separates personal memory from explicitly authorized project memory, keeps source references, and lets you inspect and review what is saved. Capture, recall and project access are separate opt-in decisions.

![ELM memory overview](assets/elm-01-memory.svg)

The candidate includes pending records, approval and correction, recoverable deletion, source/excerpt review, opt-in local capture, scoped wiki inspection and optional lexical search. Stores are local plaintext, not an encrypted secret vault.

## Find what matters, not every past message

![ELM intended search architecture](assets/elm-02-search.svg)

**Architecture illustration, partially implemented:** scoped review, local search and separate model preferences exist. The autonomous model-backed search agent is **not implemented**, and production organizer dispatch is **disabled**. This is not a demonstration of a live agent routing through memory.

## Make conversations easier to navigate

![ELM context overview](assets/elm-03-context.svg)

On the accompanying patched host, the restoration adds:

- **Message types:** Progress, Update, Answer, Final and Question, with bounded labels, colors, backgrounds and borders. Off by default; explicit source markers remain visible. “Final” is a presentation label, not proof of completion.
- **Important messages:** explicit highlights and clickable ticks for already-loaded chat messages.
- **Chat folders:** metadata-only grouping, rename and empty-folder removal. These are not filesystem folders, native projects or permission grants.
- **Six original starter skills:** research, documentation lookup, debugging/recovery, verification, delegation and creative continuity. Native catalog entries are read-only and individually disableable.
- **Memory and model settings:** scoped review, organizer/search preferences, permission and readiness checks. Preferences alone do not activate a working model agent.
- **Per-plugin update controls:** native policy support for eligible catalog installs. This manual-copy candidate does **not** self-update.

## What is next

Finish and qualify the production organizer and separate search agent; verify installed Windows/Desktop behavior; refine UI and configuration; then revisit core retrieval quality and broader benchmarks. Memory-derived skill creation and automatic model/task selection are future work, not shipped capabilities.

The latest focus is usable UI, skills and reliable recovery. We do not claim the earlier 60% at 700-token goal or improved end-to-end answer quality from this release. See the [honest capability matrix](elm/CAPABILITIES.md).

Apache-2.0. Existing artwork and repository history are preserved. [License](LICENSE) · [Security boundaries](elm/SECURITY.md)
