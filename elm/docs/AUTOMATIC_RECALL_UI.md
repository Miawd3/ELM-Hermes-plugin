# r13 optional private-chat recall controls

The active private review page now exposes explicit Refresh recall settings, enable/disable and bounded-budget preview/confirmation. Default disabled; this UI does not select ELM as Hermes' native memory provider or approve a record. The project page exposes no automatic recall settings.

Uses authenticated `plugin.elm.private.recall_settings.status`, `.preview` and `.apply` with the focused runtime session. Host derives ownership. Settings require supported host capability; enabling requires an existing explicitly initialized private store. An unavailable selected project can block settings: explicitly unbind in the project page, then refresh. The UI never bypasses host authority or claims an unsuccessful setting change succeeded.

Budgets are 1–8 records and 512–16384 UTF-8 bytes, defaults 4 and 8192. These are not token counts. Retrieval is deterministic newest approved/nonsensitive private records, not semantic search. No retrieval model or API is invoked by these controls. Added input to an existing paid chat can still cost money.

Disabling affects future request builds, not already dispatched requests, SDK/provider retries, prior model outputs, transcripts, exports or logs. User-visible status is a refreshed snapshot, not live authorization. Backend implementation and integration evidence determine delivery guarantees; SSR does not demonstrate provider transport.

Settings draft and server preview are frozen at review. Final confirmation is bound to the exact displayed action and authenticated current chat. Scope changes clear state and suppress late responses. A stale rendered form after refresh cannot stage against newer settings. Apply uses only the host's one-use preview token and explicit confirmation; there is no retry. On uncertain failure, read settings and refresh the private review to reconcile before intentionally staging a new change. Reading settings alone does not clear global mutation uncertainty.

Verification: 47 controller tests (7 added for settings), four actual React SSR suites with synthetic SDK adapters and HTML control/theme fallbacks. SSR checks budgets, scope, costs, disable boundaries, explicit confirmation, untrusted notice escaping and token nondisclosure. `ui-tests/private-recall-settings.html` is an actual component render with synthetic data, not a native installed screenshot. No browser sandbox bypass, live install, publication or paid API calls.

Availability requires the patched host, ELM selected as native provider, supported native primary ChatCompletions `api_mode`, a known context window and an explicit positive `max_tokens` output cap. Default unset/None `max_tokens` causes safe omission even with stored enabled=true. `host_supported` is capability only, not provider selection or active delivery. The UI changes neither provider selection nor output limits automatically.
