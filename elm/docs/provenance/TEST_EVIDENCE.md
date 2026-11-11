# Test evidence — baseline and reviewed provider candidate

Recorded from real tool execution on Windows 11, November 5, 2026 UTC. All stores/profile homes used below are synthetic temporary fixtures under the configured Hermes scratch directory. No inference/provider calls, credentials, live-profile install, public posts, commits or pushes were used.

## Original RC1 exercised commands

Run from the plugin source directory:

```bash
C:/Python314/python.exe -B -m unittest discover -s tests -v
python -B tests/native_contract.py
```

Observed results after integrating the engine template fix and the cache-invalidation regression:

```text
Ran 18 tests in 35.555s
OK
```

No skips or test collection failures in that final run. The stdlib run uses CPython 3.14.3 and the actual pinned stock `agent.memory_provider.MemoryProvider` ABC. The native script is a separate real consumer check using the dependency-prepared stock Hermes runtime, not a mock host:

```text
native_discovery: PASS
real_memory_manager: PASS
fresh_profile_recall: PASS
read_only_gate: PASS
background_recall: PASS
```

The original RC1 script copied the source directory into **only a disposable** `<home>/plugins/elm`, checked native name/path discovery, loaded two distinct provider instances through `plugins.memory.load_memory_provider`, verified the real ABC type and exercised native setup/config availability and background recall. It dispatched `elm_context` and `elm_note` through the real `MemoryManager`; `elm_read` and `elm_status` were originally checked for registration only. The independent review caught an overstatement of that coverage. The parent has since added and successfully exercised actual scoped `elm_read` and healthy/project/mode `elm_status` dispatch assertions. The temporary profile/store is deleted after execution.

### Independent-review qualification

RC1 passed the original 18 tests and the parent's extracted-package/catalog checks, but an independent focused review then reproduced five correctness defects: WAL-stale recall, time-expired cached claims, normalized-field readback errors, mutation receipt session misattribution and argparse interpretation of leading-dash text. Original green results do not clear those defects. `REVIEW_NOTES.md` describes the repairs and limits; the companion engineering evidence preserves original findings, raw logs and fresh sealed acceptance. No general security certification is claimed.

### Corrected source suite

The repair worker subsequently executed the expanded real-engine suite: **28 tests passed, no skips, in 206.596 seconds** (27 provider tests plus one fresh-init regression). Meaningful RED→GREEN cases covered held-WAL updates, time-only expiry, future eligibility, normalized-field/ID readback, admission-session receipts and literal leading-dash CLI data. Additional cases cover operator rebuild with a live provider, scrubbed subprocess isolation, non-primary write denial and a committed write followed by an injected lost reply.

Final cache validation uses short read-only logical metadata snapshots, not retained SQLite monitor connections. An intermediate retained-connection implementation blocked Windows operator rebuild; that failing regression and the earlier suite output remain in the companion logs, explicitly distinguished from the final snapshot-based pass. Two intermediate fixture mistakes were corrected without hiding their original logs: autonomous future observations are deferred by design, and punctuation-only queries have no searchable terms.

The parent's fresh extracted-package unit/native/catalog results are supplied in the exact candidate's external `acceptance-rcN.json`; the source worker's run alone is not artifact qualification.

The first corrected extraction (RC2) ran 28 tests in 310.709 seconds but failed both temporal fixtures before their intended transition: seven-second setup windows had already elapsed. A follow-up reviewer independently reproduced the expiry fixture race. The parent replaced those two wall-clock races with controlled-clock checks that still launch the real vendored engine process and read unchanged synthetic source/index data. Both passed in 31.328 seconds; the revised expiry check also meaningfully failed against frozen RC1 production code in 9.642 seconds, at stale cached-claim injection. The failed RC2 is preserved and not qualified. `REVIEW_NOTES.md` explains the methodology; final whole-artifact qualification uses a newly named candidate.

## Observed red → green vertical slices

Each listed RED was observed before the corresponding provider behavior was implemented/fixed; later cumulative runs verified GREEN.

| Slice | Actual RED observation | Verified GREEN behavior |
|---|---|---|
| Fresh-session recall | `'signed rollback' not found in ''` | New provider/session delivers the configured project's packet, no lighthouse distractor; exact packet matches real engine. |
| Read-only learning gate | expected `write_blocked`, got no error | Explicit notes blocked without canonical changes. |
| Proposal-only lane | expected pending result, got none | Real pending untrusted proposal, exact local receipt readback, activation blocked. |
| Autonomous learning | expected remembered disposition, got none | Real agent-curated activation, same-ID replay, separate duplicate, conflicting correction deferred with proposal/history. |
| Scope/dispatch boundary | expected invalid arguments, got none | Model project/root override rejected; unknown tools refused. |
| Per-instance binding | expected already-bound error, no error | Reinitializing another profile refused; mismatched caller home rejected. |
| Exact expansion | expected exact section, got no text | Scoped source locator expansion with raw/normalized authority, claim ID and line provenance; no duplicated body. |
| Background recall | expected source text, got empty after deadline | Context-copied bounded worker and exact-query cache; cold path returns immediately; unrelated query/indicator cleared. |
| Empty query | expected `no_query`, got `invalid_arguments` | Empty/whitespace context yields `no_query`, prefetch empty; no engine crash or broad scope fallback. |
| Non-primary writer | expected `write_blocked`, got none | Subagent note blocked even under autonomous user config. |
| Stale store | expected structured engine refusal, initially got wrapper engine failure | Wrapper now parses the engine's JSON **stderr** errors; stale reads/writes fail closed. |
| Receipt readback failure | expected committed disposition, got none | A deliberately injected post-commit I/O failure preserves the actual engine result and reports verification failure separately. |
| Invalid stored mode | invalid configuration accepted initialization | Frozen binding rejects unknown modes/scope format before use. |
| Native setup/operator init | inherited setup fields empty | Root/project/mode/budget schema plus a real `manage.py init` → status roundtrip. |
| Cache after operator sync | cached packet still contained old `signed rollback` | Index-generation change invalidates packet; background reload returns `staged rollback`. |

