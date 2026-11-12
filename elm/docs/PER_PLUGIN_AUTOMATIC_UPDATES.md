# Per-plugin automatic updates: narrow native candidate (r26)

This is an additive host policy over Hermes's existing updater, not a self-updater
inside ELM and not permission to update Hermes. The current ELM profile-copy install
is **ineligible**: it has no installer-owned catalog provenance.
The control reports unavailable rather than inventing an origin or falling back to
legacy code. Tests use synthetic local repositories and injected catalog fixtures;
no real catalog update, real plugin download, user installation or host update was run.

## Scope of the first slice

An installed plugin must have an authoritative installer registry record matching an
in-tree **official/verified** catalog identity (name, HTTPS repo, subdirectory and tier),
an exact installed commit, and an intact bounded source tree. A plugin's own manifest
or `.hermes-catalog.json` convenience sidecar cannot declare itself trusted. HTTPS/source
matching is provenance, not cryptographic publisher authentication or a code sandbox.
Opting in authorizes future catalog-pinned code from that source to execute. A source,
subdirectory, tier, installed-tree or installed-revision change outside a verified policy
transition requires new consent. Catalog commit changes from the same approved identity
are the intended unattended update, not a new repository grant.

This slice is deliberately dependency-free and requires prebuilt, syntax-checkable code. Existing or
candidate pyproject/setup/requirements/Node package/lockfiles, node_modules, manifest
Python dependencies, submodules, JSX/TypeScript build inputs, symlinks, junctions and
nonregular files are refused. Tree inspection is limited to 10,000 entries and 64 MiB;
Python/JavaScript syntax inspection to 2 MiB per file / 16 MiB total, at most 16 JavaScript
files. JavaScript requires an already-selected native PM Node runtime; it parses stdin via
`--check` in module mode for .js/.mjs and CommonJS mode for .cjs, without importing or
executing candidate code. Each parser process has a 10-second timeout and a clean
environment without NODE_OPTIONS/NODE_PATH or loader preloads, in a temporary directory.
Missing Node refuses eligibility; no Node/toolchain is downloaded. This qualifies syntax,
not browser API behavior or module availability. Manual copies, arbitrary Git repos, held refs,
community catalog entries and unknown provenance require the existing manual workflow.

## Native API and consent

`plugins.manage` with `action:"auto_update_plugin", name` returns **local-only** status.
No live catalog request, plugin code import, check or installation is performed merely
to inspect or configure the policy. The active native profile/control transport is the
authority; this is not a model tool or chat-memory RPC.

To change it, send the same action/name with `enable` (an actual boolean),
`expected_revision`, `expected_source` (the displayed source fingerprint), and
`confirm:true`. No arbitrary URL, path, source, branch or dependency override is accepted.
The write is revision/source-CAS under the existing native per-plugin update lock.
On busy/stale/error, refresh; do not present a disable as successful. Managed configurations
refuse this local policy write. Status exposes only allowlisted source metadata, not
credentials, arbitrary exception text or the private installed-tree digest.

Status fields include `mode` (inherit/enabled/disabled), configured `enabled`,
`effective_auto_apply`, `revision`, `source_fingerprint`, allowlisted `source`, `eligible`,
`reason`, `last_result`, `startup_check`, `check_hours` and `notice`. An interrupted
`attempted` state can remain configured-enabled while **effective apply/startup are false**;
inspect it and explicitly reconfirm rather than treating the flag as permission to retry.

- No policy is created automatically. Absent policy is **inherit**, preserving the
  pre-existing native profile-wide behavior, including an already-enabled global switch.
  It does not mean every old updater path has been disabled.
- Explicit **off** overrides all unattended apply entry points, including native global
  cadence and unattended Update all. It does not disable existing global read-only update
  checks or independently requested manual named updates.
- Explicit **on** grants this eligible plugin a boot check and daily check in the native
  gateway process, independently of the global interval/auto_apply values. Those global
  settings are never changed. Multiple processes still share native per-plugin locking.
  Checks contact the native live catalog and may fetch the exact reviewed candidate.
- The native housekeeping/startup hook is used. ELM UI refresh is not a hidden check or
  an installer. No host upgrade is initiated to satisfy a candidate's requirement.

## Admission, execution and outcome

The native lock spans the admitted update. Disable obtains that same short-timeout lock:
if an operation is already admitted it returns busy/refused, not a false claim that the
operation was cancelled. A successful disable before admission is rechecked **inside**
the lock even on the legacy unattended fallback, preventing absence→off races.

A durable policy `attempted` receipt is written and fsynced before candidate staging.
The native staged updater receives the exact catalog commit and host-only policy guard.
It rechecks current policy/source before staging, before reading/validating the candidate,
before dependency admission and immediately before publication. The dependency-free lane
skips dependency refresh instead of running package installers. Candidate Python is
compiled for syntax without execution (JavaScript is parsed by the bounded Node check);
catalog and manifest host-version requirements
are strictly parsed and unknown/incompatible requirements refuse. Widened surfaces,
changed names, unsafe trees, local tracked edits and native scan refusals require review.
Untracked/ignored user files use the native carry-forward helper, not silent deletion.
Native publication still owns PM admission/recovery; plugin code may execute during that
admitted process and activation. A static scan is not proof that code is harmless.

`last_result` is one of configured/current/attempted/updated/updated_needs_restart/
needs_review/outcome_unconfirmed. `updated_needs_restart` means disk publication is known
but native activation was absent or requires restart; automatic application is disabled.
`updated` follows disk/source verification and an explicit successful activation response,
not proof of all plugin behavior or all open sessions adopting every capability.
Failures before publication preserve the installed tree through native staging. A failure
after publication or a lost response can leave new code present. The policy is disabled
for review where possible; if final bookkeeping fails, the durable attempted receipt
blocks restart replay. Inspect installed revision/native recovery state, then explicitly
re-consent. There is no automatic downgrade, crash replay or global exactly-once claim.

Policy metadata is profile-local, max 64 entries / 128 KiB, atomic replace + file fsync
(and directory fsync on supported non-Windows hosts). It contains source identity,
installed revision/digest, monotonic policy revision and fixed outcomes, not code bodies
or secrets. It is not protection against a malicious local filesystem owner or rollback
of the entire profile. The native PM publication journal and policy are separate durable
stores, so an interrupted cross-store handoff is conservatively a review condition, not
an atomic all-or-nothing promise. A process-local daily timer resets on a new gateway
process; policy records persist. There is no per-plugin last-check timestamp UI claim.
