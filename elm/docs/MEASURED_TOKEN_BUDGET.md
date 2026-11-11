# Measured context budgeting

This candidate adds measured **named-encoding text** limits to successful `elm_context` responses and a guarded background-delivery path. It does not discover the active model's tokenizer or measure a complete model request. No model/API call is made.

## Configure explicitly

New guided setup, operator init/adopt and native save_config default to `budget_mode=measured`. Supply both:

- `tokenizer`: `o200k_base` or `cl100k_base`. Choose deliberately for a reference count or after verifying compatibility with your actual model. Names are not model detection.
- `tokenizer_vocab`: absolute path to the matching official local `.tiktoken` file.

Install `requirements-tokenizer.txt` explicitly in the Python runtime that hosts the provider. It pins optional `tiktoken==0.14.0`; the engine child still runs `-s -S` without site packages, Python hooks or credentials. Do not install dependencies merely by selecting a model-facing tool. Measured operations never download files or silently switch to estimates.

Official vocabulary sources and required SHA-256:

| Encoding | Source | SHA-256 |
|---|---|---|
| o200k_base | https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken | 446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d |
| cl100k_base | https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken | 223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7 |

Download the chosen vocabulary as an explicit operator preparation step. It is not bundled. The provider checks the whole file hash and constructs an ordinary-text encoder directly from those bytes, bypassing network/cache/plugin discovery in `tiktoken.get_encoding`. Encoding patterns are copied from pinned tiktoken; its MIT notice is retained in `docs/licenses/TIKTOKEN_MIT.txt`.

```sh
python -m pip install -r requirements-tokenizer.txt
python -B setup_profile.py new --hermes-home /absolute/demo/profile \
  --root /absolute/demo/new-memory --project orion --budget 700 \
  --tokenizer o200k_base --tokenizer-vocab /absolute/assets/o200k_base.tiktoken
```

Missing package/native extension, unsupported version, missing vocabulary, hash mismatch and invalid configuration return explicit refusals. Configuration validates dependencies before committing the binding. An already initialized provider keeps its validated immutable encoder in memory; asset/config changes need a fresh provider.

## Exact successful-output contract

For `elm_context`, the bound covers the **entire exact JSON string returned by the provider**: packet, project, estimated_tokens compatibility field, token_budget metadata, quotes, escapes and delimiters. Every proposed record is serialized and measured as a whole, then the final string is measured again. It is not a sum of per-record costs. Dictionary common fields and prefixes can change when a record is added.

The compact response includes `token_budget={mode,tokenizer,limit,scope}`. Counts/hashes are available through `elm_status` / `get_status_config` under `token_budget_last`, outside the capped surface, avoiding a self-referential count field. The existing `estimated_tokens` remains explicitly an estimate of the inner packet only and is **not** used for measured admission. `manage.py context` emits the same measured JSON bytes without adding a newline.

Selection keeps retrieval order and project/governance policy. It tries complete exact sources first, then at most one canonical summary per document, then manifests, with at most 12 records. Coverage identifies omitted sources. It never truncates a selected text. Measured selection is not anchored to the old estimated packet, which could already have dropped important evidence. This changes packet membership and does not prove better answer quality.

A hash-pinned vocabulary's maximum token byte length permits a necessary byte-length precheck for enormous candidates. It never substitutes a token estimate for admission. For feasible sizes, the full final text is always tokenized. UTF-8 is strict: lone surrogates are refused instead of silently replaced. Special-token-looking source strings use ordinary-text tokenization. Unicode normalization is not applied. Literal escapes are preserved; host-dangerous strings remain safely JSON-escaped and decoded only once as data.

## Background delivery and stock Hermes

`recall_mode=explicit-only` is still the default. Stock Hermes's authoritative-reference wording remains a trust mismatch; background mode is not recommended for live use.

Measured background additionally needs a hosting integration to pass `elm_prefetch_max_chars` to `initialize`: the **actual frozen, registration-time no-spill character limit**. This is a trusted host argument, not a saved/model-supplied guess. The value must be a positive integer no larger than the host's effective unchanged limit. If spilling is disabled, a hosting integration may provide a deliberately chosen finite ceiling. Stock Hermes does not pass this receipt. Without it, ELM starts no measured prefetch and returns no injection; status reports configured intent separately from effective `automatic_recall=false`, with `host_budget_unverified`. Explicit retrieval remains available. No host files are patched.

With a receipt, packing respects both token cap and raw-packet character ceiling. The actual imported host formatter is probed and must preserve every serialized packet byte. The full tool JSON, `build_memory_context_block(packet)` (multimodal text part), and `"\n\n" + build_memory_context_block(packet)` (string-message suffix) each independently fit the requested token cap; those alternative delivery surfaces are not added together. Counting both wrapper variants avoids assuming prefix-token costs are additive or monotone. Warm delivery rechecks encoding, source count, character ceiling and full formatted token count. No over-budget omission notice is substituted. A budget too small for mandatory warnings/metadata fails clearly.

The native integration harness forwards the real manager snapshot explicitly to demonstrate the supported integration, and separately verifies that ordinary stock initialization fails closed. This is not a claim that unmodified stock initialization automatically enables measured background recall.

## What this does not bound

- Hidden chat/template framing, role delimiters, schemas, system prompt or billing overhead.
- Unknown model tokenizers or tokenization spanning adjacent user/plugin text boundaries.
- Combined output of other providers/hooks or the full context window.
- Error/status responses, `elm_read`, episode recall, capture limits, notes/governance or compaction. Their existing limits remain unchanged.
- Host transformations after the verified boundary, changed spill settings, dishonest integration receipts, malicious local files or malicious installed packages.

Use the declared counts as exact counts of those strings for that encoding, not as a whole-request token guarantee.

## Legacy and migration

Historic v1 bindings with no budget_mode load as `legacy-estimate` to preserve existing behavior. Their status labels `budget_mode=legacy-estimate`; context results additionally label `method=ceil_chars_div_4`, `scope=packet_only`. New dependency-free use must explicitly request `--budget-mode legacy-estimate` (or save_config equivalent). This estimate is **not an upper bound**, especially for Unicode and JSON escaping. It does not cover provider JSON or host wrappers.

Re-adopt an existing binding deliberately with measured settings and start a fresh provider/conversation to migrate. Guided setup refuses overwrite as before. No automatic migration or dependency installation occurs. The direct low-level engine `context --budget` CLI remains labeled legacy-only; use the provider or `manage.py context` for measured delivery. The hidden `--packing-input` engine path is an internal read-only, scoped input transfer, not a new model tool; it requires no-sync and no-trace.

## Validation

Set `ELM_TEST_VOCAB` to local o200k and `ELM_TEST_CL100K_VOCAB` to local cl100k. Install the optional package in the testing runtime. Run `tests/test_measured_budget.py` and, with the pinned dependency-prepared stock host, `tests/native_measured_budget.py`. Missing assets explicitly skip those optional real-tokenizer tests, so a legacy-only regression is not measured qualification. The final candidate evidence includes both encodings, native CPython 3.14, unit/native regressions and independent adversarial review. No paid model calls or live deployment were used.
