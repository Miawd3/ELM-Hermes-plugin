> ARCHIVAL ONLY. This document describes an earlier, inactive implementation. Do not use its installation, provider, tool or permission claims for the r21 candidate. Relative links may refer to its original location.

> Catalog preparation note: this separate export removes all plugin-code update controls and sanitizes qualification paths. Historical qualification below applies to the base snapshot. See ../PUBLIC_EXPORT_NOTES.md and the root QUALIFICATION.json for current checks and unresolved gates.

# Current capability matrix

This file supersedes older additive milestone notes. All optional layers are disabled unless the profile explicitly enables them. One profile is bound to one root/project. Source-derived text is untrusted; exact offsets do not establish truth or authenticated attribution.

| Layer | Durable? | Canonical mutation? | Main limit |
|---|---|---|---|
| Canonical `elm_context` / `elm_read` | Existing source/index | No content mutation; read coordination locks | Lexical source retrieval, explicit tools by default |
| Typed logical user/work/reference documents | Existing source properties/index | Operator edits + explicit sync only | Closed declared kind/basis/sensitivity; same root/project; not identity auth or semantic DLP |
| Canonical background recall | In-memory cache only | None | Disabled by default; optional legacy mode has host authority conflict |
| Explicit `elm_note` propose | Governance + receipt | Pending proposal if mode permits | No acceptance |
| Explicit `elm_note` remember | Governance + receipt | Leased unverified agent-curated note if autonomous | No ratified truth, bounded quota/lease |
| Episode capture | Profile SQLite | None | Opt-in; bounded, scrubbed visible pairs; incomplete DLP |
| Marker proposals | Profile SQLite, then optional governance | Pending proposal in allowed mode | Narrow exact grammar; no natural-language learning |
| Episode search/read | Existing captured evidence | None | Separate opt-in; current paired evidence only |
| `BatchExtraction` | No | None | Process-local exact-span validation, restart loses batch IDs |
| `DurableCandidateInbox` | Yes | None | Bounded quarantine, never accepts/submits by itself |
| `OperatorReviewBridge` | Yes | Pending proposal after explicit interpretation and confirmation | No semantic verification, no acceptance/canonical correction |
| Submission reconciliation | Local outcome update | No proposal/claim mutation | Exact positive payload proof only; absent is still uncertain |
| Local forgetting/revocation | Tombstones persist | No canonical deletion | Logical local scrubbing, not complete erasure |

## Not implemented or demonstrated

Typed-field declaration/admission is implemented; automatic semantic classification, cross-project personal identity, lane composition and automatic derived-note correction are not. See [typed-memory scope and health/legacy limits](docs/TYPED_MEMORY.md).

General semantic extraction from ordinary conversation; automatic web/document download and source-version import; cross-profile personal/project/skill namespaces; semantic contradiction resolution; authenticated speaker identity; human ratification UI; complete uncertain-outcome recovery; complete deletion; indefinite unattended storage lifecycle; real-model tool-choice/answer-quality evaluation; competitive benchmark superiority; tokenizer-accurate total workflow billing; broad production or performance certification.

HTTP/MCP transport is not a required dependency for this native Hermes plugin. The bundled engine includes historical transport source, but this release does not start an MCP server or expose a network service. Adding another host transport would need its own authentication and data contract.

## Measured context delivery

New setup defaults to explicit named-tokenizer measurement with local hash-verified vocabulary and optional pinned tiktoken. The full successful context JSON is capped. Other memory surfaces retain their own existing limits. Historic bindings remain visibly legacy-estimate until re-adopted; no silent tokenizer fallback. Measured background additionally needs a verified host budget receipt, absent from stock initialization. See [scope and migration](docs/MEASURED_TOKEN_BUDGET.md).
