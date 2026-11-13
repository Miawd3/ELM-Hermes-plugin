# Search ranking and profile-grant follow-up

Base public commit: 0b50a492aa6c0abd93de50c434859755039cf96f.

## Changes

- Query results now sort by distinct lexical query-word coverage BEFORE the 12-record limit; ties retain update recency. Scope/status filtering remains in SQL, substring matching and literal wildcard escapes preserved. No model calls, dependencies or DB migrations.
- Explicit local grant now requires --expect-home and reports the resolved path. --show-home is a read-only preflight. This addresses the Windows report's named-profile environment trap but does not prove chosen session/profile ownership.
- README now gives explicit PowerShell and POSIX environment/interpreter steps. No private Windows paths or logs copied into public evidence.

## Evidence and limits

71 standard-library tests pass (55 prior +9 ranking +7 grant preflight). JavaScript entrypoint assertions pass unchanged. Review independently tested ranking privacy/input behavior; no scope/injection blocker found.

The targeted regression confirms an older note matching all three query words is no longer buried behind 20 newer one-word notes. This is NOT general relevance or answer-quality benchmarking. Stopwords and irrelevant keyword-rich notes may still rank poorly. No automatic improvements to long-record packing, semantics or multi-hop queries are claimed.

`search-ranking-probe.json` uses the exact old/current Store.records API, same scoped SQLite database and warm common-term query. At1k/10k records the coverage ranking adds latency. Timings are synthetic local measurements, not end-to-end user latency and not a speed claim. The independent review's100k SQL-only probe also found a latency increase.

Windows tester reported local installation/save/search/isolation/off+regrant/restart passed on Hermes0.23.1; that report is owner-supplied, not independently rerun here. The new expectation guard is unit tested in Linux; actual Windows execution and current host runtime are still unverified. No attempt was made to fix or attribute the reported profile_scope_mismatch UI403.

No production repository publication or host changes made in this follow-up.
