# Model-role routing: production boundary audit (r32)

Historical audit: r33 adds dedicated host-owned enrollment software. It does not add a production credential resolver/dispatch binding. The enrollment requirement below is now partially implemented; other execution, pricing and compatibility gates remain unmet. See the r33 checkpoint design/NATIVE_MODEL_CREDENTIAL_ENROLLMENT.md.

## Outcome

Search and organizer selections remain **declared preferences, not operational routes**. No production send is enabled. This checkpoint does not restore model-assisted search or automatic organization. It does not read credentials, probe endpoints, call providers, or install a synthetic test adapter as a production route.

## Source findings

- `agent/vault_store.py`: the encrypted local vault is for browser `login`, `payment`, and `address` items. `normalize_origin` deliberately reduces a URL to an origin; `resolve_secret` is a browser-secret operation. The vault does not supply an API-key enrollment grant bound to the native principal, exact model API path, role, and credential revision. Browser passwords must not be repurposed as model credentials.
- Native credential source/pool/lifecycle code manages named provider credentials and rotation/refresh. A provider identifier or a resolved secret does not prove authorization to send that credential to a caller-selected endpoint. Existing profile isolation is not an exact per-principal recipient grant.
- `agent/plugin_llm.py` uses the host auxiliary route. `agent/auxiliary_client.py::_ladder_provider_fallback` and its retry policy make provider/model overrides insufficient to promise a single pinned destination and one attempt.
- `hermes_cli/plugin_llm_pinned.py::production_contract` refuses production dispatch. Its offline factory is a private qualification seam, not a public permission.
- `hermes_cli/plugin_llm_transport.py::HttpsTransport` supplies direct TLS-validated, no-redirect/no-fallback HTTP transport but no authentication. Its durable attempt ledger prevents replay for accepted attempted jobs; it does not enroll a recipient-bound credential or supply a complete user-facing send workflow. The existing timeout is not a guaranteed absolute deadline across DNS/TLS/header processing.
- `hermes_cli/plugin_llm_credentials.py` explicitly restricts its credential resolver and authenticated transport to synthetic loopback qualification. Its strict Chat Completions response parser is useful, but is not evidence of production credentials or a configured provider.
- ELM curation has local payload preview and durable result-review/individual pending-record acceptance. Public production execution remains unavailable. Search additionally lacks a qualified model-assisted search result contract; the current approved-record recall is deterministic, not semantic model search.

Only repository source was inspected. No actual vault, environment key, password-manager item, provider account, or credential pool was opened or resolved for this audit.

## Smallest missing production implementation

A future implementation needs a dedicated **host-owned model-route credential enrollment**, separate from browser autofill and ambient main-model credentials. Enrollment must explicitly bind authenticated profile/principal, purpose/role, exact HTTPS origin and API path, model, opaque slot, and monotonic credential/route version. A local secret-entry UI or CLI must not expose the value to model tools, previews, logs, manifests, or attempt journals. Reuse of any existing key requires a specific explicit grant, not inferred permission from its presence.

Then connect that real enrollment to an authenticated one-shot preparation/execution workflow:

1. Resolve selected authorized data and immutable exact outbound bytes; show recipient/model, complete payload, sensitivity, bounds, pricing uncertainty and possible costs. Saving a preference is not this consent.
2. Pin owner, data/source state, role preference revision, route and credential versions. No automatic fallback, redirect, retry, provider substitution, or credential refresh that silently changes the approved route.
3. Consume confirmed consent and durably claim the attempt before I/O; revalidate authority and versions immediately before secret use. Preserve uncertainty across restart; never resend an uncertain attempt automatically.
4. Send through a qualified authenticated HTTPS adapter with explicit response and timeout limits. A maximum output-token count is not a monetary spending guarantee. If a total-price ceiling cannot be enforced, do not claim one.
5. Parse untrusted output under a role-specific contract. Organizer proposals must retain exact authorized source binding and sensitivity, remain pending, and require separate human review. Search must not widen record access or silently disclose whole sources.
6. Reconcile result publication and lost replies; a committed result can exist even if final delivery failed. Revocation stops subsequent admitted work, not already-dispatched bytes or provider-side retention.

Synthetic tests can validate state transitions and secret non-disclosure with fake values. They cannot establish a real enrollment UX, real provider pricing, successful live TLS/authentication, endpoint trust, or production readiness. Those missing seams must not be replaced by an availability flag or another generic fake dispatcher.
