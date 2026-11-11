# Metadata compaction — phase 1 only

This isolated candidate factors the **complete identical typed `memory` object** once in the existing `ELM-DICT/1` `defaults` dictionary. It does not factor individual memory fields, change the marker/decoder, remove text/locators/metadata/warnings, or change the normalization, candidate selection/order, scoring, budget, eligibility, grants or UX. The source-count validator must recognize a dictionary-valued `memory` default; other recognized defaults remain strings and unknown defaults remain refused. This is a supported-format extension for this candidate's encoder and count consumer, not an assertion that older strict count validators accept it.

Defaults are considered only when a field is present on every record and its sorted-key JSON value is identical. This retains absent versus explicit null, boolean versus number, integer versus float and nested types. The renderer still deep-copies inputs. Ordinary JSON semantics, not Python's permissive equality, determine sharing. The full existing generic decode merge and prefix logic is unchanged.

## Executed synthetic boundary

The new three-section work/observation fixture and its test were frozen before production edits. Its bodies are fictional bench observations, not benchmark examples. The final frozen fixture is `tests/fixtures/metadata_compaction_boundary.json`, revision 2. Under pinned official local `o200k_base`, tiktoken 0.14.0 ordinary-text counts of the **complete outer provider JSON** were:

| Same three complete typed records | Legacy encoder | Candidate |
|---|---:|---:|
| Full three-record wire | 725 | 597 |
| Actual pure production `pack()` output | 661 | 597 |
| Actual pure output representations | exact, exact, manifest | exact, exact, exact |

The complete-wire saving is 128 tokens on this one fixture. The final full three-record decoding equals every expected field, including complete bodies, locators, typed memory and authority. The mandatory three warnings and the declared scope warning are byte-identical; inputs/order are unchanged. Counting is of complete serializations, never an additive sum of records or substrings. This demonstrates encoding capacity and production **pure packing**, not an actual native retrieval result or quality/speed gain.

The same three full records also fit the other supported encoding: 598 complete outer JSON `cl100k_base` tokens. A test-only byte-preserving wrapper independently fits the same limit with and without its separator. This is not an actual stock MemoryManager delivery claim.

## Evidence and limitations

The sibling `performance-compaction-v1/evidence/` contains preregistration, exact RED/GREEN wires, tests, positive-environment run receipts and source entry/exit maps. An initial revision-1 fixture prediction was wrong (all three already fit); it also exposed a test insertion-order mistake. That attempt is retained and explicitly **not** counted as the meaningful product RED. Revision 2 failed at 725 > 700 before production edits and passed unchanged afterward. An intermediate encoder-only candidate failed the existing strict source-count validator; the small corresponding validator update is part of this coherent slice.

Compatibility covers actual old captured packet decoding, empty/single/multi records, mixed exact/summary/manifest, complete typed metadata and legacy untyped records, claims/time/contradiction/coverage/locators, strict JSON type/presence distinctions, input immutability, Unicode/escaping, malformed-default/count refusals and both named encodings. The existing pure measured-budget dependency subset is also executed without weakening any assertions. Child/network/provider/MemoryManager imports are refused by the phase-1 bootstrap. The engine-launching configuration test is deliberately UNRUN, not skipped-as-passed.

No actual engine, provider or MemoryManager initialization, native worker, full qualification, public-data retrieval/evaluation, reader/judge/model, deployment or profiling was run in this phase. The accepted parent source remains immutable. The encoder LRU already exists and is unchanged. Latency and public quality effects are unmeasured. Actual-native/full-gate execution requires separate parent release after its unchanged public baseline exits; see the external `NATIVE_GATE_DESIGN.md`.
