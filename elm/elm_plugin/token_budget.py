"""Offline ordinary-text counts for explicitly named, hash-pinned encodings.

Never guesses a model, downloads an asset, or changes Python's import paths.
"""
from __future__ import annotations

import base64
from functools import lru_cache
import hashlib
from pathlib import Path

from .engine import ElmError

TOKENIZER_VERSION = '0.14.0'
# Definitions from tiktoken 0.14.0, tiktoken_ext/openai_public.py (MIT).
ENCODINGS = {
    'cl100k_base': (
        '223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7',
        r"'(?i:[sdmt]|ll|ve|re)|[^\r\n\p{L}\p{N}]?+\p{L}++|\p{N}{1,3}+| ?[^\s\p{L}\p{N}]++[\r\n]*+|\s++$|\s*[\r\n]|\s+(?!\S)|\s",
    ),
    'o200k_base': (
        '446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d',
        '|'.join([
            r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*[\p{Ll}\p{Lm}\p{Lo}\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
            r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+[\p{Ll}\p{Lm}\p{Lo}\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
            r'\p{N}{1,3}', r' ?[^\s\p{L}\p{N}]+[\r\n/]*', r'\s*[\r\n]+', r'\s+(?!\S)', r'\s+',
        ]),
    ),
}
BUDGET_MODES = ('measured', 'legacy-estimate')


def validate_settings(mode, name, vocab):
    if mode not in BUDGET_MODES:
        raise ElmError('invalid_budget_mode', 'Select measured or legacy-estimate budgeting')
    if mode == 'measured':
        if not isinstance(name, str) or name not in ENCODINGS or not isinstance(vocab, str) or not Path(vocab).is_absolute():
            raise ElmError('tokenizer_not_configured',
                           'Measured budgeting requires tokenizer cl100k_base or o200k_base and an absolute tokenizer_vocab path; no model is inferred')
    elif name is not None or vocab is not None:
        raise ElmError('unused_tokenizer', 'Tokenizer settings require measured budgeting')


@lru_cache(maxsize=4)
def _encoding(name, digest, data):
    try:
        import tiktoken
        if tiktoken.__version__ != TOKENIZER_VERSION:
            raise ImportError('unsupported tiktoken version')
        ranks = {base64.b64decode(token, validate=True): int(rank)
                 for token, rank in (line.split() for line in data.splitlines())}
        # Special-looking memory strings remain ordinary data, never control tokens.
        return tiktoken.Encoding(name=name, pat_str=ENCODINGS[name][1],
                                 mergeable_ranks=ranks, special_tokens={})
    except (ImportError, AttributeError, ValueError, RuntimeError) as exc:
        raise ElmError('tokenizer_unavailable',
                       'Measured budgeting requires locally installed tiktoken==0.14.0 and its supported native extension; no estimate fallback') from exc


class TokenCounter:
    def __init__(self, name, vocab):
        validate_settings('measured', name, vocab)
        try:
            with Path(vocab).open('rb') as stream:
                data = stream.read(8_000_001)
        except OSError as exc:
            raise ElmError('tokenizer_vocab_unavailable', 'Configured local vocabulary is unreadable; no download or estimate fallback') from exc
        self.sha256 = hashlib.sha256(data).hexdigest()
        if len(data) > 8_000_000 or self.sha256 != ENCODINGS[name][0]:
            raise ElmError('tokenizer_vocab_mismatch', 'Local vocabulary does not match the named encoding SHA-256')
        self.name = name
        self.encoding = _encoding(name, self.sha256, data)
        self.max_token_bytes = max(len(token) for token in self.encoding._mergeable_ranks)

    def count(self, text):
        if not isinstance(text, str):
            raise ElmError('invalid_budget_text', 'Token counting requires exact text')
        try:
            text.encode('utf-8', errors='strict')
        except UnicodeError as exc:
            raise ElmError('invalid_budget_unicode', 'Lone surrogates cannot be delivered as exact UTF-8 text') from exc
        return len(self.encoding.encode_ordinary(text))

    def measure(self, text):
        count = self.count(text)
        return {'tokens': count, 'tokenizer': self.name, 'tiktoken_version': TOKENIZER_VERSION,
                'vocabulary_sha256': self.sha256,
                'text_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
                'utf8_bytes': len(text.encode('utf-8'))}