Supporting cases also verify unchanged canonical-source/index/vendor hashes for reads, no retrieval traces, no raw-turn persistence, stable system block and schemas, unknown adoption project rejection, stale/missing/changed identity refusal, and no implicit home fallback.

### Harness issues encountered and corrected

- A completely stripped Windows child environment initially made `Path.home()` unavailable. The child now gets explicit profile-bound HOME/USERPROFILE, without inheriting credentials or live ELM pointers. The meaningful first RED was then re-run and observed.
- An early synthetic note used January 1, 2026 as its observation date. On the actual November 2026 clock its 90-day lease was correctly `expired_deferred`, not remembered. The activation fixture now records the actual UTC observation time and reuses the identical payload for replay. Expiration was not suppressed or reinterpreted as saved.
- Engine refusal JSON is emitted on stderr. Parsing only stdout lost structured diagnostics; the stale-store regression caught this and the wrapper was corrected.
- No stock source, upstream pin or live user corpus was edited to fix these issues.

## Engine provenance and init regression

Vendored engine is source-only public commit `d687f0a48dbe841d7d8b85b801900c6cdc63ee7d`, version `1.0.1.dev0`, plus the owner's verified five-template init-metadata fix:

- Modified `engine/elm_memory/cli.py` SHA-256: `75ee545b298f17ce73e3253a34c70da30cdada5072f1c93a04e4fb1602e10eaa`.
- Included `engine/patches/init-metadata.patch` SHA-256: `23fbb498f6de728de742ae68fe9355ef625f80f845b2499e565042f853cad191`.
- The other 11 vendored Python source files remain byte-identical to the public pin. `engine/SOURCE_MANIFEST.json` contains both upstream and delivered hashes for every source file.
- `tests/test_init_metadata.py` independently invokes this **vendored** engine: a brand-new five-document store yields doctor issues `[]`, searchable metadata tags and healthy readiness. No parser suppression or doctor-result filtering is used.

The owner separately reported a 297-test engine run and the earlier metadata RED; those are **not** included in this provider's 18-test total and are not re-claimed as execution by this worker.

## Full delivery-size evidence

Actual native-contract output for the small synthetic Orion fixture (the rich response's byte count can vary slightly with generated engine metadata):

| Surface | Observed size |
|---|---:|
| Packet estimate | 239 estimated tokens |
| Complete returned model-tool string, including JSON envelope/project/estimate | 264 estimated tokens; 1,055 UTF-8 bytes |
| Packet alone | 955 UTF-8 bytes |
| Raw rich engine JSON that was **not** delivered | 3,271 UTF-8 bytes |
| All four fixed provider schemas | 584 estimated tokens |
| Fixed provider system block | 149 estimated tokens |
| One tool result + fixed schemas + fixed provider block | 997 estimated tokens |

Estimates use `ceil(characters / 4)`, not a model tokenizer. They exclude unrelated host prompt/tool/chat material and API framing. The full returned tool string is measured, not just the inner packet. The tests additionally assert that a configured 700-token packet's complete delivery stays below 800 estimated tokens in the synthetic acceptance fixture. Static schema/system overhead is shown separately rather than hidden as zero. This is not a billing, latency, quality, overall winner or production-scale claim.

## Remaining material limits

- Exact final-package/privacy checks and `hermes plugins validate` results are separate owner receipts, not implied by the source-suite total. Interactive user acceptance and autonomous main-model tool selection remain unverified.
- Cold background recall can be empty; reliable first-turn continuity uses explicit `elm_context`. Warm validation adds a logical metadata scan and readiness subprocess; large-store warm-cache latency is not benchmarked. No model-driven extraction/automatic curation is implemented.
- One configured project per profile. Cross-project/workspace recall, rich history inspection as a model tool, dashboard schema, isolated plugin-host transport and non-Windows/frozen-runtime certification are not implemented/verified here.
- Correction CAS is intentionally not exposed. Conflicting corrections remain deferred reviewable proposals, not automatic replacements.
- Engine quotas/lifecycle are retained unchanged; the provider suite specifically exercises active/replay/duplicate/conflict and readback-failure paths, not an exhaustive repetition of the engine's governance test matrix.
- Local configuration/store ownership is an assumption, not an OS sandbox. Separate CLI calls do not prevent hostile same-user filesystem races. Explicit notes require care with sensitive content; no comprehensive DLP/encryption/secure-delete guarantee is made. Receipts currently have no automatic retention/pruning.
