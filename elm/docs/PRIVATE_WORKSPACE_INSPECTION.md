# Private workspace human inspection

`private.list` returns current-chat active record metadata, including pending,
approved, invalidated and sensitive record summaries, never bodies. Parameters:
`limit` 1–32 (default16), `state` all/pending/approved/invalidated, optional
`before` from `next_before`. Pages are fresh snapshots, not a frozen listing.
Unavailable cursors require refresh. Responses are capped at32KiB.

`private.get(record_id)` returns one full current-chat active record, including
sensitive text and declared sources, or refuses if its response exceeds64KiB.
It never truncates evidence. Trashed bodies are excluded. UI should invoke get
for sensitive records only after an explicit reveal action. Neither operation
approves anything or changes recall policy. Content remains untrusted data.

Both routes use native authenticated local-read context and read fences. No
caller root, scope, profile or identity is accepted. `session_id` is a transport
field whose authority is established by the host, not this service.

“Human inspection” describes the intended UI protocol, not cryptographic proof
that a human clicked. Any appropriately authenticated trusted client can invoke
these RPCs. They are not registered as model tools or provider recall. The real
Desktop contribution uses `SDK.host.request` and authenticated focused-session
context; legacy unauthenticated REST routes are not reused.
