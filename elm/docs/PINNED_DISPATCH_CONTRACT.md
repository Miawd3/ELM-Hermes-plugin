# Experimental pinned-dispatch contract (r16)

## Production remains disabled

This milestone adds a host-side **offline contract/state-machine test seam**, not a production model transport. ELM retains r15's authenticated local curation preview and always-refusing dispatch. There is no new public fake-output import, execution token, egress consent, job, provider selection or credential handling. No model/network request is made by this module. Existing provider routing is not bypassed or qualified.

`hermes_cli.plugin_llm_pinned.production_contract()` always raises `pinned_production_transport_unavailable`. The private `_offline_contract` factory is only for trusted local recording tests. It is not a sandbox against malicious Python, nor proof of an HTTP adapter's safety. Its sole synthetic recipient is `https://offline.invalid/v1/chat/completions`, provider `offline-test`, credential mode `none`.

## Contract tested locally

Preparation accepts only messages (system/user string content), integer temperature zero, output-token limit 1–512 and a model name. Endpoint, keys, headers, proxies, redirects and fallback cannot be supplied through this API. The canonical UTF-8 JSON body includes the model, uses sorted keys, compact separators, ASCII escaping and finite JSON values. The frozen wire envelope contains those exact immutable bytes and their SHA-256. Mutating the original input after preparation cannot change the body.

The host resolves current authenticated memory ownership itself by default. A trusted integration supplies a zero-argument freshness callback, recomputed under native `read_memory` admission. That callback must fingerprint the actual selected source states, hashes, revisions, sensitivity and any relevant consent/policy, not return an untrusted caller's asserted fingerprint. Preparation compares the expected digest to this recomputation and saves the native owner snapshot. Execution rechecks the exact owner and recomputes freshness under the native fence. The offline test may substitute these seams only to exercise isolated state transitions.

Prepared entries are bounded to 16, expire after 300 monotonic seconds, and each body is at most 32,768 bytes. Timeout metadata is 1–30 seconds, response bytes 1–8,192, and output tokens 1–512. These are not a currency spending limit or an exact input-token measurement. No price is known. The synthetic fake has no payable provider; production cost authorization is not implemented.

Execution requires the stored opaque token, literal confirmation `True`, and exact body digest. A foreign owner cannot consume the rightful owner's preview. Once the owner matches, the token is consumed before expiry/digest/freshness validation and before transport. Cancellation removes an owned pending token; closing clears all entries. Confirmation is an API protocol, not cryptographic proof of a human click.

The transport receives one frozen wire request, once. There is no retry or fallback loop. Non-byte, oversized or awaitable responses and transport exceptions produce a fixed outcome-uncertain error without exception/credential details; cancellation-style `BaseException` is re-raised with an uncertainty note. A consumed token cannot be replayed, including after failure. Response bytes remain untrusted and confer no record approval.

## Deliberate limits

Native read locks are released before transport. Freshness is checked at admission, not held constant across dispatch; subsequent revoke/withdraw cannot retract already-admitted bytes. The service lock serializes cancellation/close with execution: cancellation before admission stops it, while close after invocation waits rather than interrupting the callback. Fake callbacks must be short and synchronous. Timeout/redirect/proxy/retry properties are envelope requirements, **not enforcement against an arbitrary injected Python callback**.

One-use state is in memory only. This is not durable exactly-once execution across process restart, nor proof of remote receipt or billing. Tokens disappear on restart; no recovered job is automatically sent. A future production adapter needs a durable attempt journal before sending, explicit uncertain-outcome reconciliation, pinned authenticated recipient/credential scope, redirect/proxy/retry enforcement, bounded response streaming and actual timeout enforcement. SDK/environment routing and credential discovery must not silently alter the confirmed recipient.

The fixed synthetic route tests no real credential binding, endpoint authenticity, TLS behavior, price enforcement or network outcome. Production remains unavailable until those separate guarantees and an explicit egress review/consent flow are implemented and qualified. Existing local source previews and pure source-bound proposal validation remain useful without granting any external transmission permission.

Ordinary owner/freshness/admission callback failures are normalized to a fixed diagnostic before dispatch. Lifecycle state is rechecked after callbacks, including reentrant close. Interrupt-style `BaseException` is deliberately propagated, so its arbitrary original text is not promised sanitized; transport-consumed interrupts carry a fixed uncertainty note. Output-limit metadata is derived from the same immutable serialized body, not subsequently mutable caller input.
