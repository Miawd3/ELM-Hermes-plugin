# Security and disclosure · 0.2.0-experimental

- **Trust:** plugin code runs as trusted Python with your user's permissions. It is not a sandbox. Symlink
  and identity checks on the store are defense in depth, not protection against a hostile local user.
- **Data at rest:** the store, index, episode captures and review inboxes are local plaintext. Do not keep
  secrets in them. Forgetting removes ELM's copies; it is not secure erasure of backups or of text already
  sent to a model.
- **Data in flight:** ELM makes no network or model calls of its own. Text returned by its tools (or, if you
  enable background recall, prefetched text) goes into the conversation and so reaches your configured model
  provider and Hermes's logs.
- **Authority:** retrieved memory is labelled untrusted data, never instructions. Hermes's own background
  wrapper calls recalled memory "authoritative", which is why background recall is off by default.
- **Writes:** the default store mode is read-only. Proposals stay pending until an operator reviews them;
  `autonomous` notes are marked unverified agent-curated.
- **No updater, no telemetry, no daemon, no credentials held by the plugin.**

Report problems privately to the repository owner. Do not post private memory or credentials in diagnostics.
