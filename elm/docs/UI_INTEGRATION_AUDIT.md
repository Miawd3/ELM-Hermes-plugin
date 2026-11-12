# Current Desktop UI integration audit

This document describes the inherited r38 implementation and the bounded r39 skill-reference usability addition (qualification tracked separately). Historical r21 wording and evidence are preserved verbatim in `R21_UI_INTEGRATION_AUDIT_ARCHIVE.md`; they are not current feature absence claims.

## Native integration and authority

Pinned native host base remains `126980e47b826963b26bf57d210106d849322f8a` plus the packaged cumulative host patch. The unified ELM Desktop half is `desktop/plugin.js`, importing React and `@hermes/plugin-sdk`; the native loader materializes it into the desktop plugin root. Agent registration and Desktop enablement are separate. Desktop ELM defaults off. Missing required native authority fails closed; a manifest version minimum does not establish stock-host compatibility.

Private/project review route contributions and supported settings fallback use authenticated native requests. A focused saved chat, matching profile/connection/current owner and open gateway are required for scoped memory controls. Those guards are not proof of a human caller or isolation from trusted installed in-process/renderer plugin code. Native Projects and explicit ELM memory binding/consent remain separate concepts.

## Implemented, bounded user-facing features

- Private/project record review, manual creation, lifecycle controls, explicit source snapshots/evidence, reviewed selected-export copies and receipts.
- Separate opt-in private automatic recall and local finalized-turn capture, with limits and sensitive-data notices.
- Read-only approved-memory wiki, explicit source-quote inspection, recipe-only reference drafts, and optional human-selected literal lexical search. Rejected experimental coverage search is NOT an active mode; no paragraph-extraction experiment shipped.
- Rich presentation badges through finite native directives, not arbitrary HTML or automatic model formatting.
- Explicit important-message highlighting and clickable native rail markers for loaded messages, with an off-by-default toggle and native viewport/session ownership checks.
- Metadata-only logical chat folders with actual native sidebar rows, current-chat filing/unfiling and bounded undo. No cwd, git, project binding, transcript or memory-permission change. No rename/delete/nesting yet.
- Per-plugin automatic-update policy UI using native source-bound consent; current manual-copy ELM is ineligible. No live updater qualification or automatic host upgrades.
- Six original text-only bundled skills, native plugin-provenance metadata, selected raw read-only content and scoped native disable controls. Plugin-backed file mutations and physical aliases are guarded. No 500-skill or automatic routing performance claim.
- Separate declared search/organizer model preferences, native dedicated encrypted credential enrollment UI, local exact organizer-egress preview/cancel and retained result review. Production external model dispatch remains disabled; enrolling credentials or saving preferences does not enable it.

## Skills invocation boundary

Native interactive slash projection uses a lowercased qualified name, but only after current file platform/environment/app predicates, disabled-state and collision checks. Desktop catalog metadata alone is not proof of slash eligibility. The r39 Copy skill reference affordance copies the exact qualified `name` from a fresh matching selected-content response, without adding a slash or sending a message. Copying a qualified name is a reference aid, not invocation, installation, permission grant or guaranteed command availability. Selected raw-content reads never preprocess or execute a skill. The existing backend response schema is unchanged. Actual slash availability also depends on disk/project command precedence and interactive context that this profile-scoped read does not establish; no discovery or catalog scan is added. Any future invocation affordance must respect native current eligibility and scope rather than infer it from a UI label.

## Qualification and remaining gaps

Inherited r38 evidence: 166 Node tests and16 rebuilt SSR suites; active backend cumulative1061 tests across92 files, clean profile-copy124 tests across17 files; fresh full four-stage native TypeScript and renderer build passed. These counts apply to r38, not an assertion that unfinished r39 changes have passed. Current release verification is maintained separately in the checkpoint TEST_VERIFICATION.md.

Synthetic component/registry/native-handler tests and SSR are not screenshots or a successful installed Windows/Desktop acceptance session. No complete native Electron packaging, real desktop visual/accessibility acceptance, public repository deployment, actual remote plugin update or paid provider call has been established. The renderer build does not bundle dynamically loaded ELM JavaScript; its tests are separate.

Still absent: operational production model search/extraction, cross-chat user-profile recall, full legacy migration, project automatic recall, permanent privacy purge, unlimited history retention, Obsidian/whiteboard bridge, arbitrary structured rich-document storage and universal skill routing. Inactive legacy sources and rejected experiments are references, not active functionality.
