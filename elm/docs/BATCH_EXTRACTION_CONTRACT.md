> Current release document. Run command examples from the installed `elm/` directory. The release README and CAPABILITIES.md define the product-wide contract.

# Optional offline batch extraction contract

2026-11-06. Experimental extension to the isolated ELM evidence/forgetting candidate. Synthetic fixtures only. Disabled by default. No deployment or live-profile action is implied.

## Delivered boundary

`elm_plugin/batch_extraction.py` provides an operator/test-only, model-agnostic contract. It prepares bounded local data and validates a manually supplied JSON response. It does not call a model, execute source instructions, read credentials, transmit data, write a file/database, call the governance engine, submit proposals, accept claims, or change provider registration. Existing capture, recall, forgetting, automatic marker extraction, and prompt surfaces are unchanged.

The optional extractor can only choose an exact source span and suggest three labels: kind, topic, and interpretation. Code supplies source identity, provenance, scope, hashes, retention checks, candidate IDs, and candidate status. The output has no subject/predicate/object write payload, confidence, approval, authorization, supersession, or accepted-truth field controlled by the extractor.

This is deliberately **span selection, not autonomous fact extraction**. No adapter to a model endpoint or the existing proposal queue is delivered. A future model invocation would be a separate integration requiring explicit data-sharing authority, transport/security design, token/cost limits, and its own review. This local opt-in is not permission to send the sources to any service.

## Trust and meaning

An exact citation proves only that the selected Unicode code-point slice equals text currently stored in the captured message. It does **not** prove:

- That the excerpt entails a proposed proposition or is a true fact.
- That the sender is the speaker quoted inside the text, or authored pasted material.
- That a source is an assertion rather than quotation, negation, hypothesis, joke, instruction, or outdated claim.
- That a sender ID was independently authenticated by this adapter.
- That a statement authorizes a subsequent action or should be accepted as memory.

Every validated item is `quarantined_candidate`, with `entailment`, `attribution`, and `truth` set to `not_evaluated`. `interpretation_basis` is `unverified_extractor_label`, `requires_context_review` is true, and acceptance/authorization are false. Even an extractor that marks quoted or hypothetical content as `assertion` cannot change these values. A misleading literal substring can pass the citation check; the full selected message remains present for contextual review. Surrounding conversation beyond selected messages is not included, and completeness of semantic context is not claimed.

Source text can contain prompt injection. Structured JSON and escaped serialization are not prompt-injection immunity. The module never follows source instructions or extractor-supplied actions. Any consumer must continue treating source text, quotations, topic labels, and interpretation labels as untrusted data. This work does not change the inherited stock Hermes prefetch wording limitation.

## Separate explicit configuration

Both capture and explicit recall must already be available and opt-in. A trusted caller may additionally create this profile-local configuration for a disposable test profile:

```json
{
  "format_version": 1,
  "enabled": true,
  "root_id": "<current pinned root ID>",
  "project": "<current pinned project>",
  "author_id": "<one caller-provided user author ID>"
}
```

Filename: `elm_batch_extraction.json`. No command in this extension creates it. `BatchExtraction.from_recall(recall)` returns `(None, "disabled")` without it. The configuration is strictly typed, scope-checked, at most 2 KiB, and pinned by its byte hash. A changed/removed configuration, changed capture/recall configuration, changed binding/root identity, or unsafe source/configuration path prevents further disclosure. A change observed during use permanently revokes that in-memory batch, even if the old configuration later returns.

Only explicitly selected, sealed, currently live **user** sources with this exact recorded author are eligible. Assistant sources, unknown authors, other authors, unsealed episodes, redacted source text, and cross-scope locators are refused. Author and speaker metadata remain caller observations, not proof of identity. The module reads through existing recall integrity checks, including the complete live user/assistant pair. It never substitutes proposal copies or replay-ledger entries for unavailable evidence.

## Operator/test interface

```python
from elm_plugin.batch_extraction import BatchExtraction

contract, reason = BatchExtraction.from_recall(existing_explicit_recall)
request = contract.prepare([verified_source_locator])
# No model call or transport is provided or executed here.
result = contract.validate(request["batch_id"], supplied_json_text)
current_result = contract.review(request["batch_id"])
contract.revoke(request["batch_id"])
contract.close()
```

`prepare` accepts only a bounded nonempty list of exact locators in the existing profile scope. It returns a batch ID, pinned scope/root/project, author, full selected messages, caller-observed metadata, stored-text hashes, and a constrained response contract. Locators are not authorization capabilities. The module pins the complete ordered source manifest, not merely the selected excerpts. Request mutation cannot alter the internal manifest.

The request also contains a JSON Schema with this batch ID and exact source aliases. Its schema URI is descriptive; the module does not fetch it or invoke a schema service. Schema conformance is weaker than adapter validation, especially for exact citations, liveness, integer token types, and regex anchoring. The validator independently checks everything described below.

