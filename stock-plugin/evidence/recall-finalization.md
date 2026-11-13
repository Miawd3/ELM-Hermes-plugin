# ELM recall finalization race repair

Base: published bffb4226f30540a3173bf35850a8af620504f79c.
The Pro probe validates exact source SHA256 values before executing. Independently rerunning it on the base confirmed:
- automatic recall returned context after access was disabled between retrieval and return;
- explicit recall returned an approved row that was trashed after retrieval, without a policy revision change.

## Repair
Both paths share `_recall` and a `finalize_records` transaction. Capture a profile-store identity, monotonic content generation, and policy revision before retrieval. SQLite triggers advance content generation on each record insert/update/delete, including edit-and-restore ABA. The finalizer uses BEGIN IMMEDIATE, rechecks current authorization/grant expiry/revision/identity/generation, verifies every row's current approved status, scope and exact payload, and builds the final result under the lock. Automatic failures return no context; explicit failures report a denial/retry.

No ranking, packing budget, schema content semantics or model behavior changed. Additive epoch table/triggers only. Existing stored records/grants preserved. Writes anywhere in the profile invalidate an in-flight recall conservatively, including unrelated inserts. This may increase retries. Write lock held for bounded serialization, never a model/network call.

## Evidence
71 existing tests plus 12 new race/finalization tests = 83 passed. Tests include policy revoke and ABA, trash, edit and ABA, direct delete, profile identity change, tampered candidates, expiry during materialization, and writer exclusion while materializing.

## Boundary and limitations
The final materialization is a linearization point. A mutation committed before it is rejected; a mutation ordered afterward cannot retract text already returned or sent to a provider. This does not implement erasure from remote model context, copied skill drafts or backups. Same-file backup rollback with restored identity/epoch is not detected. This patch does not claim a general security guarantee or solve organizer/source listing lifecycle boundaries. User source/provenance and derived-copy semantics remain unchanged. Actual Windows execution of new logic remains unverified.

No host modifications or paid calls were needed for these tests.

Independent review: 83 implementation tests and 5 additional adversarial checks pass. No narrow-patch blocker found.
