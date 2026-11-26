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

Restart Hermes, then enable **Capabilities → Plugins → ELM**. Requires Hermes 0.23.1 or newer. **Testing it?** Follow the [tester guide](stock-plugin/TESTING.md) (about 20 minutes, uses a separate test profile).

**Desktop activation needs an explicit grant for each chat:** run `hermes elm grant` in a terminal and pick the chat. See the [installation and permission guide](stock-plugin/README.md#desktop-grant-one-chat-from-your-terminal). Classic CLI/TUI can use `/elm on`. Do not install the repository root or apply the old host patch.

## What ELM adds

- **Memory with boundaries:** separate user, project, reference and skill records; explicit sharing; reviewed drafts, corrections and recoverable trash.
- **Useful recall:** deterministic local keyword search, plus an optional dedicated query-planning agent. Automatic recall does not invoke that planner.
- **Source-backed organization:** an explicit organizer creates reviewable excerpt drafts, with separate model settings.
- **Skills from the start:** seven focused starter skills, plus a command that turns selected long-term notes into a pending skill worksheet. Nothing is automatically installed or executed.
- **Clearer presentation:** optional inline Progress, Update, Answer, Final and Question cards, two styles, and a focused-chat settings shortcut. Labels are model-provided, not proof that work succeeded.
- **Local control:** opt-in plaintext capture, expiring per-chat grants, and model calls off by default.

[Usage and privacy guide →](stock-plugin/README.md) · [Tester guide →](stock-plugin/TESTING.md) · [Changelog →](stock-plugin/CHANGELOG.md) · [Detailed notes →](stock-plugin/docs/DETAILS.md)

## What has been checked

**136 Python tests** and 4 JavaScript boundary/presentation checks pass, and the official `hermes plugins validate` checks pass against Hermes 0.23.1 source (0.2.1-preview; sandbox run, not yet on a real install). In an unmodified stock Linux Desktop, installation, permission handling, saving/searching a test fact, revocation, settings, the chat shortcut and inline-card preview were checked. Independent code review also covered the permission and source-copy boundaries.

This is a **working candidate, not full acceptance on every platform**. Windows and live-provider workflows still need end-to-end qualification. Agent failure fallback was tested without making paid provider calls. We do not claim the earlier 60% at 700-token benchmark target or demonstrated answer-quality gains.

## Clear boundaries

Native chat folders, important-message timeline markers and whole-message bubble styling are **not** part of this stock package. Inline cards are a supported alternative, not those native features. Skill worksheets need editing and testing before manual installation.

Official Memory Wiki remains a separate plugin; ELM does not claim database synchronization. Facts already printed into chat may appear in its history views. Memory is local plaintext, not an encrypted secret vault. See the [privacy notes](stock-plugin/README.md#privacy-and-limitations).

## Next steps

Qualify Windows and real provider workflows; improve setup and usability; then revisit retrieval architecture and broader benchmarks. Further development is planned, not a promise that those features are already shipped.

Apache-2.0. [License](LICENSE). Existing source, artwork and history remain preserved.

---

## ELM Wiki (experimental, unsupported)

[`elm/`](elm/) holds **ELM Wiki 0.2.0-experimental**: memory kept as reviewable local Markdown files with a
derived SQLite FTS5 index, explicit source-linked recall and exact source expansion. It runs on stock Hermes
with public plugin API only. It is a separate plugin (`elm-wiki`), not maintained; use `stock-plugin/` above
for everyday memory.

```sh
hermes plugins install "https://github.com/Miawd3/ELM-Hermes-plugin.git#elm"
```

Setup, tools and limits: [elm/README.md](elm/README.md). The earlier patched-host prototype (rc40: scoped
workspaces, review dashboard, chat folders, organizer) is preserved at commit
[`25100b24`](https://github.com/Miawd3/ELM-Hermes-plugin/tree/25100b248790813861282e71e376d371264c1787);
`RELEASE_STATUS.md`, `TEST_REPORT.md` and `integration/` describe that prototype.
