---
name: rich-answers
description: Use ELM optional inline answer labels in Hermes Desktop when the user wants them.
---

Use only when the user enables ELM inline answer cards and requests structured presentation. Ordinary Markdown remains the default. Do not claim native message-bubble styling, verified completion, permission or memory status.

A short standalone card uses:

`::elm-answer{kind="question" title="One choice" text="Which option do you prefer?"}`

Kinds: `progress`, `update`, `answer`, `final`, `question`. These are model-provided labels, not proof that work succeeded. Verify work independently before claiming completion. Keep title <=100 characters and text <=1200. Do not put quotes, braces, line breaks, HTML, URLs, actions, sensitive data or executable commands in attributes. Use ordinary Markdown outside the card for longer content and links. If cards are disabled the source remains readable text. Never request enabling memory or changing permissions merely to render a card.
