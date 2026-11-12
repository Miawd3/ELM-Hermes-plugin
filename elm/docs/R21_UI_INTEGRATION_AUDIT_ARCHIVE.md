# r21 Desktop UI integration and release gaps

## Source-level integration verified

Pinned host base: `126980e47b826963b26bf57d210106d849322f8a`. Examined actual Desktop runtime-loader, SDK exports, plugin context and Electron unified-package materialization. The active ELM half is `elm/desktop/plugin.js`, unified ESM importing only `@hermes/plugin-sdk` and React. The host materializes unified desktop halves into its app-level desktop-plugin root; the loader then reads the materialized plugin.js. It is not a standalone screenshot or invented HTML plugin system.

The active default plugin is id `elm`, defaultEnabled=false. Agent installation/registration and Desktop enablement are distinct, opt-in concerns. The contribution uses `SDK.host`, not nonexistent `ctx.host`; authenticated RPCs run through `SDK.host.request`. Scope requires a focused existing saved chat, matching active profile/connection/owner, open gateway and supported capability. No settings/RPC/model calls are made merely during registration.

Two native route/sidebar contributions:
- `/elm-private-review`: Private memory.
- `/elm-project-review`: Project memory.

When route/sidebar areas are absent but registerSettingsPage exists, these same components register as private-review and project-review settings pages. Without either supported surface, no invented fallback appears. Disposal removes both controllers' subscriptions. Public SDK Button/Input/Textarea are used when available; native HTML fallback controls are retained.

## Stock versus patched host

The pinned stock source exports the frontend SDK surfaces, but does **not** contain `hermes_cli/plugin_memory.py`; its absence was checked directly against the pinned commit tree. Scoped owner/read/publication/capture/request authority requires the cumulative host patch. A repository installing or a page rendering on stock Hermes does not establish functional scoped memory. Missing backend capabilities fail closed instead of using legacy global memory. A manifest version range is not a claim the unpatched stock release supports these features.

Candidate installation must use the packaged `elm` plugin folder and the matching pinned patched host. Do not install the inactive legacy-plugin.js as a second desktop plugin. Native Hermes project creation/sidebar behavior is distinct from this candidate's explicit ELM project-ID binding and per-chat consent. The UI does not supply a verified native project picker or replace Hermes projects.

## Actual supported candidate UI

Private record inspection/manual pending creation, source snapshots and exact-excerpt review; correction/approval/trash/restore; reviewed pasted export copying and receipts; separately opt-in private request recall and local conversation capture; source/record sensitivity and provenance inspection; unavailable-extraction local payload inspection; authenticated retained-job/proposal review with individual pending acceptance. Project binding, explicit consent/reconsent, project records and lifecycle are separate. Backend requirements and limitations are described in each feature document.

## Not restored or release-qualified

- Chat folders/workspaces as native chat organization: not implemented by these pages.
- Native rich-answer bubbles, model-selected progress/question/final labels: not integrated.
- Important-message highlighting, side-rail jump markers or their toggles: not integrated.
- Auto-update/install-on-startup toggles: not implemented by the active candidate UI.
- Native wiki/Obsidian bridge, 500-skill retrieval/catalog or selectable organizing-agent model: not integrated.
- Production model-assisted extraction/send/credential configuration: unavailable. Retained-job tests use internal synthetic local qualification only.
- Project automatic model recall, privacy erasure and full legacy migration: not provided.
- Inactive legacy UI source is preserved as reference, not claimed recovered functionality.

No current native Desktop installation, display/browser interaction, Windows acceptance, accessibility audit or visual screenshot acceptance has been completed. Historical Chromium sandbox launch failure remains a limitation, not a reason to bypass it.

## r21 verification

Product frontend source unchanged from r20 (SHA-256 `259df2bdbae558c7e55d4d9e1eaaaeda128b8cdfeb6824e391671820dfbd6ee2`). Added three actual entry-registration tests covering opt-in two-route registration, settings fallback and unsupported-surface noninvention; all registration tests prohibit RPC. Total **78 controller/registration tests pass**. **Eight SSR suites** freshly rebuilt from actual current React components pass, including inert text, token/secret omission, exact preview/confirmation, owner fences and retention/availability disclosures.

Synthetic SDK adapters, CSS and data produce reviewable HTML evidence, not native installed screenshots. Browser-ready bundle rebuilt. No source install/live settings change, publication, paid API/model call or browser sandbox bypass performed.
