---
name: verification
description: Check that a claimed coding, document, research or action deliverable actually exists and satisfies the requested outcome.
license: Apache-2.0
---

# Verify before completion

Translate the request into observable acceptance conditions. Separate producing an artifact, validating it, and delivering it to the intended place: one does not prove the others.

For code, run relevant tests against the changed bytes and exercise the affected integration boundary. Distinguish mocks from real dependencies, a renderer build from an installed app, and a successful command from its intended effect. Preserve failures that explain a later correction.

For documents or visuals, inspect the exported result, not just the source. For research, check that citations support the precise claims. For external actions, inspect the destination or authoritative receipt before saying it completed; avoid repeating an uncertain action.

Use focused checks proportional to the cost of a mistake. Report what passed, what was not tested and what remains blocked. Do not call a metric an improvement without a comparable baseline and the same evaluation conditions. Keep a durable copy or recovery pointer when the user depends on continued access.
