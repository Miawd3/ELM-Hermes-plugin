# Frozen lexical search v1 contract

Frozen before r37 independent/held-out results. No model calls, parameter fitting, stemming, translation, synonyms, language-specific segmentation, or implicit provider integration. Native recall is unchanged.

`search.private.query` and `search.project.query` accept only `query` (plus native session envelope). UTF-8 bytes 1..512, 1..64 distinct Unicode `\w+` terms after casefold; punctuation-only invalid. Explicit authenticated local read, not proof of a human caller. Project uses existing expanded consent. The exact current scope manifest is bounded by existing store caps; no recall20 prefilter. Wiki's approved/current dependency and active-source closure is narrowed by `recall_records`, including its sensitive/user-fact restrictions and transitive exclusions. No foreign records are fetched or ranked.

Score = number of distinct query terms also in title + newline + text. Keep only score > 0; descending score, stable newest `updated_at`, then ID descending ties. No threshold tuning. Lexical overlap does not prove relevance. No match does not prove semantic absence.

Greedy indivisible complete record packing, including every record field, dependencies and bound citation metadata; skip records that do not fit and try later records. Never truncate titles, text, qualifiers or citations. The complete returned canonical JSON **string** (ASCII escaping, sorted keys, compact separators) must measure <=700 ordinary-text tokens using named `o200k_base`, pinned `tiktoken==0.14.0` and pinned official vocabulary. Transport JSON-RPC wrapping/escaping and provider message framing are NOT included; there is no provider call. No inferred model tokenizer or token estimate.

Decoded payload fields: schema=1, lane, algorithm=`literal_overlap_v1`, tokenizer=`o200k_base`, token_limit=700, snapshot_key, status, eligible_count, matched_count, omitted_count, records. All metadata is inside the measured string. Status: no_match when no positive overlap; evidence_exceeds_budget when matches exist but no whole record fits; partial when some matching records are omitted; matched when all fit. Counts reveal only already-authorized eligible scope. No omitted IDs or bodies. Metadata-alone overflow fails closed. Packing reserves the long evidence_exceeds_budget status and verifies the final serialized output again.

Configuration: native plugin setting `search_tokenizer_vocab` is an absolute local vocabulary path, selected by the host configuration, never RPC input. Install optional pinned tokenizer and correct vocabulary separately; no network/download, legacy estimator fallback, import-path changes, or hidden installation. Missing/mismatched assets/software return fixed `search_tokenizer_unavailable`. Configuration changes require normal plugin reload. Tokenizer construction occurs inside the current authenticated read fence; unloaded service refuses.

Evaluation: compare old native recall20 order, full authorized queryless pool with the same payload packing, and actual public lexical search. Report candidate censorship separately. Whole required evidence too large for the budget is a miss, not silently truncated success. No claims of answer correctness from record presence; held-out synthetic results do not establish broad production retrieval quality. UI remains unregistered pending independent gate.

Dependency closure governs eligibility, not atomic packet grouping: all dependency metadata is retained, but a dependency's body may not be delivered if it has no lexical match or cannot fit. A delivered dependent record therefore does not imply complete semantic supporting evidence was included.

## Integration outcome — 2026-11-12, r37

The preceding contract was frozen before evaluation. After independent held-out review and explicit integration approval, **Scoped lexical search is now registered as an optional user-invoked ELM settings page**. The earlier “unregistered pending gate” sentence records its pre-evaluation state, not current availability. The frozen design/preregistration artifact is unchanged. Automatic recall, default model behavior and external model execution remain unchanged. Literal matches can be irrelevant even when no answer exists; there is no semantic abstention. No benchmark score is a product guarantee.

### Actual host configuration

Merge this setting into the intended Hermes profile's existing `config.yaml`, preserving other plugin entries and settings:

```yaml
plugins:
  entries:
    elm:
      settings:
        search_tokenizer_vocab: /absolute/local/path/o200k_base.tiktoken
```

On Windows, use the real absolute local path, for example a single-quoted YAML value `'C:\Users\Example\tokenizers\o200k_base.tiktoken'`; this is an example, not a path supplied by the plugin. Install optional `tiktoken==0.14.0` in the Python environment actually running Hermes and supply the pinned official vocabulary file separately. Expected vocabulary SHA-256:

```text
446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d
```

Use normal plugin reload after configuration changes, then explicitly run a search. This setting alone does not enable a disabled plugin. Do not replace the whole configuration with the snippet. Neither the search page nor the backend installs packages, downloads a vocabulary, guesses a tokenizer or falls back to character estimates. The first query can be slower while the local tokenizer loads.

Configuration evidence: native `PluginContext.get_config` reads `plugins.entries.<plugin_id>.settings`; `tests/test_native_lexical_search.py:search_install` exercises the exact nested configuration through the real plugin manager before native authenticated searches.
