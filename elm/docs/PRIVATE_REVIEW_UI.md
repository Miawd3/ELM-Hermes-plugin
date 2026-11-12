# Experimental current-chat private memory review

The active unified Desktop entry is `desktop/plugin.js`. Hermes loads it through its existing runtime plugin loader, using the public `@hermes/plugin-sdk` and the host React singleton. Its native route is `/elm-private-review`, labelled **Private memory** in the sidebar. On hosts without the public route areas, the existing plugin settings-page registration is used if available. It remains opt-in (`defaultEnabled: false`).

This candidate requires the rebuilt authenticated private-memory RPCs. It does not make the public release compatible with stock Hermes automatically, and it does not change native chat, settings, profile or project behavior.

## Explicit human workflow

1. Focus an existing saved chat on its owning connection/profile. Open Private memory.
2. Click **Refresh records and trash**. Nothing is read or initialized automatically on registration.
3. If no private store exists, review and explicitly confirm fresh setup. No legacy data is imported.
4. Filter records by pending, approved or invalidated. Click **Inspect record** or **Reveal sensitive record** to fetch its body for human review. The page exposes full record/provenance metadata as inert text.
5. Review then confirm approval or correction. Corrections return records to pending, replace the previous current text without version history and invalidate dependent evidence.
6. Preview deletion, inspect the affected IDs and confirm retention in private trash. This is not erasure. Restore groups explicitly as pending, never automatically approved.

A failed mutation is treated as uncertain. The UI does not repeat it. Refresh records and trash to inspect the current state; trash metadata lets a lost-response deletion be rediscovered without returning retained bodies.

## Scope and display protections

Every request uses `SDK.host.request` over the existing authenticated gateway, with the current focused runtime session. No new REST endpoint, authentication scheme, localStorage cache, credential access or model tool is introduced. The host remains the authority; renderer identity checks are additional intent guards, not authorization.

Focused runtime/stored session, owning profile/connection, active profile/connection, gateway state and activation epoch bind each operation. Switching context clears cached records, bodies, confirmation and draft state. Late responses are discarded. The page also hides stale content during render before a layout effect runs. Requests already admitted before a context switch may still complete for their original owner; no cancellation or cross-store transaction promise is made.

Staged changes bind the exact rendered owner and record revision. Final confirmation binds the exact staged action. A stale handler cannot approve a new selection or initialize a newly focused chat. Reads and writes are never automatically retried. Every title, source, body and metadata value is rendered through React text nodes, not HTML or active links.

Sensitive human inspection is distinct from model recall. The existing backend sensitive/inferred-user exclusions remain in force. Project selection still does not authorize project recall; provider injection, migration and dependency-pin repair remain separate work.

## Preserved legacy UI

The previous complete Desktop entry is preserved byte-for-byte as `desktop/legacy-plugin.js` for recovery research. It is not registered, imported or refreshed by the new entry. Its older Memory, Important results, workspace and settings panels have not been qualified on this host. Recovered v6 DOM previews informed wording such as “project placement is organization, never permission,” not a claim of exact visual restoration.

## Verification and visual evidence

- The original r9 baseline had eleven Node tests executing the real exported controller with a synthetic SDK transport. They cover explicit reads/approval, immediate context clearing, late results, stale setup/record/confirmation events, mutation uncertainty, ownership mismatch and unload.
- React SSR uses the real ReviewPage component and the official pinned React dependencies. It checks detail, provenance, confirmation, hostile text escaping and stale-content suppression. The generated detail/approval HTML is preserved.
- A browser-ready bundle and Playwright interaction harness are included with synthetic data and an SDK adapter. SDK Button/Input/Textarea are native HTML stand-ins in this harness; its colors/fonts are approximate harness styling, not the installed Hermes theme.
- Sandbox-enabled Chromium could not launch in this execution environment: `socket() failed: Operation not permitted` during process-singleton setup. Escalation and a disposable writable HOME did not resolve it. The browser sandbox was not disabled. Consequently there are **no verified browser screenshots or browser-interaction results**, and no native installed Desktop acceptance claim.
- The official pinned frontend dependencies were installed into the disposable host workspace with pnpm's frozen lockfile and scripts disabled. No paid model/API calls were used.

## r12 extension
Manual pending-record creation and private exact-source snapshot/excerpt workflows are now available. See CAPTURE_AND_CREATION_UI.md for confirmation, sensitivity, textual-identity and retention boundaries. They do not run models, fetch URLs or approve records automatically.
