# ELM automatic-update policy UI (r26 candidate)

The actual ELM Desktop settings page uses native `plugins.manage` with fixed action `auto_update_plugin`, fixed name `elm`, and the active profile. It never calls `update`, `update_all`, remote check endpoints, or the profile-wide auto-update setter. Opening/registering the plugin performs no policy request. Refresh is explicit local policy inspection.

The page distinguishes inherited policy from explicit enabled/disabled policy and displays effective automatic application. Inherit may already be on through native profile-wide settings; it must not be presented as off. Explicit Off blocks ELM automatic application, not every native update check. Enabling is unavailable for manual-copy/unrecognized installations. The current candidate's companion host patch is never upgraded by this interface.

Each write requires a separate review and confirmation of the current source metadata, policy revision, and intended enable/disable choice. It sends the reviewed source fingerprint and revision to the native backend. Profile, connection, gateway activation, socket, and disposed-state guards prevent stale replies/actions from migrating to another scope. Uncertain or busy mutation outcomes clear the apparent state and require explicit refresh; there is no replay or assumption that an already admitted operation was cancelled.

Enabling authorizes future code execution from the reviewed recognized catalog source. Catalog recognition is not cryptographic publisher proof. Native capability widening, scan review, pin/source checks, and locking remain authoritative. There is no arbitrary URL, credential, publisher, or safety-bypass input.

The panel displays startup_check and check_hours from native status, plus the finite last_result code. Attempted and outcome_unconfirmed are not success. updated_needs_restart means disk publication succeeded but activation was not confirmed: further automatic application is disabled, requiring inspection/restart/reviewed reconsent, not replay. The native contract has no per-plugin last-check timestamp, and the UI says so instead of inventing one.

Timing is gateway housekeeping when due, not guaranteed Desktop launch. Updated code loads in new sessions. No hot-reload or immediate update completion is promised.

Evidence is offline synthetic controller requests and actual React SSR with synthetic status data, not a running installed application's screenshot or actual updater execution. `update-policy-preview.html` is labeled accordingly.
