# Typed memory separation — experimental native slice

This candidate adds validated **logical document lanes**, not multi-user authentication, cross-project personal identity or a classification model. It is not activated in any live profile. Definitions are experimental, not ratified categories for the user's canonical memory.

## Native intent

`elm_context` and `elm_read` accept the same optional pair:

| lane | purpose | Eligible sources |
|---|---|---|
| omitted | omitted | Same as `work` / `task`; legacy-compatible default |
| `work` | `task` | Typed work evidence plus legacy-unclassified documents |
| `reference` | `task` | Typed reference documents only |
| `user` | `communication` | Typed user statements/preferences, concrete observations and uncertain communication hypotheses |

Both fields must be supplied together. Other combinations, arrays, wildcards, capitalization changes, composition and unknown fields are refused. There is **no last-query grant**: an `elm_read` of a user locator needs `user` / `communication` on that call even immediately after a user-lane query. Root/project/authority/owner/user-ID overrides are not accepted. Selection never changes the adopted root, root-identity digest, project, claim eligibility or permission mode. The personal lane is initially bounded to that same existing profile project. It is not global personal memory.

Examples (tool arguments, not operator commands):

```json
{"query":"numbered steps","lane":"user","purpose":"communication"}
```

```json
{"section":"elm://section/section_11111111-1111-4111-8111-111111111111","lane":"user","purpose":"communication"}
```

The sample UUID is syntax only. It is not an installed record or a valid authorization token.

## Document declaration

Use the engine's existing contiguous `Key: value` metadata header before its first heading, entirely within the first 80 lines. Add all five fields:

```text
Memory lane: user
Memory kind: hypothesis
Memory sensitivity: normal
Memory source: elm://section/section_11111111-1111-4111-8111-111111111111
Memory basis: inference
```

Declarations apply to the **whole document**, including summaries and all sections. They are validated independently of arbitrary tags, document title, Scope prose, Status and body text. A mixed-purpose document needs an explicit operator decision to split/reclassify; the engine does not silently classify its paragraphs.

Closed domains:

- lane: `user`, `work`, `reference`.
- kind: `explicit_fact`, `preference`, `observation`, `hypothesis`.
- basis: `explicit_statement`, `direct_observation`, `source_document`, `inference`.
- sensitivity: `normal`, `sensitive_health`.
- source: exactly one stable local `elm://section/section_<uuid>` locator.

Kind/basis combinations:

| kind | permitted basis |
|---|---|
| `explicit_fact` | `explicit_statement`; also `source_document` for work/reference only |
| `preference` | `explicit_statement` |
| `observation` | `direct_observation`, `source_document` |
| `hypothesis` | `inference` |

`explicit_fact` means a **declared explicit statement**, not independent verification or accepted governed truth. A caller cannot label a declared inference as an explicit fact/preference by changing only kind. Misdeclaring the prose and every metadata field consistently is outside this mechanism: there is no semantic DLP or truth detector.

Typed records require a path in `20_projects/<project>/`; governed claim documents cannot carry these declarations. Unknown reserved `Memory ...` header keys (including identifier-like suffixes), indented/malformed reserved declarations, duplicates, partial declarations, invalid values, declarations hidden after an unknown header barrier, and declarations beyond the header limit fail ingestion. The reserved-declaration scan and metadata header use the section parser's same real-heading grammar; `#not-a-heading` cannot hide later declarations. Every recognized reserved declaration must actually be consumed by the canonical metadata grammar; a later ordinary field advancing the header endpoint cannot validate skipped declarations. Noncanonical delimiter whitespace is refused rather than normalized into a legacy downgrade. Ordinary examples after a real heading remain body data, not declarations. Sync reports the error; it does not index a new malformed document as legacy. Native guarded reads refuse an unhealthy/stale projection. An old derived entry may remain after a failed sync; this is not permission to use an unguarded stale operator index.

The source must resolve in the same project at admission, and must satisfy the current archive/claim-time restrictions. Missing/foreign evidence withholds the typed record from both context and direct reads; canonical text remains available to the operator on disk. The source is not automatically expanded, and a source link does not grant read access to its lane. Source existence and a format-valid basis do not prove that the source supports the declaration. References are not cryptographic evidence snapshots; explicit source/record corrections plus sync are visible to subsequent fresh readers, but semantic entailment and automatic derived-note invalidation are not implemented.

## Evidence basis, uncertainty and health

Every delivered typed record includes a `memory` object with `schema_version: 1`, lane, kind, basis, sensitivity, source and restriction. It is present in dictionary exact/summary/manifest records, legacy textual fallback blocks, engine source/omission metadata and native `elm_read`.

