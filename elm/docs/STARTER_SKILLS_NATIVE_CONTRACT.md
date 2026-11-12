# Native starter skills

ELM supplies six original Apache-2.0 text-only procedures: source research,
documentation lookup, debugging recovery, verification, delegation, and creative
continuity. They are public instructional content, not captured user data or
private memory. Existing ELM LICENSE and NOTICE apply. No third-party skill
corpus has been copied or installed.

The plugin registers `elm:<name>` through Hermes `ctx.register_general_skill`, a thin native `register_skill` wrapper. Native
skill discovery offers all six short names/descriptions; it does not load their
full instructions. Use native `skill_view` or the native skill slash command to
load a selected procedure. This is progressive disclosure of a small pack, not
semantic search, automatic routing, or evidence of scaling to hundreds of skills.
There is no new model tool, selection model, embedding service, network request,
or paid call. Normal model requests may include metadata and selected content,
with their usual input-token costs.

The accompanying host patch adds this explicit general-plugin lifetime capability.
A stock host without it skips the pack rather than attaching it to memory-provider
activation. General discovery owns these registrations; selecting a different
memory provider does not retract them.

Use exact qualified names in the intended profile’s existing skills.disabled configuration, preserving other entries. r29 additionally exposes loaded plugin skills through the native Desktop catalog with read-only source ownership and registration-pinned reads/toggles. The interactive CLI disk selector is still not claimed to expose the pack; see STARTER_SKILLS_DESKTOP_GUIDE.md. Native skill reads check disabled state;
plugin unload removes owned registrations. Already-loaded text and cached prompt
metadata cannot be retracted from existing conversations. Start a new session
after changing installed skill content or desired prompt composition. No
mid-conversation system-prompt rewrite is performed.

Registration accepts only the six fixed packaged paths, validates every file
before registration, and bounds each UTF-8 file to 16 KiB and description to 240
characters. Frontmatter has exactly name, description, and license. Known
symlink/junction escapes and executable preprocessing tokens are rejected. This
is a packaged-content integrity guard, not a sandbox against hostile local file
replacement or arbitrary plugin Python. No scripts or remote assets are needed.
Skill instructions do not authorize file changes, network use, delegation,
installation, private-memory access, or external communication. Existing host
permissions and the user's task govern each such action.

## Wiki boundary

No wiki directory, legacy ELM store, session history, or external skill catalog
is scanned. Native `skills_list` itself may discover plugins and create its
skills directory; this pack does not call it as a supposedly pure read.
Hermes's optional `llm-wiki` and `code-wiki` procedures are distinct workflows,
not an authenticated ELM wiki-reader API. Catalog wiki providers also have their
own storage, network and licensing boundaries. They are not installed, enabled,
or used as fallback here. Wiki reading remains a separate future slice requiring
an explicit source selection and existing read authorization.
