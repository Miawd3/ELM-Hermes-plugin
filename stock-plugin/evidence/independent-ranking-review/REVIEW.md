# Independent search ranking review

Reviewed `stock_store.records` SQL ranking change in the isolated candidate checkout, current working tree. No implementation files edited.

## Checks
- Existing 55 standard-library tests passed independently.
- Nine independent combined behavior/adversarial checks passed: old exact match ahead of twenty newer partial matches; duplicate query terms; cross-chat exclusion; pending exclusion; literal underscore; Unicode casefold; SQL-like input cannot bypass scope; stable pagination; recency retained for tied coverage/empty query.
- Values remain parameter-bound. The query structure is derived only from bounded token count (20), not user SQL. Escaping for LIKE wildcard underscores preserved.
- Scope/status filters remain in WHERE before sorting and LIMIT, existing transaction/revision checks unchanged.

## Performance
Synthetic isolated SQL probe:100,000 approved scoped records, three terms, six runs per method, medians after first warmup:
- Previous recency SQL:20.46 ms.
- New coverage SQL:57.08 ms.
This is not a broad benchmark. It measures only SQL retrieval on a common-term synthetic workload. Ranking adds roughly2.8x latency here, so do not advertise speed gain. No index or new dependency introduced.

## Limitations
- Coverage measures distinct matching query substrings, not semantic importance. Stopwords and long irrelevant notes containing many terms can outrank a concise answer.
- Tags contribute to matches as before; long/keyword-rich notes may dominate.
- Top12 and2400-byte whole-record packing remain separate quality limitations; change does not fix them.
- No answer-quality, Windows or live-model claim follows from this review.

## Recommendation
No security/code-level blocker found for this bounded lexical-ranking change. Reasonable as a targeted fix with explicit release-note caveats and new tests, but not validated as general retrieval superiority. Add independent test cases to permanent suite and preserve measured latency tradeoff.

## Final review: profile-home CLI guard

Re-reviewed final `local_grant.py`, README and newly added tests. Independently reran **71 tests: all passed**. Also ran four real temporary-SQLite checks using mocked public Hermes home resolution: show-home leaves storage absent; mismatched expected path refuses before creating DB; exact named profile grant succeeds and reports target; exact-profile revoke disables the session.

The new explicit expected-home comparison precedes Store construction. Absolute paths are required, symlinks normalized, and missing directories refused. No new scope expansion mechanism was introduced. `--show-home` is read-only with respect to ELM storage. Docs correctly state that standalone Python does not inherit `hermes -p` selection, placeholders require actual profile/interpreter paths, and echoing the same environment path cannot prove the operator selected the right Desktop session/profile.

No remaining code-level blocker found. This is a deliberate CLI compatibility change: existing scripts must add `--expect-home`. It does not migrate or remove erroneous old grants and does not qualify actual Windows installation. Current test environment is Linux with mocked public home resolver, not a real Windows/Hermes run.