Authority labels are derived from the validated declaration, never from an `Authority:` or `Status: accepted` body/header assertion:

- explicit statement: `declared_statement_not_verified`.
- preference: `declared_preference_not_verified`.
- observation: `unverified_observation`.
- hypothesis: `unverified_hypothesis`, with `communication_only_uncertain` restriction and provisional packet class.
- explicit sensitive-health self-report: `declared_self_report_not_medically_verified`.

All records remain `untrusted_memory_data`. Document Status is preserved as source provenance, not the epistemic status of the person or a promotion to a governed claim. User observations/statements are `communication_only`; work/reference evidence is `untrusted_evidence_only`. Any declared inference is communication-only and cannot enter work/task or reference/task packets. No acceptance, global credibility/competence score, instruction authority or diagnosis is created.

Declared `sensitive_health` hypotheses/observations/preferences are **withheld from all model-facing lanes and direct reads**. Only an explicit user-lane health statement with `explicit_statement` basis is deliverable in user/communication intent, labeled self-report rather than medical verification. This is a metadata rule, not detection of ADHD, mental illness or sensitive prose. No phrase/regex diagnostic classifier exists here.

## Index, serialization and compatibility

The existing properties table stores validated fields; there is no database per type or physical folder migration. Schema version 8 invalidates earlier parser/admission policy projections, including v6/v7 records whose malformed or recognized-but-unconsumed declarations were previously admitted as legacy. A v5/v6/v7 index is not read-compatible. Explicit sync migrates the disposable index, invalidates cached admissions and reparses documents; canonical sources are unchanged. A malformed v6/v7 source that fails reparsing leaves the projection stale/unhealthy, not a healthy cached legacy disclosure. The version bump is necessary even when the source bytes have not changed.

One SQL policy is used by lexical retrieval, supplemental current-state retrieval, section/document resolution, outline and related-document eligibility. Native tools use current-projection/root-identity guards and the same per-call intent. Optional fields do not enlarge the project grant.

Measured packing still counts the **complete success JSON string** using the configured local named tokenizer, including type/basis/restriction metadata and JSON escaping. Metadata is never dropped to fit. A low budget can return an empty evidence packet; omission is not deletion. `elm_read` keeps its existing separate 12000-character expansion limit and is not advertised as context-budget capped. No full-model-context or billing claim follows from these counts.

Untyped documents remain **legacy-unclassified**, not retroactively typed work facts. Their default retrieval/packet and expansion bytes are preserved where promised and checked against the frozen origin on synthetic untyped fixtures. The default work intent intentionally retains those legacy sources, which can contain personal/mixed/hostile prose. Absence of type metadata is not a privacy guarantee. Typed user/reference sources are newly excluded from the default work surface by design.

`elm_note` and separately opted-in capture/episode tools are unchanged closed contracts; they do not accept these new declaration fields or automatically extract/promote typed user memory. Typed ingestion/correction is an explicit operator source edit plus sync. The slice enables no background recall, capture, model request or automatic canonical mutation. Historical explicit `legacy-background` configuration remains separate and defaults to work/task; it is not enabled by this candidate.

## Acceptance and limits

`tests/test_typed_memory.py` contains behavioral engine/provider regressions. `tests/test_typed_header_quarantine.py` adds reserved-header recognition, literal-body compatibility and a modeled v6 projection migration regression. `tests/test_typed_declaration_consumption.py` adds a 24-subcase delimiter/order/line-ending matrix and a separate modeled v7 projection regression; these are two unittest methods, not 24 independent benchmark examples. Separate external repair evidence upgrades an actual frozen-v6-created store/binding through stock native context/read dispatch; the modeled unit fixture is not substituted for that check. `tests/native_typed_memory.py` launches four fresh stock MemoryManager consumer processes (initial, corrected, stale reclassification, synced reclassification) using `tests/typed_native_cases.py`. The stock host remains pinned at the repository runner's exact commit. Both local vocabularies are exercised at 200/700/1200-token caps, with full raw success strings, recounts and hashes retained outside source.

Read-only SQLite WAL connections may create empty derived `-wal`/`-shm` sidecars. The fixture primes that ordinary reader state after operator sync, then compares every root/index/sidecar byte before and after each consumer. This does not claim that SQLite reads never create transient derived files. Canonical Markdown no-mutation, installed-source no-mutation, frozen-origin verification and host tracked-clean checks are separate evidence. Live canonical memory is never accessed by this slice.

Human-supplied fixture classifications do not establish model inference quality, user benefit, benchmark superiority, authentication or clinical validity. Cross-project personal identity, lane composition, automatic classification, automatic correction of derived interpretations and a native typed-authoring tool remain unsupported. Owner acceptance and live activation are separate future decisions.
