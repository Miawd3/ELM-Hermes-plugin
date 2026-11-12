> Current release boundary: [rc40 status](../RELEASE_STATUS.md) and [test report](../TEST_REPORT.md). Milestone details below describe individual contracts; they are not claims of a live organizer/search agent or stock-host support.

# Current candidate capabilities and gaps (r35)

This file describes the active scoped entrypoint, not the retained legacy engine/provider. Exact evidence is in the enclosing checkpoint. “Implemented” does not imply production certification or live activation.

| Area | Implemented candidate boundary | Still missing / not claimed |
|---|---|---|
| Host identity | Native actor/profile/canonical receipt and lineage checks; epoch-fenced read/publication; no caller path/sidebar identity inference | Drop-in stock-host support; malicious same-process plugin sandbox |
| Private records | Explicit fresh store, pending/approval, current-chat human inspection, tracked corrections, recoverable trash/restore | Purge/full erasure; unlimited retention; automatic graph repair after revision changes |
| Project memory | Exact binding and per-chat versioned consent; same-principal project-generation records and review lifecycle | Cross-principal sharing/ACL; rename continuity; historical archive/restore revocation guarantee |
| Sources | Immutable API-received text hash, exact excerpt spans, sensitivity inheritance, tracked withdrawal | Authorship/semantic truth; arbitrary file/URL ingestion; automatic unlinked-copy withdrawal |
| Local capture | Separate opt-in, native finalizer-visible redacted text, role-separated sensitive sources, stop-new caps | Full transcript/delivery proof; guaranteed secret detection; rolling eviction; source purge |
| Default request recall | Opt-in newest eligible private records, request-only bytes, fresh native attempt admission | Semantic ranking; project automatic recall; all provider modes; exact token/currency billing |
| Curation | Strict exact-source proposal validation, durable job review, per-proposal acceptance into pending records | Configured production extraction; real credentials/provider routing; monetary authorization |
| Transport qualification | Durable attempt ledger, direct transport and synthetic recipient-bound slot tests against local fixtures | Live provider/TLS/secret-store qualification; hard total deadline; exactly-once remote billing |
| Legacy data | Full-preview user-supplied selected-export copy, pending+sensitive, atomic receipt/idempotence | Automatic discovery/adoption; verified historical ownership; dependency graph migration/general dedup |
| Desktop | Explicit private/project review pages and capability/snapshot guards | General restoration of unrelated chat/sidebar UI; fresh browser/native clickthrough certification unless separately reported |
| Deployment | Source inventories and pinned-base host patch; clean loader tests where documented | Public release/catalog approval, broad OS/runtime compatibility, production rollout |

Defaults: no model tools, no legacy prefetch or draft command, no automatic private recall, no local capture, no project read consent and no live curation dispatch. Installing or selecting the provider does not grant these permissions.

Read [install/recovery](docs/CANDIDATE_INSTALL.md) and [API contracts](API.md). Legacy six-tool/root-project behavior is not the active provider contract.

## r27 native starter skills

Six original Apache-2.0 static procedures register as elm-qualified native skills. Native discovery/selected read, disabling and unload are reused. This is not a memory-derived skill generator, automatic stuck detector, model-ranking database or a guarantee of instruction compliance. No wiki provider or additional private-data access is enabled.

## r30 memory-derived reference drafts

Explicit authorized approved-memory selection can produce a deterministic inert reference preview and separately confirmed saved recipe. Recipes are creator-chat scoped, retain sensitivity/provenance pins and regenerate only while exact sources remain eligible. UI currently selects one record; backend supports one to four. No model synthesis, automatic installation, model injection, export, permanent recipe purge or skill-quality benchmark claim. No generated body is duplicated in saved recipes; titles/IDs and related metadata remain retained.

## r31 separate model-role intent

Current-chat search and organizer preferences can be independently reviewed, saved and cleared. Both are unset by default. These declarations never activate provider routing, model agents, fallback, data egress or main-chat model changes. Only bounded provider/model identifiers and four HTTPS Chat-Completions-shaped endpoint paths are accepted as unverified intent. Responses/Messages endpoints, HTTP local models, reasoning effort and profile-wide defaults are not supported in these settings yet. Actual model-backed search/organization remains unavailable; production extraction is still disabled.

## r32 explicit production-readiness diagnostics

Role-specific settings now distinguish a saved selection from executable routing and display concrete unavailable components. This adds no model-backed search/organization and enables no external request. Dedicated credential enrollment, pinned production transport, explicit public egress flow, provider response compatibility and an enforceable cost boundary remain blockers; search additionally needs its scoped result contract. The browser vault and rotating provider pools are not reused as recipient-bound model credential grants.

## r33 dedicated host enrollment gate

The patched host now implements authenticated native credential status/set/revoke, separate encrypted search/organizer slots, exact recipient/model metadata and durable revision checks, with actual native settings UI. This software was tested using synthetic values only. Principal/profile-wide slots are distinct from current-chat model preferences and are not automatically connected. There is no secret getter, credential resolver for production transport, provider connection test or dispatch activation. Local installed code/plugins must be trusted; shared renderer/process authority is not isolated. No live credentials were enrolled.

## r34 public organizer preparation and synthetic execution qualification

Selected current-chat sources, exact organizer preference and native enrolled slot/version can now produce an actual route-bound full-payload preview and cancellation. Production execute remains disabled before job/attempt writes; no live UI send action is offered. Same-handler synthetic local tests exercise native credential consumption and bounded nonreplaying attempts, with exact/JSON-escaped credential echo rejection before proposal storage. This does not prevent arbitrary covert encoding by a malicious recipient, qualify live TLS/provider responses or establish a monetary spending cap. Search execution remains unimplemented.

## r35 request caps and local TLS qualification

Requested max output tokens1–512 are bounded at admission and pinned to canonical payload/hash. Local source/request/response byte limits are enforceable; provider token generation and charges are not. Real certificate and hostname validation is covered by synthetic local HTTPS tests, with invalid certificates and adverse responses refused. Production dispatch remains disabled. Socket timeout is not an absolute deadline; accepted provider usage is untrusted reporting, not billing proof. Historical jobs retain payload hash, not a reconstructable full request or chosen token cap.
