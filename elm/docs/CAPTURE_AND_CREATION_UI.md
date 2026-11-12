# Explicit record creation and private source capture

The existing opt-in private/project review pages now include **Add a pending record manually**. A separate private-only source panel supports exact pasted snapshots and reviewed excerpts. Nothing here runs an LLM, fetches a URL, reads a user file automatically, approves a record automatically or enables provider injection.

## Manual pending records

After refreshing the intended scope, expand the creation form and enter title, text, a declared source reference and optional quote. Domain, coherent evidence kind/basis, topic and sensitive status are explicit. A manually entered reference/quote is not independently verified; a URL is displayed as a label and never fetched.

**Review new pending record** freezes the exact form payload. The confirmation shows the complete authored fields; **Confirm create** writes a pending record only. A separate review/approval remains necessary. Byte limits are enforced by the backend. Sensitive and inferred-user recall exclusions remain unchanged.

The private form writes only the current private chat. The project form explicitly warns that it writes into the consented same-principal project pool. It requires effective policy-2 consent and passes the consent revision captured with the displayed project status. A different binding/context or revoke/regrant invalidates the staged attempt. Older rendered form handlers cannot silently adopt a newly refreshed project context.

## Exact private snapshots

1. In the private page, open **Capture pasted source text**.
2. Enter a title and the exact text, up to 64 KiB UTF-8. Optional reference and author are declarations, not verification.
3. The sensitive checkbox starts **on**. This is a user declaration, not an automated detector. Extracted records inherit it; linked-source protections cannot be bypassed merely by changing a record flag.
4. **Preview source snapshot** asks the backend to hash the exact supplied text. The confirmation displays the whole raw text, reference/author, sensitivity, SHA-256 and byte/code-point counts.
5. Explicitly confirm capture. The resulting source ID is shown. **Refresh source snapshots** can rediscover a capture after a lost response; no automatic repeat occurs.

The source list contains metadata. **Reveal source snapshot** explicitly retrieves its full retained text for human inspection. Source data and any instructions embedded in it are rendered as inert text, not executed. Source capture does not extract or approve any memory record and does not share it with a project.

## Exact excerpts, without browser offsets

From a revealed active source, paste the exact quote. It is not trimmed or normalized. An occurrence number is optional only for a unique match; repeated matches require an explicit one-based occurrence. The browser sends the quote and optional occurrence, never JavaScript UTF-16 character offsets.

The backend preview reports the exact source ID/revision/hash, quote, occurrence and Unicode-code-point start/end. The page shows that provenance and the pending candidate, including inherited sensitivity. **Confirm excerpt** creates only the reviewed pending private record. The hash plus exact quote demonstrates captured-text identity, not factual truth, verified authorship or permission to trust instructions within it.

If the source was changed/withdrawn, a preview is stale, a quote is ambiguous or ownership changes, the operation refuses. There is no automatic fuzzy matching, paraphrasing, model extraction or fallback occurrence.

## Withdrawal and retention

**Review source withdrawal** shows the exact source title, ID, revision and hash. Confirmation withdraws future extraction and invalidates linked evidence according to the backend lifecycle. Snapshot bytes remain retained. This is not permanent deletion or privacy erasure; exports, transcripts and backups remain separate retention surfaces. Refresh records and snapshots to inspect the result.

## Safety and evidence

Form state is keyed to the rendered owner; project forms additionally bind the reviewed project context. Staged content is copied, not reread from mutable form fields at confirmation. Source selection and excerpt previews bind the exact source ID/revision/hash. Old confirmations, context changes and late source-read replies cannot populate or mutate another selected context. Failed writes are treated as uncertain and are never replayed automatically.

Forty controller tests pass, including fifteen added creation/capture cases. Real React SSR renders the current component with synthetic SDK/state, checks private-only source controls, sensitive-on defaults, exact excerpt provenance, token nondisclosure, inert source strings and stale-context withholding. Source preview fixture counts and hashes are computed from its synthetic text, not represented as a native capture run.

The source/capture HTML previews are real-component server renders with approximate controls/theme. They are not installed Hermes screenshots or browser acceptance tests. The prior Chromium sandbox/socket restriction was not bypassed or retried in this slice. No paid API calls, live installation, public publication or automatic project migration occurred.

## Capacity and scope qualifications
Project creation rejects reserved `elm-snapshot-v1:` private-capture references before confirmation and again on the backend. No private source is copied or treated as project authority. A declared external reference remains an unverified label, not a fetched resource.

Private source storage is bounded at 64 snapshots including withdrawn entries, within the complete 4 MiB manifest budget. Retained source bytes are not reclaimed by withdrawal. Capacity or storage errors can refuse an operation; a failed/uncertain withdrawal is not reported as successful, and refreshing may show the source still active. Inspect current state rather than retrying blindly.
