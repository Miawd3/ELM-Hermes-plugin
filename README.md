# ELM · Keep the knowledge. Bring what matters.

**Scoped long-term memory and practical AI skills for Hermes, using its supported plugin APIs.**

The current version lives in **[`stock-plugin/`](stock-plugin/)**. It works without modifying the Hermes host. The older patched prototype is preserved separately below; it is not the recommended installation.

## Install the current plugin

In **Plugins → Install from repository**, paste:

```text
https://github.com/Miawd3/ELM-Hermes-plugin.git#stock-plugin
```

Or use the Hermes terminal:

```sh
hermes plugins install "https://github.com/Miawd3/ELM-Hermes-plugin.git#stock-plugin" --enable
```

Restart Hermes, then enable **Capabilities → Plugins → ELM**. Use a disposable profile for initial testing and keep your existing memory backup.

**Desktop activation needs an explicit grant for each chat.** Follow the short [installation and permission guide](stock-plugin/README.md#desktop-grant-one-chat-locally). Classic CLI/TUI can use `/elm on`. Do not install the repository root or apply the old host patch.

## What ELM adds

- **Memory with boundaries:** separate user, project, reference and skill records; explicit sharing; reviewed drafts, corrections and recoverable trash.
- **Useful recall:** deterministic local keyword search, plus an optional dedicated query-planning agent. Automatic recall does not invoke that planner.
- **Source-backed organization:** an explicit organizer creates reviewable excerpt drafts, with separate model settings.
- **Skills from the start:** seven focused starter skills, plus a command that turns selected long-term notes into a pending skill worksheet. Nothing is automatically installed or executed.
- **Clearer presentation:** optional inline Progress, Update, Answer, Final and Question cards, two styles, and a focused-chat settings shortcut. Labels are model-provided, not proof that work succeeded.
- **Local control:** opt-in plaintext capture, expiring per-chat grants, and model calls off by default.

[Complete usage, privacy and capability guide →](stock-plugin/README.md) · [Source and tests →](stock-plugin/) · [Verification evidence →](stock-plugin/evidence/)

## What has been checked

**55 Python tests**, JavaScript boundary/presentation checks and the official plugin validator pass. In an unmodified stock Linux Desktop, installation, permission handling, saving/searching a test fact, revocation, settings, the chat shortcut and inline-card preview were checked. Independent code review also covered the permission and source-copy boundaries.

This is a **working candidate, not full acceptance on every platform**. Windows and live-provider workflows still need end-to-end qualification. Agent failure fallback was tested without making paid provider calls. We do not claim the earlier 60% at 700-token benchmark target or demonstrated answer-quality gains.

## Clear boundaries

Native chat folders, important-message timeline markers and whole-message bubble styling are **not** part of this stock package. Inline cards are a supported alternative, not those native features. Skill worksheets need editing and testing before manual installation.

Official Memory Wiki remains a separate plugin; ELM does not claim database synchronization. Facts already printed into chat may appear in its history views. Memory is local plaintext, not an encrypted secret vault. See the [privacy notes](stock-plugin/README.md#privacy-and-limitations).

## Next steps

Qualify Windows and real provider workflows; improve setup and usability; then revisit retrieval architecture and broader benchmarks. Further development is planned, not a promise that those features are already shipped.

Apache-2.0. [License](LICENSE). Existing source, artwork and history remain preserved.

---

<details>
<summary>Archived patched-host prototype: historical documentation, not the current install route</summary>

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

</details>
