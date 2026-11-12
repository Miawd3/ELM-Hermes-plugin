# r35 organizer budgets and local TLS qualification

## Public request budget

`private.curation.organizer.preview` accepts `max_output_tokens`, an optional strict integer from1 to512 (default512). Booleans, floats, strings and values outside that range are refused before a receipt is created. The selected value appears in the exact canonical outbound JSON `max_tokens`, its SHA256, the immutable host wire request and the preview. Changing it requires a new preview. Execute has no override field.

The additional `budget` object reports:

| Field | Meaning |
| --- | --- |
| `outbound_body_bytes` | Exact UTF-8 byte length of canonical serialized outbound JSON, including model/instructions/selected source metadata and JSON escaping. |
| `outbound_body_bytes_limit:32768` | Locally enforced complete-body limit. Selected source text separately remains bounded at16384 UTF-8 bytes. |
| `response_body_bytes_limit:8192` | Locally enforced received HTTP body bound, including the response envelope. Not a remote generation or billing bound. |
| `requested_max_output_tokens` | Selected1..512 value requested from the provider. No exact generated-token measurement or billing compliance is established. |
| `input_token_count:null` | No tokenizer-specific input count is asserted. Bytes are not presented as equivalent tokens. |
| `monetary_limit:null` | No currency spending cap or price estimate is enforced. |
| `pricing_verified:false` | Provider pricing, account charges and quota enforcement have not been qualified. |
| `timeout_seconds:10` | Socket operation/inactivity timeouts and monotonic checks between stages/body reads. |
| `absolute_deadline:false` | Not a guaranteed whole-request wall-clock bound, especially inside DNS/TLS/header processing. |

If the provider includes a usage object, the strict parser refuses a reported completion count above the selected request cap. A report below the cap or an absent report does not prove the actual generation or charge. Exact byte limits cannot imply financial limits, and stopping local reads cannot retract a request or stop remote billing.

## Transport and credential constraints

The existing host transport makes one invocation, follows no redirects, uses no SDK retry/fallback/environment proxy, validates exact canonical bytes, and reads only the bound enrolled organizer slot internally. Native source/owner/preference/credential revisions and durable SQLite attempt requirements remain those in `PUBLIC_ORGANIZER_PREPARATION.md`. An uncertain attempt is never automatically replayed. Exact sent-credential echoes are withheld before proposal publication; arbitrary transformed covert channels are not claimed prevented.

Production `_TRANSPORT_FACTORY` remains unset. There is no client switch to enable it. Public production execute refuses before job/attempt writes. The UI offers preparation/cancellation only, not a send button.

## Local TLS qualification, not provider certification

Synthetic tests use a disposable CA and local HTTPS server. The server-only injected connection keeps the enrolled logical hostname for TLS SNI and certificate hostname validation while redirecting the socket dial to loopback. Its fixture-specific SSL context trusts only the explicit test CA; certificate verification remains required and hostname checking enabled. No global trust store, certificate bypass or verification-disable flag is used. Invalid trust/hostname/expiry cases must refuse before application HTTP credentials reach the server.

These tests can establish the exercised TLS verification, exact request/header/response handling and one-shot local state transitions. They cannot establish trust in an actual commercial provider, validity of a real key, model tokenization, pricing, billing enforcement or a remote retention policy. No external endpoint, real credential or paid model call is used. Model-assisted search still has no production result contract; organizer production dispatch remains disabled.

The reviewed token request is bound into the full preview payload, its hash and the host wire request. Existing durable job records retain that payload hash, not the complete outbound body or a separate selected-token-limit field. Historical job inspection therefore cannot reconstruct the chosen limit from the hash alone. This is not a complete retained payload/budget audit trail.
