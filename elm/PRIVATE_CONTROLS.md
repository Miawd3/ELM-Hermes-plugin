> Catalog preparation note: this separate export removes all plugin-code update controls and sanitizes qualification paths. Historical qualification below applies to the base snapshot. See ../PUBLIC_EXPORT_NOTES.md and the root QUALIFICATION.json for current checks and unresolved gates.

# Private controls — isolated candidate

This source package is not installed or activated by its tests. It preserves the previous memory engine, Important results and selective native updater. No canonical ELM store or existing profile is migrated.

## Where the controls live

On a host exposing the public plugin-settings SDK: **Settings → Plugins → ELM → Private memory**. Focus a saved chat owned by the current profile/gateway first. Older SDKs without the supported settings contribution cannot display this page. Qualification uses the preserved Hermes 0.23 host and a real-browser SDK fixture, not the live desktop UI.

## Defaults and creation

Private-chat and private-workspace defaults are independent. They apply only through the explicit **New private chat**, **New private workspace**, and **New private-workspace member chat** actions. Normal native New Chat/New Project is not intercepted. Placement in a project alone grants no memory access. Existing containers, including containers first introduced to ELM later, do not receive these defaults.

A workspace can provide incoming source access without receiving a private chat's notes. Chat-authored records remain chat-owned. Private here means logical memory scoping, not local-only inference, encryption, semantic DLP or automatic personal-fact detection.

Creation requires a previously human-initialized fresh workspace memory store. Settings reads do not initialize memory. Native creation and plugin configuration are not one atomic host transaction: after an uncertain response, do not assume the container is configured, and do not repeat creation. Inspect the native list, check the original intent, or explicitly close the attempt without deletion/retry. Defaults and current-read-policy writes are read back and uncertain writes are blocked until explicit verification.

## Models

Conversation preferences are passed to native creation for the new chat; no global model is changed. Native conversation retry/fallback settings still apply.

Memory processing offers the existing host auxiliary route, a separate permitted provider/model, or **follow the current chat at draft-request time**. Following a chat uses a bounded public `model.options` snapshot for the focused runtime session, with durable-session/profile/gateway/lifetime checks. It does not assume the global auxiliary default equals the chat model and is not continuous tracking or a server-attested model-version lock.

Separate/follow routes require existing native override permissions and allowlists; the plugin never grants them. An unresolved/unavailable snapshot is refused. The same preference applies to explicit processing of a private workspace's pool and its explicitly created member chats; later defaults do not migrate that workspace. Following a workspace requires a genuine invoking member chat.

The host may retry/fall back internally. New-container memory generation therefore remains blocked unless the human explicitly acknowledges host-managed fallback. Requested and returned route/usage attribution are recorded when the host supplies them. Drafts still require learning consent, approved eligible sources, current provenance and human review; they are saved pending, not automatically approved or shared.

## Spending cap

OFF and unavailable. Enabling `cap_enabled` is refused. The current host interface does not supply a qualified fail-closed reservation/settlement gate for every native-chat, auxiliary retry and fallback attempt. A top-level counter would not be an honest universal dollar cap. The separate closed evaluation's $5 ceiling is unchanged; this candidate does not run more benchmark models.

## Verification and limits

Use the parent iteration's credential-free `run_product_tests.py`; source ZIP qualification reuses installed dependencies and executes the validator and consumers from a fresh extraction with module-origin checks. UI tests use headless Edge, real candidate APIs/stores and a labeled typed native-RPC stand-in. Actual host-owned LLM registration/trust/HTTP dispatch is exercised with only the external completion transport replaced. No real provider inference is performed by these engineering tests.

The existing store deliberately refuses overlapping locks. A concurrent startup read can report busy; use the explicit read-only Refresh control after it finishes. No mutation is automatically retried. Live activation, real provider access, live native UI acceptance and joint creation-flow UX adoption are not established by these tests.
