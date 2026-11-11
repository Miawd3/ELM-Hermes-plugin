# Source provenance

## Current isolated stat-refresh candidate

This source-only candidate derives from the accepted **typed policy-v8** tree `68d30cd3cc78714baf4b17a3ebf30a5f9ba999e365eeed5f1d6b364d6c0252c7`, whose original manifest SHA-256 is `7965c21585ac65762539356f731176e4183dd108039ef182b2ff070a7c6d8c56`. It fixes the pre-existing equal-content/changed-mtime ordinary-sync availability trap in `index_one`: validated unchanged bytes now refresh only derived mtime/size while preserving content/section/record identity. Policy/schema stays 8; no source admission or read guard is weakened. See `docs/STAT_REFRESH.md`. Current RED/GREEN, real stock native refusal/recovery, source seals and prescribed full-run evidence are external under `stat-refresh-evidence/`. Prior qualification remains attributable to prior bytes, not automatically transferred. Root SOURCE_MANIFEST binds this candidate. No live/canonical/profile, host, frozen source, controller/benchmark or public repository is modified.

## Historical declaration-consumption policy-v8 input

The accepted parent source is the **8 November declaration-consumption policy-v8 repair**, derived from preserved, unaccepted v7 tree `a2ed2e571befa162c023abc3b1ab0c8fabd317b6531242c3cc6f22dd7c536af8`. Independent review refuted P1 closure: the reserved scan could recognize five leading tab-before-colon declarations while the metadata parser skipped them, and later ordinary metadata made their positions appear valid. This revision replaces the positional test with exact recognized-versus-consumed declaration-line coverage, and invalidates v7 cached admissions through policy/schema 8. It does not add another whitespace exception, semantic classifier or wider grant. Frozen v6 tree `2d418f881222ffa5bb239c29ed3678ff0bc49613e2673301f95868e4ef71fa31` and qualified November 7 tree `34d9d0672e52133d3a36a4f2086f6ab488499c7f4da5c73d7da5254562852da0` remain earlier lineage. Current RED/GREEN, actual frozen-v7 binding upgrade and qualification evidence are under this iteration's external `consumption-repair-evidence`; earlier evidence/counts are historical, not transferred acceptance. Root SOURCE_MANIFEST is the current inventory; engine/provenance manifests and paragraphs below are historical. No live/canonical/profile, host, frozen source or public repository is changed.

## Historical search-hardening input

Candidate ID: `elm-search-hardening-20261107`. Input: the complete `ELM_release_candidate_20261106.zip`, preserved unchanged. The root `SOURCE_MANIFEST.json` records its SHA-256 and the current complete inventory. This candidate changes `engine/elm_memory/cli.py` for stable tie ordering, sorted traversal, fixed bounded strict/broad context admission, and read-consistency/policy checks. The exact patch is `engine/patches/search-hardening.patch`; tests and behavior are documented in `docs/SEARCH_HARDENING.md`. The dictionary adapter and codec are unchanged. No live deployment or public publication has occurred.

The engine is no longer byte-identical to the 6 November release. Earlier manifests and qualification statements below describe that historical input only, not the current implementation. Current qualification is in the separate hardening validation evidence.

## Historical 6 November release

Release ID: `elm-0.1.0-rc1-20261106`. Intended plugin directory/name: `elm`.

Input: `ELM_submission_reconciliation_20261106.zip`, SHA-256 `9c2b95cfdd838b41c55b81ec95114a012b09a7dd4caf1907e2955c525a069b2e`. Its `candidate_elm/` is the source baseline. The input archive is not nested into this release.

The vendored `engine/` directory remains byte-identical to that baseline. Earlier public upstream provenance is https://github.com/Miawd3/elm-memory at commit `d687f0a48dbe841d7d8b85b801900c6cdc63ee7d`, version `1.0.1.dev0`. The historical `engine/SOURCE_MANIFEST.json` records that earlier vendoring and metadata patch, not a complete current engine inventory or a claim of public-upstream byte identity. Current hashes are in the root `SOURCE_MANIFEST.json`.

Changes from the input: conservative canonical-prefetch configuration/default; runtime status and setup schema; guided non-overwriting setup; deterministic offline demonstration; portable inherited regression suite; focused new tests; consolidated self-contained docs and verification. Detailed file diff is in release evidence. No stock Hermes core file is patched. Fixed provider-tool schemas and the canonical engine remain unchanged.

`docs/provenance/` preserves historical source manifests and reports for attribution/context only. Their old install paths, earlier test totals, dated feature omissions and environment claims are not current instructions or fresh qualification. Current README/CAPABILITIES/VALIDATION files supersede them.

`SOURCE_MANIFEST.json` binds every shipped file except itself using SHA-256 and size. `verify_release.py` refuses missing, changed or unexpected files (excluding VCS metadata and Python bytecode). The source-tree hash is a deterministic digest of the manifest's sorted file records. This provides consistency, not authentication against an attacker who can rewrite both source and manifest.

The evidence package records an exact local Git commit and clean tree for installation testing. No public repository URL/remote commit has been created. A future catalog submission must use a public repository pinned at the authorized final commit and rerun official validation on that exact tree.

## Licensing

Apache-2.0 LICENSE and NOTICE files are retained at root and engine scope. Source-only Python, no runtime environments, model outputs, captured user data, keys, memory databases or nested release archives are part of the install tree.

## 2026-11-07 measured-budget follow-on

Derived from ELM_search_hardening_candidate_20261107.zip in an isolated copy. Added provider-side measured packing, local named-encoding counting, configuration/migration and host-delivery guards. Engine database operations keep their restricted subprocess boundary. Existing synthetic fixtures explicitly select their original legacy behavior; new tests qualify measured delivery. Tokenizer definitions derive from tiktoken 0.14.0 under its retained MIT notice. Full source inventory and exact change evidence accompany this candidate; no deployed or model-quality claim is made.
