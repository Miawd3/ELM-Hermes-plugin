# r23 important-message presentation: native contribution boundary

## Actual host integration

This candidate adds `TRANSCRIPT_IMPORTANCE_AREA = 'transcript.importance'` to the Desktop SDK. An enabled visual plugin contributes data with a synchronous `classify({role, textPrefix})` callback. The host supplies only user/assistant role and a bounded prefix of **already loaded** visible message text. No message ID, row ID, owner, session route, file path, navigation function or backend capability is supplied to that callback.

The prefix is at most 8,192 JavaScript characters. If truncated, its incomplete last line is discarded so a cut prefix cannot manufacture a complete standalone declaration. At most eight policies are consulted. The first valid exact `{label}` result wins; label is nonempty plain text at most 48 characters, with control/bidi-format characters refused. Throws, malformed objects, extra fields and asynchronous/thenable results do not become markers. Asynchronous results are not awaited; accidental rejections are handled. Arbitrary plugin JavaScript is still trusted code, not a sandbox.

Core renders the label and a fixed subtle outline on its own user/assistant message surface. The small importance component subscribes to the computed label, not a new streaming-text subscription on the heavy message root. Plugins cannot return HTML, CSS, actions, arbitrary row IDs or redirects through this contract. Importance is an author/presentation declaration, not verified priority, memory approval, work completion or permission to act.

## Native timeline markers and clicking

The existing native user-prompt history index stays unchanged. The host may decorate loaded user entries and add explicitly classified **loaded assistant** entries. It does not fetch all older assistant bodies to find markers, and cannot promise a complete session-wide important-message index. Messages outside the loaded transcript/history window have no newly inferred assistant marker until their content is loaded normally.

The native timeline owns target IDs, persisted row identities, ordering, rail buttons, accessibility text and the existing reveal mechanism. The plugin does not query DOM, dispatch navigation events, select another session or maintain its own message-ID map. A click can use normal native history reveal to make its already known target render; that is not an automatic background body scan.

Added important-marker navigation uses a strict enclosing viewport capture, never the legacy document-wide fallback. It refuses a missing/detached/hidden root or a root without its own session anchor. The captured identity includes native stored/runtime IDs and gateway activation epoch. The host checks the same root/viewport/anchor, current SessionView, current contribution set and still-present target importance after asynchronous reveal and on every animation frame. Disabling/unloading the policy or changing the owning view/connection invalidates pending important navigation. Plugins receive no public general jump API.

Legacy unannotated native user-tick behavior is retained; its older fallback helper is not used by added important targets. This distinction preserves default behavior without claiming that unrelated historical host navigation code has been comprehensively redesigned.

## Scope, toggles and evidence

The companion frontend policy defines the finite explicit marker syntax, handles code-fence/indented-code refusal and offers a default-off presentation toggle. Register/unregister lifecycle changes invalidate native subscribers; there is no backend write, model call, text copy into a second store, semantic importance inference or external action. The native timeline's existing visibility setting remains independent.

Message content still belongs to the transcript. Declaring an important marker does not authenticate a speaker or change recall/capture/project permissions. Presentation preferences are Desktop-plugin preferences, not native per-principal data grants. Hidden older assistant messages are intentionally not inspected just to draw a mark.

Qualification must distinguish pure policy tests, actual native rail/viewport tests, full asynchronous navigation tests and real browser/native acceptance. A button callback test alone is not proof of full cross-session reveal behavior. This is an additive host/Desktop patch and therefore requires rebuilding/using the corresponding Desktop source; merely installing the plugin on an older compiled Desktop does not create the SDK capability.
