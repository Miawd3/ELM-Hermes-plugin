# Update UI audit (r26)

The pinned native Desktop already has **Update all** and a profile-wide auto-update switch in `app/capabilities/plugins/plugin-update-all.tsx`, backed by `store/plugin-update-all.ts`. It sends `plugins.manage` actions `update_all` and `auto_update`. This switch is not an ELM-only preference and must not be repurposed silently.

Native copy says the gateway checks at the configured hour interval and updated code loads in new sessions. Backend `plugins_cadence.py` runs due-gated checks; `plugins_auto_update.set_auto_update` clears the cadence marker on enabling, allowing the next housekeeping tick. These are not a guarantee that opening the Desktop immediately completes an update. Existing global update checking may already occur according to native settings; a separate ELM toggle cannot honestly claim to disable all host checks.

Single-plugin native updates use `store/agent-plugins.ts:updateAgentPlugin`, returning applied/unchanged/failed, capability-consent, or scan findings. Existing curated and tracked-git paths differ; an arbitrary git URL must not be treated as established trust. No automatic acceptance of widened capabilities, scan warnings, changed publisher/source, or an immutable pin is appropriate.

## Required new UI contract

- Per-plugin authoritative status, source/trust identity, current and proposed version or pin, scope, last check and outcome.
- Explicit opt-in with off default and independent explanation of checking/network requests versus applying code; never mutate the profile-wide switch.
- Exact reviewed state revision and context on saving; stale or uncertain responses require reconciliation, not replay.
- Honest startup timing: backend start/housekeeping is not necessarily Desktop launch; no claim until actual hook is implemented and tested.
- Unsupported or unconfigured trust is a disabled capability, not a successful enabled switch.
- No URL, credential, or publisher override input in the plugin panel.
- Existing native consent/security handling remains authoritative. UI must not offer a blanket bypass or automatically confirm code changes.

No updater calls, network checks, settings changes, or installation were performed for this audit. The implemented per-plugin control is documented in AUTOMATIC_UPDATE_UI.md; the audit above records the existing native baseline and required boundary.
