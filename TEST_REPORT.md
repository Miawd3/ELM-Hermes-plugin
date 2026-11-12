# Restoration qualification · 2026-11-12

## Fresh checks on this publication candidate

- The complete host patch passed `git apply --check` and applied on a fresh checkout of official Hermes commit `126980e47b826963b26bf57d210106d849322f8a`.
- **164 portable JavaScript tests passed:** 159 controller/review cases and five whole-message classifier/preferences cases. Reproduce with `bash integration/run-ui-tests.sh`. These use the shipped source with synthetic SDK/React bindings.
- Python syntax compilation passed for 218 restored plugin and host-overlay Python files. Syntax compilation is not a runtime integration test.
- The complete recovery Node glob was attempted: 164 passed, four environment/setup failures because host React/esbuild dependencies were absent. The portable runner explicitly excludes host-dependent suites; it is not a disguised full-suite pass.
- The shipped plugin JavaScript and cumulative patch match the backed-up integrated candidate byte-for-byte (hashes below).

## Preserved earlier integrated evidence, not rerun claims

The recovered checkpoint reports 1,118 native backend/security tests, 127 clean-profile regressions, 177 dynamic JavaScript tests, 16 component SSR suites, four actual native whole-message tests, TypeScript checks and renderer build passing. Counts overlap and must not be summed. That evidence came from the pre-reset qualified environment; this public source update does not claim all of it was rerun here.

Earlier stock/patched loader probes reported scoped-provider unavailable/zero scoped RPCs on stock and 81 RPCs plus six starter skills on the qualified patched in-process host. A loaded plugin on stock Hermes is not supported installation success.

## Known failures and gaps

- A previous publication attempt ran retained historical `test_host_identity`, `test_workspace_api` and `test_product_native_updates` suites against the rebuilt host: **21 failed, seven passed**, involving older ownership/`set_session_project` contracts. Those legacy tests remain historical evidence, not current native qualification. Do not advertise the repository's entire inherited test suite as green.
- No fresh real Windows/Electron walkthrough, OS installer acceptance, real-provider test, autonomous search-agent test or new answer-quality benchmark has been demonstrated.
- Production organizer dispatch remains disabled. Live model aliases/request profiles and actual search-agent behavior still require work.
- No claim of reaching 60% at 700 tokens, reducing actual customer billing, or outperforming other memory systems is made.

## Integrity

- `elm/desktop/plugin.js`: `210a1ff6b069ca448e8708aa808b38924b7926583e926d0416285205550fd322`
- `integration/host.patch`: `f15b63d8562cc9b99caca6c61c60bc6756221c464a5f0ef599d4549ac32d00ac`

`python elm/verify_release.py` checks the packaged plugin inventory. A checksum proves identity, not safety, compatibility or a signature. No paid APIs, real credentials or live user profiles were used for this publication qualification.
