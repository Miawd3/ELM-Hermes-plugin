# Model-assisted curation: disabled foundation (r15)

**Real model dispatch is unavailable.** This checkpoint provides authenticated,
read-only local inspection of a bounded candidate request and a pure proposal
validator tested with fixtures. It does not implement paid/model calls, routed
jobs, external-processing consent, proposal persistence or automatic approval.
It does not pretend a fake provider completed work. Existing manual exact-excerpt
review remains available independently.

## Why the existing host facade is not used

`agent/plugin_llm.py::PluginLlm.complete` trust-gates provider/model/profile hints
but delegates invocation to `agent.auxiliary_client.call_llm`. That router can
resolve endpoints/credentials at call time, retry and move through fallback
providers, including paid routes. Provider/model overrides are not a pin to an
exact recipient. Effective attribution is returned after invocation; the facade
has no immutable prepared destination/request handle with enforceable no-fallback,
no-retry and endpoint constraints.

The scoped plugin therefore never constructs/invokes `ctx.llm` for this feature,
changes provider selection, probes a route or bypasses the existing router with
its own client. A broad router/credential rewrite was deliberately not attempted.
No host flag claims a pinned-egress capability exists.

Fresh r15 scoped registration also stops registering the old
`elm-workspace-pending-draft` legacy command. Its source file remains inactive for
reference, not as an authorization or model fallback. This is a candidate entrypoint
change, not an instruction to deactivate unrelated plugins or alter a live global
runtime. Existing legacy data is not read, adopted or migrated.

## Authenticated local preview

- `private.curation.status {}` reports `dispatch_supported:false`,
  `external_egress_enabled:false`, `reason:"host_route_not_pinnable"`, an unresolved
  `destination` whose provider/model/endpoint are null, limits and a cost/privacy
  notice. Capability is not inferred from whether credentials happen to exist.
- `private.curation.preview {source_ids:[...]}` selects one to four distinct,
  active snapshots owned by the authenticated current private chat. It reads under
  the native ownership fence and store snapshot; it accepts no caller root,
  profile, principal, arbitrary path or project scope. Foreign and missing source
  lookups are indistinguishable. Withdrawn sources are refused.
- The response contains the full `egress_payload` candidate (fixed instruction
  message, selected source-data message, temperature 0 and a proposed 512-output-token
  cap), `payload_sha256`, `utf8_bytes`, source summaries, unresolved destination,
  `payload_kind:"local_candidate_not_dispatchable"` and `consent_granted:false`.
  The instruction and every included source field/text are visible. Native captured
  roles remain distinct from manually declared author/reference labels.
- `private.curation.dispatch {payload_sha256,confirm}` always refuses with
  `curation_dispatch_unavailable`, even for an exact fresh hash and `confirm:true`.
  A caller cannot authorize transmission to an unidentified recipient by setting
  that boolean. No job, consent token or fake success is created.

The preview is local inspection of a candidate message payload, **not** an exact
final provider wire request, a recipient authorization, price quote or durable
permission to send later. There is no send/execute UI action. Source changes or
withdrawal require a new local preview; an older displayed payload cannot become
a dispatch grant because dispatch remains unavailable. Previously returned local
preview text cannot be retracted from the viewer's memory or copies.

## Bounds and hash representation

Selected source text totals at most 16,384 UTF-8 bytes. The entire serialized
candidate payload is capped at 32,768 bytes; metadata, prompts and JSON escaping
count. Nothing is silently truncated. The hash covers UTF-8 bytes of:

`json.dumps(payload, ensure_ascii=True, separators=(',', ':'), sort_keys=True, allow_nan=False)`

This is a deterministic local serialization, not a promise that a future transport
would transmit those same HTTP bytes. Source snapshots include content revision,
state revision, captured digest, sensitivity and role provenance. Sensitive text
can be explicitly selected for local preview, but is visibly marked and **never
sent**. Local capture consent and automatic recall opt-in do not grant external
model-processing consent.

A future real call could incur input/output charges and routing/retry costs.
This checkpoint supplies no resolved provider, endpoint, price or dollar cap and
makes no claim that a nominal token cap proves a monetary limit.

## Pure proposal validator, not a public job API

`validate_model_proposals(raw, selected_sources)` is an internal pure function for
offline fixtures and a future verified caller. Its trusted selected sources must
come from a fresh authorized snapshot, never from the model output. It writes
nothing and makes no permission or freshness decision by itself. There is no
public arbitrary-output import, fake-result submission, job-apply or approval RPC.

The strict output envelope is one to four `candidates`, each containing exactly
`source_id`, `sha256`, `quote`, `start`, `end`, and `title`. Duplicate JSON keys,
extra authority/sensitivity/state fields, duplicate candidates, unknown sources,
withdrawn sources, wrong hashes and invented quotations are refused. Offsets are
strict integers in Unicode codepoints, inclusive start/exclusive end; booleans,
UTF-16 guesses and normalized/paraphrased mismatches are not accepted.

Validated fixture candidates contain the exact quoted text, source-bound reserved
citation, `state:"pending"`, reference domain/kind, source-document basis, inherited
sensitivity and native source-origin metadata. A model-suggested title remains an
unverified label. Assistant-source text is never transformed into an authenticated
user fact. Neither exact quotation nor a matching hash verifies truth or author
identity. Existing source-metadata/record-size limits also apply. A separate human
review and approval would still be necessary; this checkpoint does not persist
these validator results.

## Required future pinned-egress contract (design only)

Before a real model-assisted workflow can be enabled, the host must support a
verifiable immutable route/request capability covering:

1. Exact receiving endpoint/provider/model and relevant auth scope, without
   exposing credentials. The actual adapter/redirect behavior must respect it.
2. Exact disclosed message payload/hash and bounded output, timeout and call count;
   no undisclosed fallback or automatic physical retry. Any permitted retry or
   changed destination needs its own specified authorization semantics.
3. Explicit per-batch external processing approval, including selected sensitive
   sources, cost uncertainty and logging/provider-retention disclosures.
4. Fresh native ownership, source versions/digests, consent revision and cancellation
   checks at dispatch admission; no cached/background authority. Already dispatched
   requests cannot be recalled by revoking later consent.
5. Strict response validation, untrusted per-proposal human review, source/sensitivity
   binding, pending-only publication and final native/store freshness checks. No
   response can select scopes, authorize sharing or approve itself.
6. Durable job reconciliation for uncertain sends/commits, so a lost reply does not
   cause automatic paid re-execution. Middleware, telemetry, SDK and provider copies
   must be covered by the disclosure, not hidden behind a no-logging claim.

These are requirements, not implemented capabilities. Tests use synthetic model
output and forbidden-call spies only; no paid or live model request is necessary.
