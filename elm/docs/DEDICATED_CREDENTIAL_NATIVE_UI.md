# Dedicated native credential enrollment (r33)

Native Hermes Settings → Tools & Keys → Settings includes a dedicated model credential section. This is not an ELM plugin settings page and sends no secret through plugin RPC. Open a saved chat on the same selected settings profile and connected host first. The saved chat is an authorization anchor; slots belong to the authenticated principal within that profile, not only to that chat.

1. Read the trust warning and explicitly acknowledge the trusted host and enabled plugins.
2. Refresh secret-free slot metadata. This performs no model/provider request.
3. Select Search or Organizer, then enter the exact provider, model and HTTPS `/v1/chat/completions` recipient.
4. Review the binding. Only then enter the key into the password input and explicitly confirm enrollment.
5. Revocation is separately reviewed and confirmed. Historical slot metadata remains after revocation.

Saving a binding does not activate dispatch, change the chat model, test a provider, approve external processing or authorize future spending. Production model execution remains disabled. Future processing needs separate recipient, exact payload and cost approval.

## Security boundary

This is first-party UI but not an isolated secret window. Native plugins execute in the renderer with app authority; trusted local code and installed plugins may access secrets. Do not enter credentials if you do not trust that environment. The host's file/keychain storage does not eliminate renderer exposure. There is no plaintext getter, reveal button, query-cache secret, localStorage copy or secret notification. JavaScript strings cannot be guaranteed zeroized.

The password input is cleared before awaiting a mutation and on cancel, unmount or owner/socket change. Native authenticated methods use exact saved-session authority and backend context/revision checks; authentication is not proof that a human clicked. Repeated mutation clicks are blocked while a request is active. Lost replies are uncertain and require explicit metadata refresh; the UI does not replay mutations or claim success on failure. Errors are fixed generic messages, never raw backend exception bodies.

## Verification limits

Component tests use synthetic keys and mocked native socket requests only. They do not establish real-provider compatibility, actual key storage, encryption, installed runtime acceptance or a screenshot. Backend/native-auth tests qualify those separate host boundaries. No real keys, provider calls or paid model requests were used.

The UI checks both registry socket routing and renderer owner/profile agreement before admitting a request. Mutation receipts must advance the reviewed revision and slot version and match the reviewed role/recipient/model, otherwise they are treated as uncertain. The native canonical client's retry fence only applies to retained model/reasoning session mutations, not these credential methods.
