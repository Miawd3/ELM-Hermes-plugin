# Reference recipe from long-term memory (r30)

In **Approved memory wiki**, explicitly select the private or consented-project scope, refresh the index, and open an approved record. The **Reference draft from memory** panel uses that single selected record and the exact authorized wiki snapshot. The backend supports up to four records; this first UI intentionally offers one at a time.

Enter a title and click **Preview reference draft**. **Include declared citation evidence** is a separate checkbox, off by default. Previewing evidence may reveal sensitive quotes, but does not fetch full captured sources, open URLs, or call a model.

Review the complete deterministic text, its digest, and sensitivity warning. **Confirm saving recipe** is a separate action. This is a source-linked reference document, not AI-generated expertise, a validated reusable skill, or a native installed skill. Nothing is exported, sent to a model, installed, or automatically approved.

## What saving retains

Saving retains a creator-chat-scoped recipe: title, selected IDs, source/version pins, and evidence selection. It does **not** retain the generated Markdown body. Recipes are retained indefinitely; this interface offers no purge control. Titles and identifiers may themselves be sensitive metadata.

**Refresh saved recipes** lists recipe metadata explicitly. Selecting one requests regeneration. The backend regenerates only when the exact current authorized approved source pins still match; otherwise the panel reports unavailable and shows no retained body. Saved recipe selection does not bypass current project consent or private ownership.

A lost save response clears the preview token and marks the outcome uncertain. The preview includes a predetermined recipe ID; the last attempted ID remains visible after an uncertain save. Match that exact ID in the refreshed recipe list, not merely a similar title. Refresh the saved recipe list to reconcile; the UI does not replay a save. Changing the wiki scope, snapshot, selected record, owner, connection, or activation invalidates the displayed preview and action intent. Already displayed text is point-in-time inspection, not a continuous server revocation mechanism.

## Verification

Controller tests cover explicit preview/save separation, evidence opt-in, UTF-8 title limits, stale scope, late responses, and uncertain saves. Actual React component SSR uses synthetic adapter data and inert text, not a native installed-application screenshot. The actual settings contribution reuses the Wiki page. Backend tests separately establish recipe ownership and source pin checks.
