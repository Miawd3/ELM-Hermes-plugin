# Current test report

## Provenance and environment

Input source commit: ea694a0c0a6a8b75b47332f0f92bae2087f10e8f. All 188 retrieved input files matched their Git blob hashes before edits. Original source remains separate and unmodified.

Official Hermes source: https://github.com/NousResearch/hermes-agent/tree/6a0d2d12815c0546b0bcaf05046e2fe3293f60aa . Official source checkout remained clean. Python 3.14.9 and dependencies were prepared through Hermes's managed runtime. Tests used disposable profile and temporary data, without user credentials or live model calls.

## Fresh checks

- Official validator: all 16 checks pass, exit 0, empty stderr. Security scan says safe. One warning lists 21 private/undocumented core import/call locations. This is not an independent audit or catalog approval.
- Full current-host root discovery with exact host dependency pins plus tiktoken 0.14.0 and regex 2026.9.29: 338 executions, 264 pass, 73 errors, 1 skip. No existing Hermes dependency version changed. Source is imported directly; only the local hermes-agent distribution metadata is absent from the separate dependency test environment.
- Error breakdown: 62 missing set_session_project calls in fixtures; 5 missing resolve_session_project runtime calls; 5 retained tests expecting the intentionally disabled plugin updater; 1 test requiring its owned native-mount harness. No tests were removed or newly skipped to conceal failures.
- Four inherited regression discovery lanes: 356, 158, 150 and 19 executions, all pass. These inherited counts overlap; they must not be summed into a unique-test claim.
- Focused catalog update/bridge guards: 5 pass.
- Native human-draft bridge: 16 pass with synthetic completions, not real provider access.
- Durable record suite: 19 pass.
- Offline synthetic demo: passes, no Hermes service or model needed.
- Syntax: 135 Python files and 11 JavaScript files pass.
- Targeted source secret/path scan: zero findings across 196 text files. Scan covers PEM private-key headers, common credential prefixes and personal home-path patterns. It is not an exhaustive credential audit.
- Both regenerated source inventories verify exact final file hashes. Bytecode, caches, Git history and dependency runtimes are excluded from the delivery.

The earlier host-only root run without optional vocabularies had 82 errors and 15 skips. A separate initial tokenizer environment re-resolved some host dependencies and had 77 errors; it is superseded by the pinned 73-error run above. Those earlier runs are not used as current acceptance evidence.

## Workspace compatibility finding

The current official projects_db module lacks resolve_session_project and set_session_project. The old upstream commit b200f5bc60e31588ba2cb60e288029c4a54ba5fa named in inherited docs also lacks those named functions. The preserved Hermes 0.23 historical receipt is therefore not evidence that the optional workspace layer works on a clean stock installation.

Current-host UI workspace listing and session CWD do not encode ELM's earlier explicit/manual binding, explicit Home override or compression-ancestor precedence. A path-based substitute would weaken ownership. No such substitute was made.

A separate fail-closed patch detects an absent/noncallable resolver and raises host_api_unsupported. Human routes return HTTP 503. Eight tests pass, including actual current-host refusal, unchanged database bytes, no memory-store creation, unknown-session refusal and retained legacy binding/Home/archive/current-lineage contracts using scoped test doubles. The official validator also passes that variant. It is a safety diagnostic, not functional compatibility.

The visible update-panel wording was reconciled after the full root run to state that plugin updates are disabled. This changes text only; JavaScript syntax and the exact-byte validator were rerun afterward.

## Limits

No fresh full live UI acceptance, model tool-selection success, answer-quality gain, semantic DLP, encryption guarantee, complete erasure, guaranteed monetary cap, independent security certification or production readiness is claimed. The screenshots/browser results, if supplied separately, must be evaluated in their own stated test context.
