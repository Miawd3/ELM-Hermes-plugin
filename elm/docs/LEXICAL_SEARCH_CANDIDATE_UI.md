# Optional user-invoked lexical search UI (r37)

After independent held-out review and explicit integration approval, this checkpoint registers **Scoped lexical search** in the native plugin settings surface and disposes its controller on unload. The ELM plugin itself remains default-disabled. This is an optional human-invoked lookup, not automatic model memory, an answerer, or a default recall change.

The isolated candidate offers explicit private/project selection and a typed query. It sends no query until Search is clicked, never reads a global corpus, and makes no model calls. Project selection does not grant access; the backend requires current consent and native authority. Query editing, scope changes and owner/socket changes clear old results and reject late responses.

The authenticated backend returns a canonical JSON string with complete selected native records and a reference limit of 700 `o200k_base` tokens. The UI renders that exact string inertly rather than reconstructing a lighter packet. This budget is for the entire returned memory JSON, not the full model prompt, provider framing, billing or currency. The UI does not claim to have independently counted provider tokens.

Distinct states are shown: literal matches, partial admission, matching whole evidence too large for the budget, lexical no-match, and unavailable/rejected. A missing tokenizer is not an empty successful search. Literal no-match is not proof that an answer is absent. No record text or declared citations are silently truncated. Sensitive and otherwise ineligible records are excluded. Dependency metadata may be present without all supporting dependency bodies being delivered, so a result is not a complete semantic-support guarantee.

Tests exercise the real candidate controller and actual React SSR with synthetic SDK data. They do not establish retrieval improvement, installed native UI acceptance, corpus-scale search performance, answer quality or competition results. Registration adds this explicit lookup page only; automatic recall and model behavior are unchanged.

Literal matches may not answer the question: there is no semantic abstention, and distractors can be returned for questions with no answer. Large indivisible evidence and cross-language matching remain weak. No benchmark percentage is hardcoded into the UI. The first query may incur tokenizer loading cost; setup requires optional pinned tiktoken 0.14.0 plus the matching official o200k vocabulary configured locally as search_tokenizer_vocab, followed by normal plugin reload. There is no hidden installer or fallback estimator.

## r38 readability only, prior to experimental-mode gate

The existing literal mode now presents decoded record title and complete text as inert cards, with expandable declared citations and the unchanged exact returned JSON packet. This is a display of data already returned, not a lighter packet, additional source fetch, summarization, truncation or model input change. Titles, text and citation strings cannot create HTML, remote images, scripts or automatic links. Experimental search modes remain withheld until their independent evaluation and explicit integration decision.

### Rejected experimental mode

The independently evaluated experimental mode failed its fresh held-out utility gate and was never exposed in the registered UI. Its controller/page branches were removed after preserving the full experimental source and evidence outside the active feature. The active page and request contract remain literal-only; only the inert readability improvements above are retained. See the checkpoint's `experiments/coverage_idf_v1` evidence index, not the active feature, for the rejected experiment.
