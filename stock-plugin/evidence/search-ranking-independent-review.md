# Independent search ranking review

Reviewed `stock_store.records` SQL ranking change in `/workspace/shared/elm_improve_now`, current working tree. No implementation files edited.

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
