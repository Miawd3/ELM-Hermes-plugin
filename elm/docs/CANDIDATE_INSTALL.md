# Install the experimental restoration candidate

## Compatibility

Use **a new disposable checkout/profile**, not a running or personal installation. This requires official [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) commit `126980e47b826963b26bf57d210106d849322f8a` plus this repository's complete [`integration/host.patch`](../../integration/host.patch). The plugin manifest minimum version is only a loader minimum, not stock/newer-host compatibility.

## 1. Prepare the host

In a terminal, in a directory where you keep test projects:

```sh
git clone https://github.com/Miawd3/ELM-Hermes-plugin.git
git clone https://github.com/NousResearch/hermes-agent.git hermes-elm-test
cd hermes-elm-test
git checkout --detach 126980e47b826963b26bf57d210106d849322f8a
git apply --check ../ELM-Hermes-plugin/integration/host.patch
git apply ../ELM-Hermes-plugin/integration/host.patch
```

Stop if the check fails. Do not force the patch or replace it with partial file copying. Follow the pinned host's own installation/build instructions to provision Python and Desktop dependencies. This repository does not ship a prebuilt desktop executable or a one-click installer.

## 2. Copy the plugin into a fresh profile

Choose a new disposable directory for `HERMES_HOME`. Set it in the same terminal that starts Hermes. Create its `plugins` directory, then copy the **whole** `ELM-Hermes-plugin/elm` directory into it, producing:

```text
<fresh HERMES_HOME>/plugins/elm/plugin.yaml
<fresh HERMES_HOME>/plugins/elm/__init__.py
<fresh HERMES_HOME>/plugins/elm/desktop/plugin.js
```

Do not copy the repository root as the plugin and do not use the old archived setup/adopt scripts. Do not reuse a live profile, existing store or real credentials for initial qualification. Pasting the repository URL into a stock-host plugin installer is not a supported route for this release.

## 3. Enable and inspect

Load the plugin through the patched host's native loader. The loader materializes the unified Desktop extension; enable it separately in the native plugin UI. Work from an authenticated saved chat. Open ELM settings/review and explicitly initialize fresh memory. Provider selection, capture, recall, project binding and project consent are independent actions.

Stock Hermes can report the plugin as loaded while its scoped memory provider remains unavailable. That is expected fail-closed behavior, **not** a successful supported install. Patched in-process hosting is required for full callbacks; process-hosted plugins have a narrower owner-read surface.

## What to expect

- Chat folders organize chats only; they do not change working directories, files or permissions.
- Message categories and important-message highlighting are optional and off by default.
- The six starter skills appear in the native catalog on the patched host.
- Organizer and search model preferences can be inspected, but production organizer dispatch is disabled and the model-backed search agent is absent.
- This manual-copy candidate is ineligible for unattended auto-updates.

[Current qualification and limitations](../../TEST_REPORT.md). Clean dependency installation from scratch, arbitrary OS versions and installed Windows/Desktop acceptance are not certified. Keep your original installation untouched; discard only the disposable test profile when finished. Never delete real memory to troubleshoot this candidate.
