# Route-bound organizer preparation UI (r34)

The current-chat private memory page retains its destination-unresolved local payload preview and adds a distinct **Prepare exact organizer payload (not sent)** action. Select one to four exact active private source IDs. This may reveal complete sensitive source text locally.

The backend requires native interactive authority, a dedicated active organizer slot, and an exactly matching saved organizer model preference. The UI does not supply or retrieve a key, endpoint or model override. It receives secret-free recipient metadata and the exact prepared payload.

The preparation display includes provider, HTTPS endpoint, organizer slot/version, route digest, model inside the full payload, source revision/digest/sensitivity pins, payload digest, reserved job ID and 300-second expiry. A reserved job ID is not a stored result or proof of sending. All source/model text is rendered inertly with no remote images, links, code execution or recursive directives.

**Production execution remains unavailable. No execute/confirm-send button exists.** Cost is unknown. The 512-output-token and 32768-serialized-byte limits are not monetary spending caps. Neither native credential enrollment nor preparation grants external-processing consent. Future live execution needs separate exact payload/destination consent and qualified transport and cost controls.

Explicit Cancel invalidates the prepared token, not a running network request: none was sent. Replacing a preview cancels the previous same-owner preparation first. If cancellation fails, the UI clears the visible preview and does not automatically continue or retry. A switch of owner/session/socket clears visible data and never attempts cleanup against the new owner; old server-side preparations expire independently. Backend validation remains authoritative for slot/source/preference changes after preview.

Strict response validation rejects unexpected fields, secret-bearing recipient metadata, enabled production flags, wrong source pins, malformed hashes, wrong transport policy or unsupported payload shape. Rendering is point-in-time review, not a guarantee that a slot remains unchanged. Tests use synthetic fixtures only. SSR is the real component with a synthetic adapter, not installed native acceptance or a screenshot.

## r35 bounded output request and precise local limits

The organizer preparation form lets the user request 1–512 maximum output tokens (default 512). This number is included in the exact payload and bound to the returned preparation. It is a provider request, not measured output, a guarantee of provider compliance, or a billing cap. Editing the requested value or selected source IDs clears and cancels the displayed preparation; another preparation is required. Invalid/fractional/out-of-range values cannot prepare.

The displayed budget separately identifies canonical outbound-body bytes (local cap 32768), the local response-body limit (8192 bytes), and the requested provider output-token parameter. Input token count and pricing remain unknown, with no monetary limit. The 10-second socket timeout is not an absolute end-to-end deadline. Production execution remains disabled, so these controls do not authorize spending or cause a provider call.

Validation rejects contradictory monetary/pricing flags, changed fixed byte caps, invalid actual body byte counts, or any mismatch between requested tokens, payload max_tokens and returned budget metadata. Tests use synthetic transport/controller data only, never real provider requests.
