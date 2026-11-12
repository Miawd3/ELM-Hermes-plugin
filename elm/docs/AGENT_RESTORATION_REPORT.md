> Historical integration narrative, retained for provenance. Partial patch references and publication status below are superseded by the complete [integration/host.patch](../../integration/host.patch), [current installation guide](CANDIDATE_INSTALL.md) and [release status](../../RELEASE_STATUS.md). Do not apply any partial patches separately.

> Historical first checkpoint. See PROVIDER_ENVELOPE_UPDATE.md for the subsequent parser repairs and fresh tests. Live dispatch remains gated.

# Organizer restoration patch: qualified local workflow, live gate retained

## Delivered
- Explicit full-payload send consent UI, including sensitive-data disclosure, exact recipient, unknown provider charges and absent enforced monetary cap.
- Backend requires `accept_unknown_cost: true` in addition to one-use exact payload confirmation. Enrollment/preferences never authorize egress.
- Controller consumes preview before send, prevents double-click/stale-owner execution, and fences uncertain failures. Results remain separately reviewed pending proposals.
- Candidate direct HTTPS connection resolves once, rejects every nonpublic DNS result, connects to one numeric address, verifies original TLS hostname, and has no proxy, redirect or fallback retry. It is NOT enabled by default.
- Production `_TRANSPORT_FACTORY` remains None. This is an intentional safety gate, not a claim that the requested autonomous agent is complete.

## Verified locally
- 29 backend/transport/verified-local-TLS tests passed (20 existing warnings).
- 169 UI controller/security/registration tests passed.
- Four compatibility-blocker reproduction tests passed: current parser rejects logprobs:null, token-details usage, service_tier and model alias/snapshot differences.
- Independent reviewer confirmed parser incompatibility is a live-enablement blocker. No external provider, paid model call, real credential or native desktop screenshot used.

## Why production stays gated
The existing strict completion parser rejects common optional provider metadata and exact alias/snapshot differences. A valid charged response could be discarded. Do not enable the candidate simply by assigning its transport factory or by exposing an environment switch. Provider request parameters and response envelope profiles need explicit qualification first. Pricing is unknown; socket timeout is not an absolute DNS/header deadline. No enforced monetary cap exists.

## Exact remaining steps
1. Choose supported provider/model profiles from official docs; normalize only permitted bounded metadata while retaining duplicate-field rejection, nonfinite rejection, refusal/tool-call handling, response-size caps and identity checks. Add realistic fixture contracts, including alias policy and compatible output-token parameter names.
2. Decide and enforce an actual spending rule or maintain clear per-request unknown-cost consent. Never auto-run with existing preferences.
3. Qualify the new public TLS adapter in the native packaged host (including durable DB configuration), then run an explicitly authorized capped live request. Current loopback evidence is not that qualification.
4. Enable live dispatch only after review; remove unavailable-only wording consistently in job/status/credential panels.
5. Model-assisted search remains unimplemented. It needs a bounded read-only query-plan contract, scoped native search, result/source validation and separate model/recipient controls. Do not describe organizer execution as search-agent restoration.
6. Automatic background organizing is not added. This patch processes explicitly selected 1–4 private sources with one-shot consent.

## Integration
Patch is against r38 (r39 reportedly changes only native skill-detail UI). `restoration.patch` changes plugin desktop/plugin.js, elm_plugin/curation_jobs.py, host hermes_cli/plugin_organizer.py. Add candidate host plugin_public_https.py separately. Tests are additive/updated in the delivery archive. Rebuild manifests and host identity/hash qualification after integration; do not copy the plugin-source git metadata or reuse old test claims. No public push performed.
