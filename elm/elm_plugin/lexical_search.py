"""Explicit local lexical search. Does not change recall or call a model."""
import json
import re

from .private_workspace_v2 import _fail
from .wiki_read import WikiRead


def _terms(value):
    return set(re.findall(r'\w+', value.casefold(), flags=re.UNICODE))


def _query(value):
    if type(value) is not str:
        _fail('invalid_query', 'Search requires a short textual query')
    try:
        size = len(value.encode('utf-8', errors='strict'))
    except UnicodeError:
        _fail('invalid_query', 'Search requires valid UTF-8 text')
    if not 1 <= size <= 512:
        _fail('invalid_query', 'Query requires 1-512 UTF-8 bytes')
    terms = _terms(value)
    if not 1 <= len(terms) <= 64:
        _fail('invalid_query', 'Query requires 1-512 UTF-8 bytes and 1-64 distinct word terms')
    return terms


def _serialize(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _pack(counter, lane, snapshot, records, terms):
    from .workspace_records import recall_records
    eligible = recall_records(records)
    ranked = [(len(terms & _terms(record['title'] + '\n' + record['text'])), record)
              for record in eligible]
    # WikiRead already establishes newest updated_at/id order; stable sort preserves it.
    ranked = [record for score, record in sorted(ranked, key=lambda pair: -pair[0]) if score > 0]
    result = dict(schema=1, lane=lane, algorithm='literal_overlap_v1', tokenizer='o200k_base',
                  token_limit=700, snapshot_key=snapshot, status='no_match',
                  eligible_count=len(eligible), matched_count=len(ranked),
                  omitted_count=len(ranked), records=[])
    # Reserve the longest status form while greedily adding indivisible complete records.
    result['status'] = 'evidence_exceeds_budget' if ranked else 'no_match'
    if counter.count(_serialize(result)) > 700:
        _fail('search_budget_unavailable', 'Search metadata exceeds its exact token budget')
    for record in ranked:
        result['records'].append(record)
        result['omitted_count'] -= 1
        if counter.count(_serialize(result)) > 700:
            result['records'].pop()
            result['omitted_count'] += 1
    if result['records']:
        result['status'] = 'partial' if result['omitted_count'] else 'matched'
    output = _serialize(result)
    if counter.count(output) > 700:
        _fail('search_budget_unavailable', 'Search response exceeds its exact token budget')
    return output


class LexicalSearch(WikiRead):
    def __init__(self, vocab):
        super().__init__()
        self._vocab = vocab

    def query(self, lane, query):
        terms = _query(query)
        def render(snapshot, records):
            from .token_budget import TokenCounter
            from .engine import ElmError
            try:
                counter = TokenCounter('o200k_base', self._vocab)
            except (ElmError, TypeError, ValueError):
                _fail('search_tokenizer_unavailable',
                      'Search requires configured local pinned o200k_base vocabulary and tiktoken 0.14.0; no fallback')
            return _pack(counter, lane, snapshot, records, terms)
        return self._read(lane, render)


def register_search_rpc(ctx):
    try:
        from hermes_cli.plugin_memory import memory_capabilities
    except ImportError:
        return False
    register = getattr(ctx, 'register_rpc', None)
    if not callable(register) or not memory_capabilities().get('record_read'):
        return False
    get_config = getattr(ctx, 'get_config', None)
    vocab = get_config('search_tokenizer_vocab', None) if callable(get_config) else None
    service = LexicalSearch(vocab)
    from .private_workspace_rpc import _fields
    def handler(lane):
        def run(params, **kwargs):
            _fields(params, ('query',))
            return service.query(lane, params['query'])
        return run
    for lane in ('private', 'project'):
        register('search.' + lane + '.query', handler(lane), memory_scope='local_read')
    unload = getattr(ctx, 'on_unload', None)
    if callable(unload):
        unload(service.close)
    return True
