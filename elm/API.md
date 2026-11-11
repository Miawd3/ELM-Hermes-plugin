# ELM integration API, release contract v1

This is an experimental compatibility reference for the exact release tree, not a promise of stable future schemas. Inputs and outputs are JSON except where noted. Fixed model-facing schemas live in `elm_plugin/schemas.py`; unknown fields and scope/authority overrides are rejected.

## Native provider

`register(ctx)` registers a new `ElmMemoryProvider` using the public Hermes MemoryProvider extension. This exclusive provider has no general plugin tools/hooks/capabilities. Hermes owns model execution and selection; ELM does not call a model.

Configuration `elm.json` uses `format_version=1`: absolute root, project, mode, budget, root ID, identity SHA-256, optional recall_mode, budget_mode, tokenizer and tokenizer_vocab. New setup defaults to measured and requires a supported named tokenizer plus its absolute local vocabulary path; historic bindings without budget_mode retain labeled legacy-estimate behavior. See [measured budgeting](docs/MEASURED_TOKEN_BUDGET.md). Omitted recall_mode means explicit-only. Supported recall modes: explicit-only and legacy-background; the latter exposes untrusted evidence to the stock authoritative-prefetch wrapper. Supported mutation modes: read-only, proposal-only, autonomous.

Setup schema, save_config and get_status_config support the public host setup flow. save_config explicitly re-adopts/replaces the binding; guided setup_profile.py is the non-overwriting entrypoint. Config/store changes require a fresh provider instance. Root identity and relevant settings are revalidated at use boundaries; no automatic root adoption/repair.

| Tool | Input | Result/refusal |
|---|---|---|
| elm_context | query string, max 2000 chars; optional paired lane/purpose | packet, project, estimated_tokens, token_budget; measured mode caps exact JSON wire; no_query for whitespace; never widens project |
| elm_read | section UUID locator, optional elm://section/ prefix; same optional paired lane/purpose | exact content, typed restrictions when declared, provenance; only stable section IDs, 12000-char expansion limit |
| elm_status | empty object | readiness/binding/mode/recall_mode/automatic_recall plus optional layer states; not full audit |
| elm_episode_search | query max 256 chars, optional limit 1–8 | bounded lexical current evidence with scoped locators; requires capture + recall opt-ins and primary context |
| elm_episode_read | exact scoped locator from search | complete stored scrubbed source or refusal for expiry/scope/oversize/inconsistent paired evidence |
| elm_note | operation, submission_id, subject, predicate, object, valid_from, rationale, source_refs | exact engine disposition + separate receipt/readback; permitted by binding + primary context only |

`elm_note` operation is propose or remember. Stable ID is `submission_<uuid>`. Reuse the identical ID and payload on a deliberate retry; changed payload under the ID is refused. UTC observation time must stay identical. source_refs are an array (empty when absent), maximum 16 URI/digest strings, not fetched or independently verified. Model notes are normal-sensitivity only; do not supply raw chats, secrets or sensitive records.

Successful engine effects and receipt/readback verification are separate fields. Duplicate does not activate a new claim. Conflict can defer a proposal without changing the old claim. Readback failure does not undo a committed mutation. Timeout is an unknown outcome: inspect operator history before any retry. No provider tool accepts, ratifies, supersedes, deletes governance or changes trusted source roots.

## Typed logical document lanes

`elm_context` and `elm_read` accept optional paired `lane` / `purpose`: `user` / `communication`, `work` / `task`, or `reference` / `task`. Omit both for legacy-compatible work/task. The pair is enforced independently on every read; it does not change the configured project or create a user identity grant. Typed records carry a validated `memory` object through exact/summary/manifest/fallback serialization. Declared inferences are uncertain, communication-only and cannot be promoted by a misleading kind; declared sensitive-health inferences are withheld. Legacy untyped material remains unclassified. Typed ingestion is operator source editing plus explicit sync, not new `elm_note` fields. See [typed-memory fields, migration, evidence restrictions and limitations](docs/TYPED_MEMORY.md).

## Operator CLIs (existing contracts)

All require explicit profile scope. Run each with `--help` for exact syntax.

- `setup_profile.py new|adopt`: safe first configuration, defaults off/read-only/explicit-only; refuses overwrite. Flags described in docs/WORKFLOW.md.
- `manage.py init|adopt`: explicit lower-level binding setup/replacement. `status`, `context QUERY`, `read SECTION [--document]`, `sync`, `doctor`, `history` use the existing binding. `sync` explicitly refreshes derived index; normal tools do not silently sync.
- `manage.py episode-forget-preview` then `episode-forget --confirm-plan`: digest-confirmed local forgetting.
- `inspect_episodes.py status|candidates|evidence`: read-only local inspection, source text only with explicit flag; does not infer canonical acceptance.
- `review_candidates.py prepare|validate|list|review|revoke|revoke-all`: durable quarantine, with possible privacy-tombstone writes while reading. Exact source-text flags and stdin response contract in docs/DURABLE_INBOX.md.
- Same review CLI's `operator-prepare|operator-inspect|operator-list|operator-submit|operator-revoke|operator-revoke-all|operator-reconcile`: separate review bridge. Submit requires current reviewed plan hash and literal confirmation. Reconcile never submits/retries/accepts.

## Offline Python APIs and states

- `BatchExtraction`: process-local batch IDs and bounded exact-span validation. No persistence, transport or governance bridge itself. Strict response format `ELM-BATCH-EXTRACTION/1`.
- `DurableCandidateInbox`: restart-persistent prepare/validate/review plus explicit revoke control. Rows pending → validated or failed; revoked/expired rows retain tombstones. Source/configuration changes fail closed. Lifetime 128 rows, 3 validation attempts per batch, no ID recycling.
- `OperatorReviewBridge`: supplied semantics produce a review plan. Prepared → submitting (durably before dispatch) → submitted on confirmed result. Uncertain stays submitting/unknown; revocation does not erase uncertainty. Lifetime 128 rows. No automatic acceptance or correction.
- Reconciliation classifications: matched, absent_uncertain, conflict, unverifiable, unavailable. Only exact comparable canonical payload proof can record historical submission locally. All outputs deny retry permission; absent does not fence a delayed original dispatcher. Missing/expired/scrubbed payload proof remains blocked.

Detailed contracts are self-contained under docs/. They define byte/row bounds, refusals, observed opt-out, corruption handling and privacy limits. Local consistency hashes are unkeyed and do not authenticate a hostile local filesystem owner.

## Context admission diagnostics

The experimental context response adds `retrieval` with `policy="strict_broad_rrf"`, `rrf_k=60`, `lane_count`, `per_lane_limit`, `final_limit`, `strict_count`, `broad_count`, `candidate_count`, and `fallback_used`. The existing top-level `fallback_used` retains its old strict-empty/broad-nonempty meaning. See [search hardening](docs/SEARCH_HARDENING.md). Ordinary `search` semantics are unchanged.

## Measured accounting and host integration

Successful context JSON includes accounting mode and scope. Exact final counts, tokenizer/vocabulary identity and SHA-256 are reported separately in status. `automatic_recall_configured` records intent, while `automatic_recall` reflects the missing-host-budget guard. `initialize(..., elm_prefetch_max_chars=N)` is a trusted integration receipt for the frozen actual host no-spill limit, unavailable from stock initialization. See the complete [contract and exclusions](docs/MEASURED_TOKEN_BUDGET.md).
