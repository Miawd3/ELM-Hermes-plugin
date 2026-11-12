> Current release boundary: [rc40 status](../RELEASE_STATUS.md) and [test report](../TEST_REPORT.md). Milestone details below describe individual contracts; they are not claims of a live organizer/search agent or stock-host support.

# Active scoped API index (r21)

This is an experimental exact-candidate API, not a stable stock Hermes interface. `register(ctx)` registers `ScopedMemoryProvider` and capability-gated authenticated RPCs. It registers no model-facing tools, legacy global draft command or legacy automatic memory fallback.

The native host supplies actor/profile/canonical identity. Client session transport fields are not authority; arbitrary root/profile/scope selectors are refused. Read callbacks and mutating callbacks require the in-process patched host. Capability flags describe individual host contracts, not full byte-level compatibility.

| Surface | Contract |
|---|---|
| `memory.owner` diagnostic, explicit workspace binding/status | [Binding](WORKSPACE_BINDING_RPC.md) |
| Private setup/create/approve/recall | [Private store](PRIVATE_WORKSPACE_V2.md) |
| Private list/get/correct/delete/trash/restore | [Inspection](docs/PRIVATE_WORKSPACE_INSPECTION.md), [lifecycle](docs/PRIVATE_WORKSPACE_LIFECYCLE.md) |
| Project consent, inspection, records and lifecycle | [Project contract](docs/PROJECT_WORKSPACE_CONSENT.md) |
| Private source snapshots/excerpts/withdrawal | [Source contract](docs/PRIVATE_SOURCE_CONTRACT.md) |
| Private recall settings and native request lane | [Request recall](docs/SCOPED_REQUEST_RECALL.md) |
| Local capture settings and captured turn receipts | [Capture](docs/LOCAL_CONVERSATION_CAPTURE.md) |
| Local curation payload preview, unavailable production dispatch | [Foundation](docs/MODEL_CURATION_FOUNDATION.md) |
| Durable curation jobs list/get/accept | [Job review](docs/CURATION_JOB_REVIEW.md), [synthetic route qualification](docs/SYNTHETIC_CREDENTIAL_ROUTE.md) |
| User-supplied export preview/apply/receipts | [Declared export copy](docs/DECLARED_EXPORT_IMPORT.md) |

Human confirmation fields and immutable review tokens are an authenticated-client protocol, not proof a human physically clicked. Model output never becomes approved memory automatically. Historical curation recipient metadata is not a current route grant.

Public production dispatch always refuses. Private loopback test factories and synthetic credential resolvers are not public APIs or a way to enable real extraction. There is no public fake-output import.

On uncertain mutations, inspect native/current state and the relevant receipt/job/trash map before acting. Never infer rollback from an error or replay external side effects blindly. Read [recovery](docs/CANDIDATE_INSTALL.md#recovery-and-rollback).
