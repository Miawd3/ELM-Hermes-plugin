> Historical integration narrative, retained for provenance. Partial patch references and publication status below are superseded by the complete [integration/host.patch](../../integration/host.patch), [current installation guide](CANDIDATE_INSTALL.md) and [release status](../../RELEASE_STATUS.md). Do not apply any partial patches separately.

# Provider-envelope compatibility follow-up

Official references checked 2026-11-12:
- https://developers.openai.com/api/reference/resources/chat
- https://developers.openai.com/api/reference/resources/completions
- https://api-docs.deepseek.com/api/create-chat-completion/

The documented text-completion shape permits null logprobs, service tiers, usage breakdowns and inactive optional message fields. DeepSeek also reports cache-hit/cache-miss counts. The parser now validates those narrowly rather than rejecting otherwise valid text answers. Optional numeric breakdowns are bounded and checked against totals; unknown fields remain rejected.

The change is deliberately NOT a universal OpenAI-compatible parser: one non-streamed text choice, exact enrolled model identity, stop finish, no tools, no refusal, no reasoning body, 8 KiB response cap and 512 requested output tokens remain. Duplicate JSON keys and nonfinite numbers fail; malformed UTF-8 text fails. Metadata is only null/empty; moderation output remains unsupported. A provider returning an alias snapshot different from the enrolled model still fails; no wildcard or silent identity change was introduced. Empty-string reasoning_content also fails.

## Evidence
- 56 parser/credential-review tests passed (15 existing warnings).
- Native TLS fixtures send representative synthetic OpenAI-shaped and DeepSeek-shaped metadata through actual organizer RPC, then accept a proposal only into pending sensitive memory.
- Independent reviewer found no unsafe weakening; additional adversarial evidence is retained separately.
- Request-body compatibility remains unresolved for models not accepting temperature=0/max_tokens. DeepSeek's currently documented thinking defaults also need explicit request profile support. This work therefore does not establish readiness for all models/providers.

## Release decision
Keep production _TRANSPORT_FACTORY=None. No live requests, real credentials, costs, billed-token results, real-provider certification or native desktop screenshot claimed. UI consent and transport foundation remain useful tested progress; automatic organizer/search-agent completion is still unproven.

## Integration delta
New host overlay hermes_cli/plugin_llm_credentials.py plus parser-compatibility.patch (against r38 host overlay). This is additive to restoration.patch from the previous partial checkpoint. Regenerate host identities and manifests; rerun native suite after integration. Do not use historical blocker tests claiming that logprobs/token-details/service_tier still fail: updated test_provider_compatibility_blockers.py now verifies they succeed while unpinned aliases fail.