The response is exactly one JSON object, with no Markdown wrapper or repair step:

```json
{
  "format": "ELM-BATCH-EXTRACTION/1",
  "batch_id": "<exact prepared batch ID>",
  "candidates": [
    {
      "source_id": "s0",
      "start": 0,
      "end": 25,
      "quote": "I prefer concise answers.",
      "kind": "preference",
      "topic": "answer_style",
      "interpretation": "assertion"
    }
  ]
}
```

Offsets are Python Unicode code points, not UTF-8 bytes, UTF-16 code units, grapheme clusters, or token positions. No whitespace or Unicode normalization occurs. Integer offsets must satisfy `0 <= start < end <= len(source_text)` and the quoted text must equal the exact slice. Boolean/floating offsets, duplicate spans, empty/whitespace quotations, unknown fields, duplicate JSON keys, NaN/Infinity, excessive nesting, malformed JSON, and fabricated source IDs are refused atomically. `candidates: []` is valid abstention, not evidence that no relevant facts exist.

Allowed kinds: `note`, `preference`, `decision`. Allowed interpretations: `assertion`, `quoted_speech`, `hypothetical`, `negated`, `instruction`, `uncertain`. Topic is a lowercase ASCII label matching `[a-z][a-z0-9_.-]{0,63}`. These labels cannot confer authority or factual status. Topic labels may themselves contain untrusted source-derived text, within the 64-character limit; they are not privacy-free metadata.

The validator never silently repairs malformed output or retries a model. A failed batch creates no partial candidates. At most three attempts are admitted per batch. A successful identical raw JSON response returns the same candidate IDs after current source revalidation. Changed output after success is refused, including whitespace-only changes. After three failures the batch stays failed. IDs and retry counters are process-local; a restarted instance has no knowledge of old batch IDs. This is not durable exactly-once processing or a global quota across callers/restarts.

## Conflicting facts

All selected excerpts remain separate. Within one batch, different excerpts carrying the same suggested kind/topic receive `potential_conflict_same_key_different_excerpt: true`. This is a coarse review hint, not semantic contradiction detection. It can flag compatible statements, miss paraphrases with different topics, and cannot detect conflicts across batches or canonical memory. There is no winner selection, timestamp-based overwrite, deduplication into truth, automatic contradiction resolution, or supersession.

## Revocation and retention

Sources and configuration are re-read before validation, before review/replay, and again at the final disclosure boundary. Forgetting either paired message, source expiry, loss of complete pair linkage, source/hash/metadata changes, or scope/configuration withdrawal prevents a late result from being returned. Explicit local batch withdrawal also works after configuration/source loss. Closing revokes all known batches.

The batch registry stores only locators, a manifest fingerprint, counters/status, response digest, and bounded selections without quotes. It holds no copy of full source text and creates no durable derivative store. The bounded topic labels remain source-derived data until batch revocation/close. On observed source/configuration revocation, selections and response digest are cleared. Metadata hashes and locators remain until the instance is released; they are not anonymization.

This is a logical disclosure boundary, not secure erasure. Already returned requests/results, caller caches, model contexts, process memory remnants, backups, or separately saved files cannot be recalled. In-memory source/configuration revocation is observed on the next contract operation, not by a background watcher. There is inevitably a race after the final check and before any caller's later use. No result token authorizes external consumption, and no atomic lease over future downstream actions is provided. Persisting derivatives or integrating dispatch would require a separate revocation-aware design.

## Exact bounds

- Selected sources: 1–8, each no more than 8,192 stored UTF-8 bytes.
- Whole serialized request: at most 32,768 bytes under the contract's ASCII-escaped `encoded` serializer. Refused rather than truncated. No tokenizer guarantee is claimed.
- Raw response: at most 32,768 UTF-8 bytes; at most eight JSON nesting levels.
- Candidate count: at most 32. Each quote: at most 1,024 Unicode code points.
- Whole serialized review result: at most 65,536 bytes, using the same serializer.
- Attempts: at most three before success/exhaustion; no automated calls.
- Lifetime batch registry: eight records per instance, including failed/revoked/validated records. No eviction to bypass the in-instance bound.

Caller-side transport/input buffering, the host's existing bounded source database, and caller-created multiple instances are outside these bounds. The existing recall source reader still uses its own captured-store bounds. A serializer other than `encoded` may produce different byte counts; use the exported serializer for the documented output bounds.

## Synthetic verification

Developer tests are in `tests/regression/test_batch_extraction.py`; independent adversarial tests are in `tests/regression/audit/test_batch_extraction_independent.py`. The root `run_validation.py` executes both with the full inherited suite. See `VALIDATION.md` at plugin root for prerequisites and commands, and the separate release evidence for exact source hashes, logs and counts.

These tests verify deterministic contract boundaries, not model quality, semantic extraction accuracy, speaker authentication, universal injection resistance, or production readiness. This process-local validator remains separate from the current durable inbox and operator bridge.
