# r23 explicit important-message display and native timeline markers

## Authoring and settings

ELM adds **Important messages** to Desktop plugin settings. Highlighting is off by default. Enable “Highlight marked messages and show clickable timeline markers” to register a bounded classification policy. Disabling unregisters the policy so native contribution subscribers remove the highlighting and extra assistant markers. It does not delete messages, change memory approval or override the ELM plugin's own disabled state.

Use an explicit standalone marker outside fenced/indented code:

```text
::elm-important{kind="decision"}
```

Kinds: important, decision, question, warning, result. The first recognized standalone marker within the bounded prefix wins. Classification does not infer importance from keywords or content. Quoted, inline-code, indented and fenced examples are not classified. The native host supplies at most 8192 characters of role/textPrefix, clipping long bodies at a complete line; the plugin additionally refuses potentially incomplete final lines. A declaration after the bounded prefix is not considered.

A matching native transcript leaf renders a small inert “Decision · marked by author, not verified” label. That label's display is independent of timeline highlighting, has no link/navigation action and does not claim verified completion or priority. Invalid attributes remain literal escaped text. Ordinary messages are not rewritten.

## Actual native integration

The patched public SDK exports TRANSCRIPT_IMPORTANCE_AREA = transcript.importance. Its pure classify input is only a frozen `{role,textPrefix}`; the plugin returns `{label}` or null. There are no message IDs, session/profile identifiers, destinations, navigation callbacks or raw CSS supplied by ELM. The native host validates output, fixes colors/styles and owns actual message identity, ordering, viewport scope and click behavior.

Native message components render the importance badge/outline. Existing native user ticks are decorated; explicitly marked **loaded assistant** messages receive native rail ticks. The native rail click uses current-pane/session/profile ownership checks, not a plugin-generated ID or DOM event. No assistant-history bodies are fetched to manufacture a complete index. Unloaded/older assistant messages are not advertised as indexed. Existing native user-history behavior remains host-owned.

On hosts without the new native area, the settings toggle is disabled with an explicit unsupported notice; no timeline/navigation is emulated. The inert declaration leaf can still render where the older transcript-directive surface exists.

## Preference and privacy boundary

Only `importance.v1` `{enabled}` is stored in ELM's local Desktop plugin storage, shared across profiles. Message bodies, marker IDs and classification results are not persisted by this plugin. Storage exceptions fall back to in-memory/off defaults and visible save warnings. Registration/removal and subscriptions are disposed with the plugin. No backend/model request or paid API call is made.

## Evidence

Controller tests cover finite explicit markers, code-fence/indent handling, prefix bounds, default-off settings, registration/unregistration, unavailable-host fallback and storage failure. Independent tests exercise the actual native classifier/rail click and native directive parser, rather than a mock navigation API. Actual React settings SSR produces `important-messages-preview.html`, clearly labeled synthetic component/label examples, **not a fake functional timeline or native installed screenshot**. Native interactive visual acceptance remains unverified; no browser sandbox bypass, live installation or public publication occurred.

This is explicit author-marked highlighting, not an AI heuristic, arbitrary manual click-to-bookmark editor, durable importance database or whole-history indexing feature.
