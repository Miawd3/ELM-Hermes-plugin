"""Model-neutral token accounting used by ELM retrieval surfaces."""
from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """Return ELM's legacy characters/4 token estimate (not an upper bound).

    This is deliberately not a tokenizer for any one model. It can undercount substantially, especially Unicode and escaped JSON.
    Measured provider budgeting does not use this estimate for admission.
    """

    return max(1, (len(text) + 3) // 4)
