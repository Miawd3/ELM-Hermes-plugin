# ELM recovery and rebuild checkpoint 1

## Verified base
Use public commit `29ee4024bf9a1696ef01365ad795b5bd4c4277ad` as the rebuild base. It includes all 157 files in the older recovered candidate, plus 30 files; 14 common files differ. The older snapshot is useful historical evidence, not a replacement for the newer public code. Do not infer current acceptance from old receipts.

The prior Nov12 integrated candidates, host-authority patches/rebase, organizer intent/preview/save pipeline, optional workspace capture, capability doctor and retrieval experiments were not recovered. Descriptions and former test counts remain historical records, not test results for this source. A separately reconstructed evidence-batching addition cannot be applied without its missing capture base and new tests.

## First bounded rebuild
A profile-independent diagnostic checks required callable presence and explicitly does not claim compatibility. Run from the elm folder with the intended trusted Hermes Python environment:

`python -m elm_plugin.host_requirements`

Exit 0 means required symbols are present but unverified; exit 2 means workspace host requirements are unavailable. This is not an install or repair command. Imported trusted host modules may have their own import behavior. No profile argument, model call or direct profile read/write is made by this diagnostic.

The workspace identity path now refuses missing host modules and absent/noncallable project ownership resolver with `host_api_unsupported` before opening its database. Human API maps that error to HTTP 503. It does not substitute current directory, active sidebar or inferred projects as authority. This is a controlled failure, not functional workspace compatibility.

Fresh evidence: 10 synthetic unit tests passed. Tests include unchanged existing database bytes, nonexistent profile staying nonexistent, redacted import failures and a unit extraction of the real HTTP failure mapper. No full FastAPI request, installed host, GUI, Windows or live provider test was run. Source inventory and archive checks are recorded separately.

## Rebuild order
1. Preserve this baseline and every reviewed incremental patch in persistent storage, with exact source hashes and test receipts. Every handoff must name the persistent copy, not just a local path.
2. Recover/fetch an exact official host commit and implement a versioned read-only session/project ownership contract with explicit compression/reset lineage and publication guard. This is the shared dependency for most missing features. Use official APIs; do not infer access from paths or copy old SQLite assumptions. Verify stock fallback separately from paired-host functionality.
3. Restore native install/onboarding and honest read-only capability diagnostics; run fresh offline disposable-profile install, read/recall, pending draft and cross-chat-isolation smoke. Update README at the same time. Current diagnostic is only the first small part.
4. Restore UI in bounded independent increments: Important toggle/timeline; folders; separate search and organizer model settings; source-backed wiki. Rich answers and its host integration need a separately verified source. Do not depict static previews as implementation.
5. Rebuild organizer preview/confirm/results then per-proposal pending draft. Use authority-scoped host RPC, not untrusted session selectors. Revalidate source/settings/owner at request admission and publication, keep one-shot intent and uncertain-write handling. Pending draft is not approval.
6. Implement per-plugin host-owned auto-update with default Off, pinned-reference behavior, publication locks and fresh single-snapshot policy. Reject both thrown read errors and FailedConfigRead fallback; test Off races. Do not restore the forbidden independent plugin self-updater.
7. Rebuild opt-in bounded local evidence only after authority is restored. Windows is the primary practical target. Prior POSIX prototype does not prove Windows support. Add actual Windows-qualified secure storage or keep unsupported platform explicitly disabled. Retention, deletion semantics, consent revocation and no default model egress require tests.
8. Restore reviewed skills with provenance/license metadata; distinguish selection, execution, draft learning and approval. Saved Nov11 skill prototype is research input, not integrated feature evidence.
9. Re-run representative token/answer-quality evaluation on frozen independent data after product behavior is restored. Failed paragraph/adjacency experiments must not be silently integrated. No claim toward 60% at700 tokens follows from current unit tests.

## Ownership and publication
Only an isolated local source copy was edited. Public repository and user installations remain unchanged. This is a recovery checkpoint, not the prior complete candidate or a release. The root agent owns further integration and publication decisions.

## Recovery r5 host layer
An experimental host patch now provides explicit principal-scoped project selection and
cross-store publication fencing. This plugin source does not yet wire the selection API
into its old workspace UI/provider; do not claim project recall or installation repair complete.
See the enclosing checkpoint STATUS.md for tests and strict compatibility boundaries.
