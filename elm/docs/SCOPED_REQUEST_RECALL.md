# Opt-in private request-scoped recall (r13)

This is a fresh scoped mode, not activation of the old ELM workspace/legacy
provider. The plugin entrypoint now registers `ScopedMemoryProvider`; it does
not read, migrate or fall back to retained legacy files. Hermes's normal built-in
provider and default selection are unchanged. No project records are automatically
injected, regardless of project consent. Existing explicit inspection RPCs remain
separate.

## Exact supported setup

Enabling the checkbox alone does not guarantee an injection. This slice requires:

1. The patched Hermes host shipping the `request_recall` capability, admitted-turn
   ownership binding and request-only build hook. Stock/unpatched hosts cannot
   supply it. The provider reports unavailable and does not fall back to legacy.
2. Explicit native selection of the **ELM** memory provider and in-process plugin
   execution. The recall settings UI does not select/activate a provider for you.
3. An authenticated, claimed, local primary session turn on the supported native
   admission path. Session/profile strings from provider initialization are not
   authorization. Standalone legacy contexts, managed worker subprocesses and
   plugin-host subprocesses cannot use this authority.
4. `api_mode == "chat_completions"`, text-only request content, a known positive
   native context window and an explicitly configured positive output `max_tokens`
   reserve. The native default can leave the output cap unset; in that case this
   lane omits recall. It does not invent or silently change output/billing limits.
5. Explicit private-store setup, current-chat opt-in, eligible records and enough
   conservative request headroom for at least one complete record.

MoA/advisor, auxiliary/side-question, subagent, cron, background/flush,
persistence-disabled, interrupted, unsupported multimodal and non-Chat-Completions
paths omit this lane. An unavailable/archived selected native project may block
private fences too: recall is already refused, and changing stored settings
requires explicitly unbinding that unavailable project first. No fence bypass is
introduced. `host_supported` describes host capability, not effective provider
selection or proof that a particular turn injected data.

## Settings RPC

- `private.recall_settings.status {}` returns `enabled`, `revision`, `max_records`,
  `max_utf8_bytes`, `scope:"private_chat"`, `delivery:"request_only"`,
  `host_supported` and a cost/revocation notice. Missing settings mean disabled,
  four records and an 8,192-byte packet limit.
- `private.recall_settings.preview {enabled,max_records?,max_utf8_bytes?}` accepts
  a strict boolean, 1–8 records and 512–16,384 UTF-8 bytes. It returns proposed
  `settings`, a cryptographic one-use preview token, expiry and notice. Enabling
  requires an already initialized private store; preview creates nothing.
- `private.recall_settings.apply {preview_token,confirm:true}` returns status.
  Tokens expire after 300 seconds, are capped at 64, and pin exact host ownership,
  immutable store identity and prior settings revision. They are consumed before
  a single publication attempt. Unload clears unused tokens. A failed/uncertain
  write requires status reconciliation and new review, never automatic replay.

Settings are per canonical private chat, in a separately validated additive
`private_recall` manifest extension. At most 512 settings entries are retained;
the existing 4 MiB full-manifest limit includes them. A default-disabled absent
store does not need to be created to report or confirm that it is disabled.

## Selection and packet budget

Selection is deterministic newest-first among current-chat approved eligible
records, not query-ranked or semantic search. Pending/invalidated, sensitive,
user-inferred and dependency-ineligible records are withheld by the existing
recall policy. Withdrawn captured sources are also excluded. Each fresh read
revalidates native ownership, source integrity and current settings under the
host and store fences. There is no packet cache or background prefetch.

The packet contains full selected record text and source provenance, record IDs
and revisions, with an explicit `untrusted_memory_data` label. It does not assert
truth, authenticated authorship or instruction authority. JSON preserves structure;
it does not make malicious content harmless. Records that do not fit are omitted,
not truncated. The UTF-8 budget counts the entire serialized packet, including
its labels and provenance, not just record bodies. It does not mean tokens, total
HTTP bytes, a dollar limit or a measured provider-token count.

The host separately applies a conservative text-byte/headroom reserve using the
existing messages, tools, packet, configured output cap and framing allowance
against the known window. Missing/insufficient headroom omits recall. This is not
an exact tokenizer calculation or a universal guarantee of request fit. Request
hook character and rough-token metadata includes an estimate of the added packet.
There are no retrieval model/API calls, but extra input tokens, retries and changed
prompt-cache prefixes can increase the cost of an already paid chat.

## Native request and revocation boundary

The host derives a read-only principal from the committed claimed admission, not
from provider/caller identity hints. It checks the exact session, authority epoch,
execution generation, serving state and cancellation latches. The context expires
when the admitted execution exits; copied/background contexts cannot revive it.
The provider resolves the canonical owner again on every supported request and
checks its initialized profile without treating profile identity as permission.

The dedicated hook runs in `agent.turn_api_request.build_api_request`, once per
native main-request attempt, not in generic auxiliary payload construction.
It appends one user-role data packet to a deep request-only copy. The returned
retry baseline remains pristine. It does not modify canonical transcript/history,
`api_content`, static system prompts, prefill data or tools. Normal provider
`prefetch`, queued prefetch, sync/capture and model tools remain empty; this lane
never uses the legacy authoritative-memory wrapper or durable replay sidecars.

Disable, source withdrawal, invalidation or scope changes are rechecked on the
next native request build, including tool iterations and native retries. Locks
are not held across network I/O. Authorization is a snapshot taken during building
that logical request: later changes cannot retract a packet already built or
sent. SDK-internal retries of an already dispatched request may reuse those bytes.
Host middleware, request hooks, debug dumps, telemetry and the remote provider may
see or retain a sent payload. Generated assistant text can also repeat remembered
facts into normal history. This feature neither purges those copies nor guarantees
that previously disclosed information disappears from later model context.

The guarantee is narrower: this lane does not persist its packet as a replay
sidecar or reuse a stale packet on a later native build. No paid/live model call
is needed to test its construction, filtering, authority and retry-baseline rules.
