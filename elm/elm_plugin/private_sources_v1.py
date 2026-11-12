"""Captured private-chat source bytes and human-reviewed exact excerpts; never model extraction."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
import re
import secrets
import threading
import time
import uuid

from .workspace_records import RecordError, RecordStore, _id, _now

_MAX_SOURCES = 64
_MAX_TEXT = 65536
_REF = re.compile(r'^elm-snapshot-v1:(src_[0-9a-f]{32}):(0|[1-9][0-9]*):(0|[1-9][0-9]*)$')


def _fail(code, text):
    raise RecordError(code, text)


def _items(data):
    return data.get('private_sources', {}).get('items', {})


def _hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _source(data, chat, source_id):
    _id(source_id)
    item = _items(data).get(source_id)
    if item is None or item['scope_id'] != chat:
        _fail('source_not_found', 'Source is not available in this private chat')
    return item


def _links(record):
    for source in record['sources']:
        if source['ref'].startswith('elm-snapshot-v1:'):
            match = _REF.fullmatch(source['ref'])
            if match is None:
                raise ValueError('Invalid captured source reference')
            source_id, start, end = match.groups()
            yield source, source_id, int(start), int(end)


def validate_sources(data):
    """Called on every private manifest load/save, including retained bodies."""
    ext = data.get('private_sources', {'schema': 1, 'items': {}})
    if (type(ext) is not dict or set(ext) != {'schema', 'items'} or type(ext['schema']) is not int
            or ext['schema'] != 1 or type(ext['items']) is not dict or len(ext['items']) > _MAX_SOURCES):
        raise ValueError('Invalid private source registry')
    fields = {'id', 'scope_id', 'title', 'text', 'reference', 'author', 'sha256', 'created_at', 'state', 'revision', 'sensitive'}
    for key, item in ext['items'].items():
        if (type(item) is not dict or set(item) not in (fields, fields | {'native_capture'}) or item['id'] != key
                or re.fullmatch('src_[0-9a-f]{32}', key) is None
                or type(item['sensitive']) is not bool or type(item['revision']) is not int or item['revision'] not in (1, 2)
                or item['state'] != ('active' if item['revision'] == 1 else 'withdrawn')):
            raise ValueError('Invalid source snapshot')
        provenance = item.get('native_capture')
        if provenance is not None:
            if (type(provenance) is not dict or set(provenance) != {'admission_id','role','phase','representation'}
                    or type(provenance['admission_id']) is not str or re.fullmatch('[0-9a-f]{32}', provenance['admission_id']) is None
                    or provenance['role'] not in ('user','assistant') or provenance['phase'] != 'finalized_before_delivery'
                    or provenance['representation'] != 'secret_redacted_native_text' or item['sensitive'] is not True):
                raise ValueError('Invalid native captured-source provenance')
        for field, limit in (('title', 512), ('text', _MAX_TEXT), ('reference', 2048), ('author', 512)):
            if type(item[field]) is not str or len(item[field].encode('utf-8')) > limit:
                raise ValueError('Source field exceeds bounds')
        if not item['text'] or item['sha256'] != _hash(item['text']):
            raise ValueError('Source byte integrity mismatch')
        scope = data['scopes'].get(item['scope_id'])
        if not scope or scope['kind'] != 'chat' or scope['private'] is not True or 'read_policy' in scope:
            raise ValueError('Invalid source ownership')
        if datetime.fromisoformat(item['created_at']).tzinfo is None:
            raise ValueError('Invalid source timestamp')
    records = list(data['records'].values())
    for envelope in data.get('private_trash', {}).get('items', {}).values():
        records.extend(envelope['records'].values())
    for record in records:
        for ref, source_id, start, end in _links(record):
            item = ext['items'].get(source_id)
            if (item is None or item['scope_id'] != record['scope_id'] or not 0 <= start < end <= len(item['text'])
                    or (item['sensitive'] and not record['sensitive'])
                    or ('revision' in ref and (type(ref['revision']) is not int or ref['revision'] != 1))
                    or ref.get('sha256') != item['sha256'] or ref.get('quote') != item['text'][start:end]):
                raise ValueError('Captured source reference does not match owned bytes')


def sources_active(data, record):
    return all(_items(data)[source_id]['state'] == 'active' for _, source_id, _, _ in _links(record))


def require_active_sources(data, record):
    if not sources_active(data, record):
        _fail('source_withdrawn', 'A captured source was withdrawn; record cannot regain eligibility')


def _summary(item):
    return dict(source_id=item['id'], title=item['title'], sha256=item['sha256'], revision=item['revision'],
                state=item['state'], content_revision=1, sensitive=item['sensitive'], utf8_bytes=len(item['text'].encode('utf-8')),
                codepoints=len(item['text']), created_at=item['created_at'],
                **({'native_capture':deepcopy(item['native_capture'])} if 'native_capture' in item else {}))


def _input(title, text, reference, author, sensitive):
    if type(sensitive) is not bool:
        _fail('invalid_payload', 'Source sensitivity must be an explicit boolean')
    values = dict(title=title, text=text, reference=reference, author=author, sensitive=sensitive)
    for field, limit in (('title', 512), ('text', _MAX_TEXT), ('reference', 2048), ('author', 512)):
        value = values[field]
        if type(value) is not str or len(value.encode('utf-8')) > limit:
            _fail('invalid_payload', 'Source fields exceed the bounded UTF-8 input limits')
    if not title or not text:
        _fail('invalid_payload', 'Source title and exact text are required')
    return values


class PrivateSourcesV1:
    def __init__(self):
        self._lock = threading.Lock()
        self._active = True
        self._previews = {}

    def close(self):
        with self._lock:
            self._active = False
            self._previews.clear()

    def _live(self):
        if not self._active:
            _fail('context_expired', 'Source workflow is no longer active')

    def _token(self, owner, store_id, kind, payload):
        now = time.monotonic()
        self._previews = {k: v for k, v in self._previews.items() if v[0] > now}
        if (len(self._previews) >= 64 or sum(len(json.dumps(v[4], ensure_ascii=True).encode()) for v in self._previews.values())
                + len(json.dumps(payload, ensure_ascii=True).encode()) > 8 * 1024 * 1024):
            _fail('preview_limit', 'Too many outstanding source previews')
        token = secrets.token_urlsafe(32)
        self._previews[token] = (now + 300, owner, store_id, kind, deepcopy(payload))
        return token

    def _redeem(self, owner, token, kind):
        if type(token) is not str or len(token) > 128:
            _fail('stale_preview', 'Source preview is unavailable')
        preview = self._previews.get(token)
        if preview is None:
            _fail('stale_preview', 'Source preview is unavailable; review again')
        deadline, expected, store_id, operation, payload = preview
        if (owner.profile_id, owner.principal_id, owner.canonical_session_id) != (expected.profile_id, expected.principal_id, expected.canonical_session_id):
            _fail('stale_preview', 'Source preview is not owned by this chat')
        del self._previews[token]
        if owner != expected or operation != kind or time.monotonic() >= deadline:
            _fail('stale_preview', 'Source preview changed or expired; review again')
        return store_id, payload

    def preview(self, *, title, text, reference='', author='', sensitive=True):
        from hermes_cli.plugin_memory import memory_owner, read_memory
        from .private_workspace_v2 import _transaction
        values = _input(title, text, reference, author, sensitive)
        owner = memory_owner(version=1)
        with self._lock:
            self._live()
            def inspect():
                with _transaction(owner) as (_, data, _):
                    return data['store_id']
            store_id = read_memory(owner, inspect)
            token = self._token(owner, store_id, 'source', values)
            return dict(preview_token=token, sha256=_hash(text), utf8_bytes=len(text.encode('utf-8')),
                        codepoints=len(text), sensitive=sensitive, expires_in_seconds=300,
                        notice='Capture the exact text received by this API with its UTF-8 digest, not original file bytes or a live URL. Reference and author are unverified declarations, never fetched. Withdrawal retains text; no purge is provided.')

    def apply(self, preview_token, *, confirm=False):
        if confirm is not True:
            _fail('confirmation_required', 'Explicit source capture confirmation is required')
        from hermes_cli.plugin_memory import memory_owner, publish_memory
        from .private_workspace_v2 import _transaction
        owner = memory_owner(version=1)
        with self._lock:
            self._live()
            expected_store, values = self._redeem(owner, preview_token, 'source')
            def capture():
                with _transaction(owner, write=True, create_chat=True) as (_, data, chat):
                    if data['store_id'] != expected_store:
                        _fail('stale_preview', 'Source destination changed; review again')
                    items = data.setdefault('private_sources', dict(schema=1, items={}))['items']
                    if len(items) >= _MAX_SOURCES:
                        _fail('source_limit', 'Private source capacity reached; no eviction or purge attempted')
                    key = 'src_' + uuid.uuid4().hex
                    if key in items:
                        _fail('revision_conflict', 'Generated source identity collided')
                    item = dict(id=key, scope_id=chat, **values, sha256=_hash(values['text']),
                                revision=1, state='active', created_at=_now())
                    items[key] = item
                    return _summary(item)
            return publish_memory(owner, capture)

    def list(self, *, limit=16, before=None):
        if type(limit) is not int or not 1 <= limit <= 32:
            _fail('invalid_payload', 'Source list limit must be one to thirty-two')
        if before is not None:
            _id(before)
        from hermes_cli.plugin_memory import memory_owner, read_memory
        from .private_workspace_v2 import _transaction
        owner = memory_owner(version=1)
        with self._lock:
            self._live()
            def inspect():
                with _transaction(owner) as (_, data, chat):
                    items = sorted((v for v in _items(data).values() if v['scope_id'] == chat), key=lambda v:(v['created_at'], v['id']), reverse=True)
                    if before is not None:
                        matches = [i for i, v in enumerate(items) if v['id'] == before]
                        if not matches:
                            _fail('stale_preview', 'Source cursor unavailable; refresh this chat list')
                        items = items[matches[0]+1:]
                    result = dict(sources=[], truncated=False, next_before=None)
                    for item in items[:limit]:
                        result['sources'].append(_summary(item))
                        if len(json.dumps(result, ensure_ascii=True).encode()) > 32768 - 256:
                            result['sources'].pop()
                            break
                    result['truncated'] = len(items) > len(result['sources'])
                    if result['truncated'] and result['sources']:
                        result['next_before'] = result['sources'][-1]['source_id']
                    return result
            return read_memory(owner, inspect)

    def get(self, source_id):
        from hermes_cli.plugin_memory import memory_owner, read_memory
        from .private_workspace_v2 import _transaction
        owner = memory_owner(version=1)
        with self._lock:
            self._live()
            def inspect():
                with _transaction(owner) as (_, data, chat):
                    item = _source(data, chat, source_id)
                    result = dict(source={**_summary(item), **{k:item[k] for k in ('text','reference','author')}},
                                  content_role='untrusted_source_data', verification='captured_bytes_only')
                    if len(json.dumps(result, ensure_ascii=True).encode()) > 524288:
                        _fail('inspection_limit', 'Full source exceeds inspection response limit; no partial content returned')
                    return result
            return read_memory(owner, inspect)

    def excerpt_preview(self, source_id, quote, *, occurrence=None, title=None):
        if type(quote) is not str or not quote or len(quote.encode('utf-8')) > 8192:
            _fail('invalid_payload', 'A nonempty exact quote of at most 8192 UTF-8 bytes is required')
        if occurrence is not None and (type(occurrence) is not int or occurrence < 1):
            _fail('invalid_payload', 'Occurrence must be a positive integer')
        from hermes_cli.plugin_memory import memory_owner, read_memory
        from .private_workspace_v2 import _transaction
        owner = memory_owner(version=1)
        with self._lock:
            self._live()
            def inspect():
                with _transaction(owner) as (_, data, chat):
                    item = _source(data, chat, source_id)
                    if item['state'] != 'active':
                        _fail('source_withdrawn', 'Withdrawn source cannot produce new pending records')
                    positions, start = [], item['text'].find(quote)
                    while start >= 0:
                        positions.append(start)
                        start = item['text'].find(quote, start + 1)
                    if not positions:
                        _fail('quote_not_found', 'Quote does not exactly match captured text')
                    if occurrence is None and len(positions) != 1:
                        _fail('ambiguous_quote', 'Repeated quote requires an explicit one-based occurrence')
                    chosen = 1 if occurrence is None else occurrence
                    if chosen > len(positions):
                        _fail('quote_not_found', 'Requested quote occurrence is unavailable')
                    record_title = item['title'] if title is None else title
                    if type(record_title) is not str or not record_title or len(record_title.encode('utf-8')) > 512:
                        _fail('invalid_payload', 'A bounded excerpt title is required')
                    start = positions[chosen - 1]
                    # Refuse unsupported record content/serialized provenance before
                    # asking for confirmation, not after consuming the preview.
                    from .private_workspace_v2 import _authored_fields
                    _authored_fields(record_title, quote,
                        [dict(ref=f"elm-snapshot-v1:{source_id}:{start}:{start + len(quote)}",
                              quote=quote, sha256=item['sha256'], revision=1)],
                        'reference', 'reference', 'source_document', 'facts', item['sensitive'])
                    return data['store_id'], dict(source_id=source_id, source_revision=item['revision'], sha256=item['sha256'],
                        quote=quote, start=start, end=start+len(quote), offset_unit='unicode_codepoints', occurrence=chosen,
                        candidate=dict(title=record_title, text=quote, state='pending', sensitive=item['sensitive']),
                        **({'source_origin':deepcopy(item['native_capture'])} if 'native_capture' in item else {}))
            store_id, payload = read_memory(owner, inspect)
            return dict(**payload, preview_token=self._token(owner, store_id, 'excerpt', payload), expires_in_seconds=300,
                        notice='Create a pending exact excerpt, not a verified fact or semantic extraction. Approval remains separate.')

    def excerpt_apply(self, preview_token, *, confirm=False):
        if confirm is not True:
            _fail('confirmation_required', 'Explicit excerpt creation confirmation is required')
        from hermes_cli.plugin_memory import memory_owner, publish_memory
        from .private_workspace_v2 import _transaction, _record_count, _authored_fields
        owner = memory_owner(version=1)
        with self._lock:
            self._live()
            expected_store, payload = self._redeem(owner, preview_token, 'excerpt')
            def create():
                with _transaction(owner, write=True) as (store, data, chat):
                    item = _source(data, chat, payload['source_id'])
                    if data['store_id'] != expected_store or item['revision'] != payload['source_revision'] or item['sha256'] != payload['sha256'] or item['state'] != 'active':
                        _fail('stale_preview', 'Captured source changed; review again')
                    if _record_count(data) >= 512:
                        _fail('store_limit', 'Private record capacity reached')
                    ref = f"elm-snapshot-v1:{item['id']}:{payload['start']}:{payload['end']}"
                    fields = _authored_fields(payload['candidate']['title'], payload['quote'],
                        [dict(ref=ref, quote=payload['quote'], sha256=item['sha256'], revision=1)], 'reference', 'reference', 'source_document', 'facts', item['sensitive'])
                    key, now = 'rec_' + uuid.uuid4().hex, _now()
                    if key in data['records'] or key in data['tombstones']:
                        _fail('revision_conflict', 'Generated record identity collided')
                    record = dict(id=key, revision=1, scope_id=chat, **fields, created_at=now, updated_at=now)
                    data['records'][key] = record
                    return deepcopy(record)
            return publish_memory(owner, create)

    def withdraw(self, source_id, expected_revision, *, confirm=False):
        if confirm is not True:
            _fail('confirmation_required', 'Explicit source withdrawal confirmation is required; bytes are retained')
        from hermes_cli.plugin_memory import memory_owner, publish_memory
        from .private_workspace_v2 import _transaction
        owner = memory_owner(version=1)
        with self._lock:
            self._live()
            def retire():
                with _transaction(owner, write=True) as (store, data, chat):
                    item = _source(data, chat, source_id)
                    if type(expected_revision) is not int or item['revision'] != expected_revision or item['state'] != 'active':
                        _fail('revision_conflict', 'Source changed or was withdrawn; refresh before retrying')
                    linked = {r['id'] for r in data['records'].values() if any(k == source_id for _,k,_,_ in _links(r))}
                    affected = linked | store._dependents(data, linked)
                    if any(data['records'][key]['scope_id'] != chat for key in affected):
                        _fail('sharing_denied', 'Source withdrawal cannot cross private chat ownership')
                    item.update(state='withdrawn', revision=2)
                    for key in affected:
                        r = data['records'][key]
                        r.update(state='invalidated', revision=r['revision']+1, updated_at=_now())
                    return dict(source=_summary(item), invalidated_ids=sorted(affected), retained_bytes=True, purge_available=False)
            return publish_memory(owner, retire)
