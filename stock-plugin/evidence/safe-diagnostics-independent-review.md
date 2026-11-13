# Independent review: pre-grant static help and context-only diagnostics

Reviewed runtime diff against published d454e06. No implementation edits by reviewer.

## Verdict
No blocking security or correctness issue found in the narrow change. No publication performed.

## Executed checks
- Python unittest discovery: 87 tests passed.
- All three desktop JavaScript scripts passed, including existing owner/connection guards, locked UI contracts, and rich-answer contracts.
- Independent adversarial probe: 540 combinations of supported/unsupported/malformed surfaces, absent/oversize/malformed/surrogate/current session values, static help, diagnostics, and parser-invalid arguments. Context and Store trap objects raised on every attribute access. All 540 returned without accessing either object; current-session sentinel never appeared in results.
- Read source and tests for missing storage, valid/expired/revoked/wrong-profile/malformed database cases. Informational routes never call Store connection factory and preserve file bytes.
- Protected memory routes remain downstream of existing sid authorization. No memory, counts, project names, paths, sharing settings or other session identities are returned by diagnostics.

## Limitations
- Diagnostics intentionally return authorization=not_checked and storage=not_opened. They do not identify an expired or revoked grant, wrong profile, malformed DB, or installation health. These limitations are explicitly stated in the response.
- Existing protected/denied regular commands may still initialize schema, unchanged. The no-mutation guarantee covers the new informational and parser-error routes, not every command.
- No actual Windows Hermes GUI testing or live provider testing was performed.
- Existing static help lists /elm on, although unified-local Desktop must use the exact-session CLI. New preceding help text explains that requirement, but onboarding could later improve with a verified copyable recipe.
