# Native Desktop plugin-skill inspection (r29)

The accompanying host patch extends the existing profile-scoped Skills catalog
and selected-content route. It does not add an ELM-specific mirror, disk copy,
private-memory reader, remote skill installer, or model tool.

`GET /api/skills` now includes current loaded, enabled plugin registrations as
metadata-only rows: `provenance:plugin`, `read_only:true`, `plugin_owner`, and an
opaque 32-hex `registration_id`, alongside name/description/category/enabled/
usage/locked. Category is plugin; usage is currently zero (not a measured usage
claim), locked is false (no editable skill lock). Only existing registry entries
are inspected. This read never calls discovery or imports new plugin code.
A plugin not loaded in the requested profile is not displayed. Both native
plugin allowlist and denylist changes are rechecked without reload.

The body is fetched only when selected through `GET /api/skills/content` with
name, profile, and `expected_registration` from its catalog row. The result is
raw UTF-8 SKILL.md, not `skill_view` preprocessing; no inline shell, variable
substitution, linked file read, or model call occurs. The result repeats plugin
provenance, read-only status, owner and registration ID. `path` is empty: no
absolute install/home path is disclosed. The native UI must show it as inert
read-only text rather than an editable agent-authored skill.

The registration ID covers a random native registration identity and bounded
file stat metadata (inode, size, timestamps). Reloads and observed file changes
invalidate cached selections. Reads check the exact current entry and stat
again before returning. This is not a content-signature or defense against a
hostile filesystem owner who can race/rewrite files. Known symlink/junction
escapes and paths outside the loaded plugin root are refused.

Per-skill disabling does not prevent human inspection of that skill, allowing
informed re-enabling. The existing toggle route accepts an optional
`expected_registration` field for backwards-compatible disk skills, but requires
it for plugin-qualified names. Plugin toggles re-resolve the exact current
registration under requested profile, discovery, and config mutation locks.
They change only native skill-disabled configuration, never plugin files or
memory consent. A disabled/unloaded plugin is unavailable even if a stale row
remains in a client. Already displayed content and existing conversation prompt
text cannot be retracted.

Colon-qualified names are reserved for plugin identity in this catalog. Disk
rows claiming such names are omitted, not renamed or deleted. Skill editor
create/update/lock/uninstall paths refuse them, disk lookup cannot alias them
through frontmatter, and learning-node deletion also refuses them. Future disk
frontmatter cannot create a qualified-name collision. Resolved disk-skill aliases
inside known installed/registered plugin trees (including disabled plugins), or
ancestor directories containing them, are also refused for lookup, creation and
archiving. This closes external-directory and symlink aliases; an independent
copy outside those roots remains an ordinary editable disk skill. The guard does
not enumerate hardlinks; native skill edits replace the outside directory entry
atomically rather than writing through a shared inode. This does not remove a
user's separate authorized filesystem/terminal powers or make plugin files
immutable to their owner.

The added plugin catalog is bounded to256 registry entries and4096 UTF-8 bytes
per description; selected raw files are capped at64KiB. No large-corpus or
semantic-search performance claim is made. Existing disk-skill behavior remains
separate. Earlier r27 documentation describing a Desktop listing gap is
superseded by this patch only where the current plugin is actually loaded.
