---
name: debugging-recovery
description: Investigate reproducible bugs or stalled attempts by changing hypotheses and measuring outcomes, rather than repeating failed edits.
license: Apache-2.0
---

# Debugging and recovery

Write down expected behavior, observed behavior and a minimal reproduction. Preserve the last known working state and relevant failing evidence before changing code.

Maintain a small attempt ledger: hypothesis, discriminating test, result, and what that result rules out. Prefer a test that separates plausible causes over a broad rewrite. Change one interacting layer at a time when that makes attribution possible.

If an approach repeatedly produces the same failure or no measurable progress, pause that approach. Check whether the observation itself is reliable, inspect a lower-level boundary, compare with a known-good example, or propose a different architecture. Do not escalate effort indefinitely merely because previous attempts were expensive.

Before retrying a state-changing operation, establish whether the first attempt took effect. Unknown payment, publication, migration or API outcomes require reconciliation, not blind replay. Never weaken authentication, isolation, tests or validation simply to make a failure disappear.

Finish with the verified fix, regression evidence and remaining limits. If blocked, preserve a reproducible handoff with the attempted hypotheses and the exact missing capability or decision.
