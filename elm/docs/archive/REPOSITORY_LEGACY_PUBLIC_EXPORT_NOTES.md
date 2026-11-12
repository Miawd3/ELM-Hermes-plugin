# Catalog export notes

This is a separate sanitized experimental source export of ELM for Hermes. It does not modify the original repository, a live Hermes installation, a user profile, or canonical memory. These notes record the preparation checks and remaining compatibility gates; catalog admission requires maintainer review of the exact public commit pin.

## Provenance

Base: ELM-Hermes commit ea694a0c0a6a8b75b47332f0f92bae2087f10e8f. All 188 input files were retrieved at that commit and independently matched their Git blob hashes before editing. The base's 183-member plugin archive hash is historical provenance, not this export's hash.

## Changes from the base

- Removed personal workstation paths from 11 retained qualification harnesses. Host source, dependency directory, optional legacy test suite, Python and browser locations are explicit prerequisites. Scratch fixtures use a named temporary directory.
- Added qualification_paths.mjs and QUALIFICATION_SETUP.md for those optional harnesses. Prior browser qualification does not transfer to these changes.
- Removed plugin-update discovery, application and installed-ref inspection from the human product router. Both ELM self-updates and updates of other plugins are refused. Visible panel wording now explicitly states that plugin updates are disabled and skill updates remain separate. Use Hermes's native reviewed-catalog update flow. Explicit, human-selected skill updates remain and retain native scan/ownership/readback gates.
- Added five focused source-level tests for plugin-update removal and safe bridge registration.
- Changed the optional workspace-draft registration bridge to skip a foreign/incomplete plugin context instead of raising. The command handler still requires owned ELM identity and all existing dispatch guards. The official validator uses such a generic recording context.
- Restored the missing elm/SOURCE_MANIFEST.json required by verify_release.py, with fresh hashes for this export. Regenerated repository inventory separately.
- Retained Apache-2.0 source/engine licenses and notices; copied the same source license and notice to the repository root for discoverability.
- Clearly separated inherited qualification from current export checks. No hosted CI, public release, live activation, benchmark score, security certification or generated-answer superiority is implied.

## Remaining admission work

The official validator passes all 16 checks on the prepared bytes using the current upstream managed runtime; its private-core-import warning remains (21 import/call locations). Passing that validator is not catalog acceptance or functional UI qualification. The bridge's native owner/permission tests pass with synthetic model completions.

The current upstream host has removed `projects_db.resolve_session_project`, which the workspace layer invokes, and `set_session_project`, which its tests use. No equivalent authoritative ownership API was found. CWD and sidebar project selection are insufficient substitutes under ELM's existing privacy contract. Workspace/private UI support on that host is blocked. The official historical upstream commit named in inner docs also lacks those functions; a preserved-host receipt is not proof of clean upstream support.

Four inherited regression lanes pass (356, 158, 150 and 19 test executions, overlapping counts). The root current-host suite is not green: errors separate removed host APIs, five retained tests of the now-disabled plugin updater, and one harness-only native-mount prerequisite. The current report distinguishes runs with and without the optional tokenizer. No tests were deleted or skipped to hide this. Optional browser lanes require external prepared JavaScript/browser assets and the old UI suite. Prior 90-method/6-browser qualification remains historical, not current acceptance.

A separate experimental safety patch in the surrounding delivery bundle returns `host_api_unsupported` and HTTP 503 cleanly when ownership cannot be verified, with eight passing guard tests. It does not restore workspace functionality and is not applied to this baseline export.

Token-measured setup additionally requires the pinned optional tokenizer and local hash-verified vocabularies. Dependency-free demonstration uses explicitly labeled legacy estimates. No guaranteed dollar cap exists.

The catalog entry must point to a new public source-only repository and its verified full 40-character commit SHA. Do not use the private base commit as the public pin. A separate new repository avoids exposing historical workstation paths through Git history.

## Behavior disclosures for reviewers

The plugin reads its selected local memory root and host-owned profile/session/project metadata outside the plugin directory. It writes explicit local profile stores and approved memory actions according to configured mode. Engine operations spawn the same interpreter against bundled source with restricted environment and no shell command interpolation. Optional capture retains scrubbed visible exchanges, but scrubbing is not complete DLP or complete erasure.

Explicit human-requested learning drafts use the host's permitted LLM route and can send approved selected source text to that provider. The plugin holds no provider credential. Explicit skill checks/updates use Hermes's native source and scan flow, which can contact configured external skill sources. There is no plugin telemetry and no plugin code updater in this catalog export. Read the underlying API, security and private-control contracts before enabling optional layers.
