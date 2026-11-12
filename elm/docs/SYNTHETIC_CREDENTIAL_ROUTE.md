# r19: dedicated credential-route and response-contract qualification

## Production remains unavailable

This milestone qualifies a dedicated recipient-bound credential interface using **synthetic values and a local loopback server only**. No real credential is read, copied, stored, sent or selected; no external or paid model call is made. Public curation status and dispatch remain unavailable. The UI gains no live-send or credential-entry capability. The internal factory is not an authorization API or a sandbox against malicious Python.

Existing PluginLlm/auxiliary routing still uses dynamic provider/task configuration, credential pools and fallback behavior, rather than a reviewed immutable recipient/credential contract. This code never consults those pools, ambient main-provider keys or environment key/proxy settings. A real host-owned secret-storage implementation and explicit user configuration/authorization remain missing.

## Dedicated synthetic slot

`hermes_cli.plugin_llm_credentials._SyntheticCredentialResolver` is private qualification infrastructure. `install(slot_id, owner, endpoint, model, secret)` accepts a trusted native owner snapshot, an exact loopback HTTP `/v1/chat/completions` destination, a model and a visibly synthetic ASCII value beginning `synthetic-`. There are at most 16 slots. Installation cannot overwrite a slot. `rotate` increments the version; `revoke` increments it and removes its active secret. A new route preparation is required after version changes. Prefix checking is a fixture constraint, not detection of all real secrets; callers must supply synthetic data only.

The route binds the complete native owner snapshot (therefore profile, principal, canonical chat and current authority state), endpoint, model, slot ID, version and active state. Its public metadata contains slot/version and a route hash over **non-secret route metadata**, never the credential or a hash of the credential. Prepared canonical request bytes still contain the model; the durable attempt binding includes recipient metadata, body digest, owner and source/policy fingerprint. Secrets are not in previews, dataclass representations, jobs, body hashes, ledger rows or ordinary error messages.

`_CredentialLoopbackTransport` retains a reference to the private resolver, not a copied secret in a prepared request. It checks the exact route and native owner before any socket connection and again after connecting, immediately before constructing Authorization headers. Only then is `Bearer <synthetic value>` passed to the exact loopback request. A version change, revoked slot, different owner/model or destination refuses. Redirects are never followed, so credentials are not forwarded. There is no environment proxy, fallback, automatic retry or production HTTPS credential implementation.

As with r17, authorization is a final-admission snapshot. Rotation after the final check cannot retract headers already admitted or sent. Resolver/service locks are not an atomic transaction with network I/O. A route change can leave a durable attempted job/ledger entry even when no HTTP request body was sent; no automatic retry is permitted. Socket/header/DNS deadline qualifications from r17 still apply. This local qualification does not prove real TLS/secret-store integration or remote billing outcomes.

Default object representations redact synthetic values. No guarantee is made against arbitrary trusted Python introspection of the resolver's private storage, process dumps, an authorized receiving server, or caller-added logging. The adapter itself does not log credentials, headers or response bodies.

## Actual response envelope

The credential-qualified ELM workflow parses an OpenAI-compatible Chat Completions envelope before the existing source-bound proposal validator:

- UTF-8 JSON response at most 8,192 bytes, with duplicate keys and nonfinite constants rejected.
- Required id, object `chat.completion`, exact reviewed model and exactly one choice, index integer zero.
- Finish reason must be `stop`; truncation/length, tool calls, multiple choices and refusal are rejected.
- Message role must be assistant, content a nonempty string, no unsupported fields; optional refusal must be null.
- Optional created timestamp, system fingerprint and usage are strictly typed/bounded. If present, usage totals must sum correctly and reported output tokens cannot exceed 512. These reported numbers are not trusted price enforcement.
- Model aliases that return a different actual model identifier are unsupported; no silent normalization or fallback occurs.

The assistant content then undergoes r15/r18's strict exact-source quote/hash/codepoint-span, sensitivity and provenance validation. Invalid raw responses are not persisted or logged; only validated proposals enter the private job manifest. Response-model equality does not authenticate the remote model or prove semantic truth. Model-generated labels remain unverified, source roles remain distinct, and each proposal still requires explicit acceptance into a pending record followed by separate record approval.

## ELM qualification path

`curation_jobs._credential_qualification_workflow(resolver, slot_id, ledger)` is internal only and must be created in an authenticated native context. It uses the real source snapshots, native fences, r17 durable attempt ledger and r18 job/result lifecycle. Its explicit `prepare` model must match the slot. The full preview shows exact recipient metadata and canonical body before one-use confirmed execution. No credentials appear there. Source withdrawal and stale route versions refuse; lost/uncertain outcomes require job/ledger inspection, never blind resend.

The older r18 uncredentialed private loopback fixture still accepts raw candidate JSON for backward test coverage; it is not a public or production path. The new credential-qualified workflow requires the envelope above. Durable job get now includes strictly validated secret-free recipient metadata, model and payload SHA-256 for destination review. It excludes raw owner identity, owner digest, attempt/token ID and credentials. Recipient fields are limited to the qualified loopback provider/endpoint, no-redirect/retry/fallback/proxy flags, and optional synthetic slot/version/non-secret route hash. Public APIs remain only local preview plus authenticated durable job list/get/individual acceptance; there is no fake-output import or live dispatcher.

## Remaining blockers

Production needs an actual host-owned encrypted/approved credential store with durable slot/version identity, exact HTTPS recipient binding and user-selected settings, qualified TLS/network/deadline behavior, explicit monetary authorization, durable job recovery policy and provider-specific response compatibility. None is inferred from successful synthetic local tests. No production route is configured or enabled by this milestone.
