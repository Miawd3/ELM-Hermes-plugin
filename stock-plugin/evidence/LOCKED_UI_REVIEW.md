# Locked-state UX candidate

Base: published 052e2e7962db1fe781e0aa4af4f9de86cc966238. Not published.

Frontend-only change: explicit owner-bound setup/locked screen for missing/expired/changed grant; separate unsupported and unavailable errors. Unknown error details are not echoed. Disabled placeholders describe available features, not saved chat settings. Exact-profile guide link, runtime session ID and profile label are displayed only for the authenticated focused owner; label explicitly is not a filesystem path. No automatic grants, new backend routes or permission changes.

All 83 Python tests and three JavaScript scripts passed. Independent reviewer found no code-level blocker and suggested a wording correction (applied). Imported helper exact parity and original official loader imports remain verified. Stale setup/errors are fenced by the same connection/profile/session/epoch as saved settings.

No native Desktop visual validation performed. Current workspace lacks full host build. Headless component screenshot attempts failed due sandbox socket EPERM; locked-preview.html is a synthetic component rendering fixture, not a screenshot or proof of host rendering.

Known limitations: terminal grant remains necessary; exact_session_cli_grant_required does not distinguish never-granted from historical expiry/revocation. The UI must not pretend to know saved disabled settings while locked. Core folders, timeline and native bubbles still unsupported. This does not implement a provider adapter.
