# Memory model preferences (r31)

The ELM **Memory model preferences** settings page stores separate intended selections for **Memory search** and **Memory organizer**, scoped to the current authenticated saved chat. This is preference storage only: actual routing remains unavailable.

Explicitly refresh local saved preferences. Existing private-memory setup is required; the page never initializes a store automatically. Choose a role, enter declared provider/model identifiers and a credential-free HTTPS chat-completions endpoint, then **Review preference**. Inspect the previous and proposed canonical values before **Confirm saving preference**. **Review clearing selected role** saves a null selection after the same separate confirmation.

No available-model catalog is implied. The native model menu was deliberately not mounted because it requests model options and may invoke catalog/provider work. These inputs do not check credentials, availability, pricing, reasoning support, or task quality. No effort selector is provided. Do not enter API keys or secrets. The backend validates bounded identifiers and allowed endpoint paths; the UI displays the canonical reviewed destination without accepting an unrelated destination.

Saving does not authorize external processing, change the chat model, activate recall/capture, install a local model, run a connection test, or enable a fallback. No model or network request is performed by this feature. Local saved preferences are not a claim that search/organizer agents have been implemented.

Requests use authenticated `model_preferences.status`, `preview`, and `apply`. Preview pins the current preference revision/context and previous role value. Apply requires a one-use preview and explicit confirmation. Owner/socket changes clear the view; stale rendered handlers and late responses are rejected. An uncertain save clears the token and requires explicit refresh, never replay. No raw server errors or credentials are displayed.

Tests cover the actual controller and React component with a synthetic transport. The labeled `model-preferences-preview.html` is not an installed-app screenshot. Native host compilation does not substitute for these dynamically loaded plugin component tests.

## r32 role-specific readiness

The page additionally displays the native `routing_readiness` report for search and organizer. `selection_saved` means only that a preference exists, never that a route is configured. Both roles remain unavailable. Fixed, human-readable blockers identify missing dedicated credential enrollment, production destination-pinned dispatch, explicit egress execution, unverified provider compatibility, and lack of an enforceable spending bound. Search also lacks its model-assisted result contract.

No calls or charges occur through this feature now. Future execution requires separately reviewed recipient, exact payload, pricing and spending limits; no cost estimate or enforceable cap is invented. The extraction panel explicitly states that saved preferences do not activate it. Older hosts without the additive readiness field are labeled as not reporting role-specific readiness, with execution still unavailable.

## r33 enrollment versus dispatch

The patched native host now has a separate trusted-host credential enrollment surface. ELM does not read slot state or secrets. The role readiness blocker is now `credential_route_dispatch_binding_unavailable`: enrolled credentials are not connected to production dispatch. A saved preference still cannot enable extraction, and no positive readiness flag is inferred from the existence of enrollment software. Stock hosts do not gain this native surface from the ELM plugin alone.
