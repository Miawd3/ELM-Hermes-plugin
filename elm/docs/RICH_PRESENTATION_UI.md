# r22 bounded native rich presentation

## Available now

The active single-file ELM Desktop plugin registers the real public `transcript.directives` contribution `elm-answer` when the pinned SDK exposes it. It never rewrites the transcript DOM or replaces ordinary message bubbles. It also adds a **Rich answer reading** settings page with a formatting toggle and Compact/Comfortable spacing. The ELM plugin remains defaultEnabled=false; a presentation preference cannot enable the plugin itself.

Author a standalone directive or place one in an ordinary assistant message:

```text
::elm-answer{category="answer" title="A clear plan" text="Start with the door."}
```

`category` is progress, answer, question or final; default answer. Labels are Progress, Answer, Question and Final answer, explicitly **self-declared presentation**, not native final events, verified completion, permission or approval. Optional title has at most 180 Unicode characters; optional plain text at most 1200. Parsed attributes are whitelisted and bounded to 2048 serialized characters in addition to the native parser's 2048-character brace-body bound. Use normal Markdown outside the directive for larger content, multiline content or awkward quoted/braced text. Nested directives inside text are inert.

Inline cards use the recovered strict reader validation and native React component. Invalid attributes fall back to the original directive text. While streaming or when formatting is disabled, the complete bounded title/text remains visible as plain text. No document ID, file path, URL fetch, memory read, model request or backend publish is needed. No paid call is performed.

## Local preferences and failure handling

`ctx.storage` holds only `rich-reading.v1` `{enabled,density}` under the ELM desktop plugin. This is local display preference storage shared across profiles, not an authenticated principal's memory store. Answer bodies are never persisted by this renderer. Missing/throwing storage uses temporary in-memory preferences with an explicit notice; optional reading settings cannot abort existing private/project memory registration. User changes are applied locally even when saving fails. Disposal removes preference subscriptions.

## Recovered reader boundaries

Strict normalization, safe URL filtering and Markdown export were adapted from the recovered MIT Rich Answers 0.1.1 source; the original license is included at `docs/licenses/RICH_ANSWERS_MIT.txt`. The fuller reader supports section/detail layout, visible notes, source inspection, text view and full-copy behavior. It uses native SDK Streamdown with skipHtml, disabled controls, inert task inputs and no automatic image loads; external HTTP(S) source links open only after a user click via the host OS API. Copy uses the real `ctx.os.writeClipboard` capability.

The richer full-document component is exercised in **synthetic component previews**, not claimed as a restored saved-document publishing workflow. This checkpoint does not expose a backend rich-answer publication tool, global answer store, authenticated rich-document fetch route, tool-media renderer or 100-kilobyte document hidden inside directive attributes. Native tool turns currently lack the narrow presentation publication authority that workflow would require. No existing authority was weakened to recreate it.

## Evidence and limits

Actual pinned host parser/materializer tests cover author syntax and the native contribution contract. Controller/registration tests cover bounds, four-category validation, storage failures and no automatic RPC. Real React SSR covers four categories, toggle-off text preservation, malicious-text escaping, no automatic links/images/clipboard and separately labeled full-reader fixture behavior. `ui-tests/rich-answer-preview.html` is real-component HTML with synthetic SDK/theme/data, **not a native installed screenshot**. No browser sandbox bypass or production/live installation acceptance claim.

This restores a bounded opt-in presentation slice, not native rich-answer bubbles across all messages, highlight/jump markers, chat folders, auto-updates or complete recovered backend functionality.
