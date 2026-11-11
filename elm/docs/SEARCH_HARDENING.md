# Experimental search hardening, 7 November 2026

This isolated candidate changes retrieval admission and determinism. It is not a live deployment or a claim of improved generated-answer accuracy. The existing experimental dictionary packet adapter remains unchanged.

## Retrieval behavior

- `elm search` retains its existing strict implicit-AND behavior. `--broad` still explicitly selects OR matching.
- `elm context` considers strict and broad lexical results together. A nonempty strict lane can no longer suppress the broad lane.
- Each lane uses the same existing project, namespace, archive, status, path, tag, and governed-history predicates. Both use the same policy timestamp. No new source roots or permissions are introduced.
- Each lane returns at most `--limit` candidates, default 24. Two independent read-only SQLite connections run the lanes concurrently. A one-term query runs only one identical lane.
- Candidate keys are deduplicated and ranked by equal-weight reciprocal rank fusion, with exact rational scores and fixed k=60. Final ties use best lane rank, strict rank, broad rank, then section key. The final candidate list is capped at the same `--limit`.
- Existing supplemental rows and packet selection remain in place, including the maximum of four supplemental rows and twelve packet records. Supplemental rows now also enforce the existing governed-history predicate, preventing them from reintroducing an ineligible claim.
- Candidate relevance scores in source rows remain BM25 values. RRF determines admission order; it does not replace provenance, authority, body text, or source identity.

The `retrieval` response field reports policy, k, lane count, per-lane/final limit, and strict/broad/final counts. Existing `fallback_used` keeps its historical meaning: strict returned no candidates and broad returned candidates. It is false when both lanes return results, even though broad admission still participates. Trace format is unchanged.

## Reproducibility

FTS sorting retains the existing score, authority, and update-date priorities, then resolves ties using the stable section key with binary collation. Supplemental sorting likewise ends with section key. Neither ordering uses document/section SQLite row IDs.

Markdown traversal is sorted by casefolded relative path and then exact relative path. The second key resolves casefold collisions. Sorting traversal is additional hardening: retrieval order remains stable even if files are deliberately indexed in reverse order.

This does not promise identical SQLite file bytes, numeric row IDs, execution latency, or results across changed source content, tokenizer/SQLite implementations, policy time, or scopes. Source section identities and packet bytes are the stable outputs tested on equivalent stores. Stable tie resolution may change previously observed historical packet order and cutoff membership; old benchmark metrics must not be silently reassigned to this new implementation.

## Concurrent writes and read-only boundaries

The command opens a fresh read-only monitor connection after any requested sync. It brackets lexical retrieval and supplemental selection with `PRAGMA data_version` and database file identity checks. An intervening commit or database replacement refuses the whole context read instead of emitting a mixed packet. Lane errors do not silently downgrade to a single lane. Each worker closes its connection.

Existing pending-governance-transaction and `--require-current-projection` guards remain active. The latter still holds the existing writer lock. Uncommitted caller connections are refused. No candidate source file, index schema, governance decision, or permission is changed by retrieval. Ordinary sync and disposable trace behavior remain as explicitly requested by the caller.

## Budgets and evidence limits

The final candidate cap is unchanged, but up to twice that many lane results are examined before deduplication. This is additional upstream work, not an equal-work comparison or a demonstrated speedup.

`--budget` still means `ceil(len(packet) / 4)` estimated tokens. It is not a tokenizer-measured cap, not a model billing limit, and not a bound on total runtime context. Candidate membership and actual packet tokens can increase. The audited historical comparison showed only limited evidence recovery and does not establish answer-quality improvement. This hardening does not implement the separate true-token-cap ranking/packing research proposal.

## Verification

Run the focused offline tests with:

```sh
python -B tests/test_search_hardening.py
```

They cover fresh stores with opposite creation/index orders, equal BM25 ties and cutoff prefixes, supplemental ties, strict-match suppression, exact RRF, caps, read-only concurrency, shared policy time, project/namespace/archive/status/path/tag/history restrictions, single-term behavior, lane failures, concurrent commits, file replacement checks, and estimated budget semantics.

The separate hardening evidence includes targeted replays of the two known LongMemEval admission failures and one LoCoMo admission failure, each in fresh forward/reverse-indexed stores. These are reused regression fixtures, not a new held-out evaluation. See the current validation receipt for the exact native Hermes runtime, completed checks, and remaining limits.
