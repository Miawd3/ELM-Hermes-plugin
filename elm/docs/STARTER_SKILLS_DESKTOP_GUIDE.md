# ELM starter skills in native Desktop (r29 candidate)

This candidate adds native registry-backed plugin entries to the existing **Capabilities → Skills** interface. Earlier r27/r28 versions did not list registered plugin skills there; their synthetic component tests were not discovery proof. r29 requires both the updated native backend routes and frontend.

## Use

1. Load the ELM plugin on the patched host and select the intended connection/profile.
2. Open **Capabilities → Skills** and search `elm:`. The native catalog requests metadata; it does not load all instruction bodies.
3. Select a qualified skill to read its packaged text. Plugin rows show **Plugin · elm**; the detail identifies plugin ownership and read-only instructions.
4. Use the native switch beside the skill to enable or disable it. Plugin reads and toggles send the exact registration identity from the displayed row. If the registration or installed file changed, refresh rather than retrying with an old confirmation.

The six names are `elm:source-research`, `elm:documentation-lookup`, `elm:verification`, `elm:delegation`, `elm:creative-continuity`, and `elm:debugging-recovery`.

## Safety and limits

Plugin instructions are package-owned: Edit, Archive, and Lock controls are hidden for these entries. Native backend mutation guards separately protect qualified plugin names and physical package aliases; frontend hiding is not the security boundary. Ordinary disk-skill controls remain unchanged. The native interactive CLI disk selector is not claimed to discover registry entries.

Selected text is displayed in an inert plain-text block, not executable Markdown/HTML/directives. No remote images or source links are loaded. Query caching includes plugin registration identity and hides old data during revalidation or errors. A metadata refresh supplies a changed identity after reload or file replacement. This is not continuous revocation: already displayed text cannot be retroactively erased from a person's knowledge or a model's context.

These are static instructions, not background workers. Skill discovery or reading does not execute the procedure, authorize tools, or grant spending permission. Existing permissions still apply. Native model `skills_list`, `skill_view`, and slash handling remain available; ordinary model input-token costs may apply when metadata or a selected skill is sent to a model.

After replacing the pack, reload through supported native plugin handling and start a new session for fresh prompt/catalog composition. Disabling or unloading does not rewrite cached prompts or undo earlier work. Qualified `skills.disabled` profile configuration remains an alternative; preserve other entries when editing it.

## Evidence

Native component tests cover metadata filtering, exact token-bearing read/toggle requests, read-only controls, inert text, and stale-registration rejection. Separate real backend route tests must demonstrate registry listing, selected content, disabled-state enforcement, and mutation rejection. Neither component tests alone nor this guide claims a full installed-application screenshot or end-to-end live deployment.
