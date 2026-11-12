# r22 rich-answer presentation: backend boundary and deferred work

## Implemented scope decision

This milestone uses the existing public Desktop transcript-directive contribution area for explicit, bounded **presentation labels** alongside ordinary native Markdown. No new Python backend, model-facing publish tool, host permission, source store, authenticated document endpoint, prompt section or automatic send is introduced. The original message text remains the transcript source; display preferences are presentation settings, not memory permissions.

The visual categories (for example progress, answer, question and final) are untrusted author-supplied labels. They do not prove that work completed, that a question requires an action, that content was approved, or that a message is a native finalization event. They must never influence memory admission, tool authorization, provider routing or source trust. Malformed/unsupported content must remain understandable ordinary text rather than grant rendering power.

Exact frontend syntax, controls and qualification belong to the companion UI contract. This is a partial restoration of reading/category affordances, **not the recovered plugin's full persistent structured-answer workflow**.

## Actual native surfaces inspected

The pinned official host already exposes:

- `apps/desktop/src/lib/transcript-directives.ts`: `TRANSCRIPT_DIRECTIVE_AREA`, untrusted attribute strings, original source, streaming flag and transcript-owned sessionId. `DIRECTIVE_BODY_MAX` is 2,048 characters. Unknown names/malformed directives remain text. A contribution renders a leaf, not an arbitrary whole-message rewrite.
- `apps/desktop/src/components/assistant-ui/transcript-directive.tsx`: registry-backed rendering with a contribution error boundary and the owning session context. This does not itself authorize backend file reads.
- `apps/desktop/src/lib/tool-media-renderers.ts`: a separate tool-media extension surface. A registered renderer does not grant a tool permission or make a returned path/identifier authoritative.
- The Desktop SDK's settings/storage/contribution APIs: appropriate for bounded visual preferences and lifecycle cleanup, not for inventing native actor identity.

No additional host patch is necessary for the chosen frontend-only scope. These existing interfaces do not provide a general public “rewrite every assistant message with trusted categories” hook. The candidate must not patch DOM text, reinterpret arbitrary source text as HTML, impersonate native role metadata, or mutate already-created session prompts to make that happen.

## Why the recovered backend is not activated

The recovered Rich Answers source registered `rich_answer_publish`, wrote content-addressed JSON/Markdown to a **profile-global** store, and exposed dashboard `/answers/{identifier}` reads. A content hash proves neither principal ownership nor current-chat access. Dashboard/profile authentication is not the stronger principal/canonical-chat memory boundary established by this candidate. Reusing those reads would silently reintroduce cross-chat or cross-principal access assumptions.

The old registration also added a desktop system-prompt section and a model tool. The current scoped ELM provider deliberately registers no such tools or legacy draft fallback. Restoring those behaviors without explicit configuration and native qualification would change agent behavior and prompt/tool surface, not merely improve presentation.

On the current host, an admitted model turn has a read-only memory scope for fresh request recall. `publish_memory` correctly refuses writes from that scope. The capture-only finalization permit is not a general presentation grant and must not be repurposed. A new rich-document tool cannot safely bypass this by writing from a read callback, using a caller session ID, caching prior authority or adopting the old profile-global path.

Therefore there is no new publish/get API in r22, no old dashboard route registration, no automatic rich document persistence and no claim that standalone recovered fixtures prove current scoped authorization. Old source is reference material only. A small inline presentation marker can fit the native directive contract; a 100 KiB recovered document cannot be smuggled through a 2,048-character leaf or fetched by an unauthenticated hash lookup.

## Future design only: scoped structured documents

If persistent structured answers are separately requested, a narrow design should establish all of the following before activation:

1. Explicit user opt-in and a dedicated presentation-only native capability bound to the currently admitted actor/profile/canonical chat and lifetime. Do not broaden the model turn's generic memory-write authority.
2. A principal/chat-qualified immutable document store or equally scoped native attachment facility, with bounded schema, storage and response sizes; source/category metadata remain declared and unverified.
3. Native owner-fenced publication and read operations, including current epoch/lineage checks, no caller-selected root/profile/owner, no process-global “current chat” fallback and no cached authorization.
4. A rendering reference that is an identifier, not permission. Every retrieval must independently authorize the transcript's actual owner context; scope changes and stale async responses must fail closed.
5. Complete inert Markdown fallback, no arbitrary HTML/JavaScript, source links opened only by explicit user action, and no forced external fetch or model call.
6. Explicit outcome/recovery behavior for publication failures and bounded retention, with no hidden overwrite/purge. The read surface must not make a known hash a cross-user document oracle.
7. Tests through the real native tool/turn and Desktop contribution paths, including disabled mode, profile/chat isolation, unload/reload, stale scope, malicious text and unsupported hosts. Synthetic rendering alone is not full native browser acceptance or real-model tool-choice evidence.

This list is an architectural proposal, not a newly available capability or permission to modify a live host. The frontend-only restoration preserves normal defaults and existing memory/security behavior while this larger contract remains unimplemented.
