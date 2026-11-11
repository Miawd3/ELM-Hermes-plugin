# Review repairs and qualification boundaries

The original RC1 artifact is frozen. Although its 18 tests/native checks/catalog admission passed, independent review reproduced five missing correctness cases. This revised source repairs those cases; its source suite passed 28 tests (27 provider cases plus the fresh-init metadata regression). Final extracted-artifact checks are recorded separately in the companion `acceptance-rcN.json` receipt.

## Corrected behavior

- **Committed WAL changes:** a short, read-only SQLite transaction snapshots document identities/hashes/indexing timestamps, projection metadata and project claim boundaries. Revision comparison after retrieval and before cache delivery observes committed WAL data; no file-stat approximation or retained monitor connection is used. A real operator rebuild remains possible while the provider lives.
- **Time-only changes:** a packet is valid only until the next accepted-project claim activation/expiry boundary, including future claims omitted from the packet. Crossing a boundary discards it and queues a fresh read. No guessed TTL or file edit is required; a backward clock before the cache's sample also invalidates it.
- **Canonical verification:** subject/predicate filters use the engine's surrounding-whitespace normalization and unambiguous option-value encoding. Verification checks the actual returned proposal/claim IDs.
- **Session provenance:** receipt session identity is captured under the session-switch lock before mutation dispatch, not after readback completes. A later session switch does not relabel the originating mutation.
- **Literal CLI text:** the internal subprocess bridge places every trusted option before `--`, followed by one unchanged query value. Leading-dash text cannot become CLI options. Environment scrubbing, no-shell execution, timeout/unknown-outcome handling and identity/projection checks remain.

The native consumer script now actually dispatches all four provider tools through the real stock `MemoryManager`; registration alone is not counted as dispatch. `elm_read` asserts exact configured-project source text, and `elm_status` asserts healthy/project/mode state.

## Time-fixture correction after RC2

RC2's extracted suite exposed a test race: seven-second validity windows could elapse during mutation/readback/warming, before the intended initial-state assertion. That failed candidate remains preserved. The two temporal tests now control the provider and actual engine process clocks independently of setup latency. A test-only bootstrap still executes the real vendored CLI/parser/retrieval against the synthetic canonical store; no engine files or responses are replaced. Production uses the unchanged ordinary module launcher. Separate subprocess-isolation/argument tests cover that production boundary.

Both revised temporal tests passed. The owner also ran the revised expiry test against a disposable extraction of RC1 production code: it failed precisely because expired memory remained cached, proving the clock fixture still catches the original defect. This corrects the harness rather than disguising a production failure or merely increasing sleep/retry allowances.

## Costs and limits

Warm cache checks retain the readiness subprocess and add a metadata scan proportional to indexed document count plus configured-project claims. Large-store warm-cache latency has not been measured. Cold prefetch stays nonblocking; explicit `elm_context` remains the reliable first-turn path.

Consistency relies on the pinned engine's metadata contract, not arbitrary-SQL-tampering detection or an OS sandbox. Snapshots validate evidence at check points; they cannot freeze another operator's changes throughout a later model answer. Hostile same-user filesystem replacement, cross-platform behavior, process-kill/disk-full recovery and autonomous real-model tool selection are not certified.

Detailed RED/GREEN logs, corrected intermediate fixtures and the independent-review findings are in the companion engineering evidence, not hidden behind the final passing total. The replaced retained-connection approach's earlier passing suite is not the final qualification. No live store/profile, canonical memory, public repository or competition submission was changed by these tests.
