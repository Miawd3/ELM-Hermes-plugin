> Catalog preparation note: this separate export removes all plugin-code update controls and sanitizes qualification paths. Historical qualification below applies to the base snapshot. See ../PUBLIC_EXPORT_NOTES.md and the root QUALIFICATION.json for current checks and unresolved gates.

> Metadata-compaction candidate: **phase-1 pure codec/packing checks only**. No actual-native or full qualification of these bytes has run; historical qualification below does not transfer. See docs/METADATA_COMPACTION.md and sibling performance-compaction-v1/evidence/ for the frozen fixture, RED/GREEN wires, source seal and explicit UNRUN gates.

> Stat-refresh candidate: historical qualification statements below do not qualify these modified bytes. The current Windows managed-Python focused/native/full-run commands, exact sealed source hash, raw outputs and failures/skips/unrun inventory are external under this isolated iteration's `stat-refresh-evidence/`. See docs/STAT_REFRESH.md and docs/TYPED_MEMORY.md. Nothing is activated in a live profile.

# Reproduce validation

The install tree includes all current operational docs and test sources; external prerequisites are Python with SQLite FTS5 and a dependency-prepared stock Hermes checkout for native tests.

## Offline smoke, no Hermes/model dependency

```sh
python -B verify_release.py
python -B demo.py
```

The demo creates disposable synthetic data and prints retrieved evidence, not a generated answer. Query selection is scripted. Its operator read-only refusal is not a substitute for native `elm_note` tests.

## Full regression and native integration

Prepare stock Hermes source at exact commit `b200f5bc60e31588ba2cb60e288029c4a54ba5fa`, using its official runtime instructions. Then:

```sh
export HERMES_STOCK_SOURCE=/absolute/hermes-stock
/absolute/prepared/python -B run_validation.py --output /absolute/separate/evidence
```

The runner refuses another/modified host commit, uses the selected Python interpreter, discovers the current root tests, inherited regression modules and native harnesses from its declared globs, and saves commands, exits, logs, runtime identity and per-file source hashes. It does not fetch dependencies or call a model. Use `--unit-only` for a partial run; it is not full qualification. Output must be outside plugin source.

Test execution counts may include inherited unittest cases rerun by multiple fixture modules. Do not interpret the aggregate as a count of unique behaviors. All tests use disposable stores. Two inherited reconciliation adversarial fixtures deliberately accept synthetic proposals to test observation of accepted canonical state; the actual bridge/reconciliation API never accepts claims.

## Official catalog validation and installation

Follow stock Hermes's catalog-submission validation instructions, including preparing the PM runtime and dependency preparation. The official validator can catch dependency-preparation errors and still return successful JSON/exit 0. Inspect stderr and runtime preparation evidence; a green report alone is insufficient.

The separate release evidence contains the exact official command and output, a disposable local Git installation/selection test, and an independent audit. Local Git installation establishes no public clone/catalog admission. No catalog entry/PR or public release has been submitted.

## Qualification limits

Historical release qualification targeted Linux x86-64; that does not qualify this candidate. Current isolated execution uses the Windows managed CPython/runtime and pinned clean stock host recorded in the external structure-evidence report. Python 3.11+ remains the intended minimum, not a tested version/platform matrix. No live profile/store, credential, external model or user transcript was used. No end-to-end AI answer-quality, autonomous tool-choice, comparative superiority, broad performance or production-readiness claim is supported.

## 7 November isolated search-hardening candidate

The earlier release qualification above is historical and does not automatically qualify changed sources. The focused new test is `python -B tests/test_search_hardening.py`. Current full-regression/native results and the exact runtime identity are recorded separately in the search-hardening evidence. No Windows or other platform qualification is implied.

## Measured-budget follow-on

Set `ELM_TEST_VOCAB` and `ELM_TEST_CL100K_VOCAB` to the official hash-pinned local vocabularies, with `tiktoken==0.14.0` available to the test/provider runtime, before running current full validation. Missing assets explicitly skip optional real-tokenizer tests, not qualify them. The new native harness verifies exact JSON, real wrapper/character limits, and stock receipt-missing refusal. See [measured contract](docs/MEASURED_TOKEN_BUDGET.md). Old source digests and test counts above remain historical.
