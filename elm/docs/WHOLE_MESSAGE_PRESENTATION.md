# r40 whole-assistant-message types

This slice is actual native message-root integration, not just an inline card mockup. `AssistantMessageBody` mounts the small `MessagePresentation` selector leaf directly inside `MessagePrimitive.Root[data-slot=aui_assistant-message-root]`. The leaf's validated attributes select host-owned finite CSS for that message only. Response groups, Markdown source, actions, message statuses and navigation are untouched. Important-message highlighting keeps its external outline alongside the new inset side/outline border.

## Controls and use

ELM Settings → Message bubble types. Master is off by default. Each of Progress, Update, Answer, Final and Question has an enable switch, inert label (24 characters), label visibility, six fixed accents, none/subtle background and none/side/outline border. Turning master off or unloading the plugin unregisters the policy. None background + none border + hidden label adds no padding/rounding. Reset disables the feature and restores defaults.

The local storage namespace is `hermes.plugin.elm.message-presentation.v1`, shared across Desktop profiles on this installation, not a private per-profile setting. No message text is stored by these settings. Failure to persist is displayed as session-only. No backend route or model request is added. Unsupported hosts show an unavailable explanation rather than an imitation.

An author may explicitly emit:

```
::elm-message{type="question"}
What should happen next?
```

The marker must start the message or follow a blank line, occupy its own line outside fenced/indented/quoted examples, and fit inside the first 8192 characters. During streaming the line needs a newline before it is recognized. This is a bounded grammar, not a full CommonMark AST classifier. The first eligible recognized type wins, and a disabled type does not fall through to a later type. It does not make the model emit markers automatically. “Final” is author-declared styling, never verification of completion or correctness.

The marker remains visible in ordinary Markdown and copy output. No generic directive renderer is used to hide it, since the generic parser accepts inline contexts that the whole-message classifier intentionally rejects. This is a functional presentation foundation, not a polished hidden metadata channel.

## Text and safety boundaries

Native visible parts render separately through `TimelineMarkdownText`/`MarkdownText`, not through the concatenating copy helper. To avoid manufacturing syntax, the selector preserves whitespace, joins text only when boundaries contain actual newlines, and abstains on ambiguous fragment boundaries or mixed tool/reasoning content. This intentionally leaves some otherwise useful messages unstyled. Hidden reasoning/tool text is not inspected. No arbitrary CSS, HTML, URL, status mutation, event callback, IDs or navigation authority crosses the classifier contract. Invalid/throwing/asynchronous policies are ignored. Trusted plugins still have the native app's ordinary authority; this is not a malicious-plugin sandbox.

## Evidence

Initial native actual-Thread qualification: 4 new cases plus 9 existing inter-agent-collapse and render-invalidation regressions passed (13 total, 27.13 s). It covers actual direct-child native roots, different types for different messages in a response, hidden labels, importance coexistence, source/content retention, default/reset, streaming bounds and native validation. Controller + actual React server settings rendering: 6 passed. Independent review/qualification may add more evidence in the final report.

The theme accent variable exists in native styles.css. Text inherits the native theme's foreground; only a low-alpha background and accent border change. Actual Electron light/dark screenshots, OS interaction and visual contrast acceptance were not performed here. jsdom/SSR assertions are not a claim of installed visual acceptance.

## Fresh full dynamic requalification

All `ui-tests/*.test.mjs`: **172 passed, zero failures** (1.542 seconds), including the new six focused controller/settings SSR cases. Do not add those six again. All **16 existing actual-component SSR bundles** were rebuilt from the rc40 plugin source with pinned esbuild/React and executed successfully (`full-ssr-r40.log`; reproduction `release-tests/rebuild-ssr-r40.cjs`). These are synthetic adapters, not native screenshots.

The first full Node run found two outdated fixture expectations: the exact settings-page list and disposer count did not include the new message-bubble-types registration. That initial 170/172 log is retained as `full-dynamic-ui-r40-outdated-fixture.log`; only those expected values were updated, then the full 172 reran successfully. Production code did not change during requalification. SDK missing-export warnings in SSR builds describe intentionally minimal synthetic adapters and are not actual host build qualification.
