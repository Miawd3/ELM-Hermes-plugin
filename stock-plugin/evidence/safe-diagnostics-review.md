# Safe informational commands candidate
Base: d454e06 (published base). No publication performed.
Changes: stock_runtime.py, README.md, tests/test_safe_diagnostics.py; regenerated source manifest.

87 Python tests and 3 desktop JavaScript scripts passed. Independent reviewer reran all suites and exercised 540 informational command/context combinations with storage and context-attribute traps: no access, no session ID disclosure, no blocker.

Static help is available before grant. Diagnostics report only syntactic current-context availability/support and explicitly say authorization not_checked and storage not_opened. They intentionally do not inspect profile, grant, expiry, revocation, database state, settings, counts, memory, other chats, or model services. The metadata result cannot authorize any action.

Missing storage, valid/expired/revoked grant, wrong-profile DB, malformed DB, malformed command, and private field tests passed without informational-route connection calls or file changes. Protected routes retain existing gates. Existing normal denied routes can still initialize schema; not changed here.

No live Hermes Desktop UI, Windows host, provider call or paid model test performed. This is not an end-to-end installation fix and does not implement native UI controls. Last post-review edit only clarifies in static help that Desktop/local /elm on cannot grant access and the CLI must be rerun after off; all tests rerun.
