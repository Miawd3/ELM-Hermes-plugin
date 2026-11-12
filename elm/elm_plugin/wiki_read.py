"""Human-selected wiki projections; no corpus scan, synthesis, writes or model tools."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
import json
import re
import threading

from .private_workspace_v2 import _digest, _fail


def _snapshot(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        _fail('invalid_payload', 'A current wiki snapshot is required')
    return value


@contextmanager
def _view(owner, lane):
    if lane == 'private':
        from .private_workspace_v2 import _transaction
        with _transaction(owner) as (_, data, scope):
            sources = {key: item for key, item in data.get('private_sources', {}).get('items', {}).items()
                       if item['scope_id'] == scope}
            yield data, scope, sources, None
    else:
        from .project_workspace_v1 import _transaction, _scope, _consent
        with _transaction(owner, access='expanded') as (_, data):
            yield data, _scope(owner), {}, _consent(data, owner)


def _visible(records, data, lane):
    """Approved human evidence only, including sensitive records; not model recall."""
    from .private_sources_v1 import sources_active
    by_id = {record['id']: record for record in records}
    denied = {record['id'] for record in records if record['state'] != 'approved'
              or (lane == 'private' and not sources_active(data, record))}
    children = {}
    for record in records:
        for dep in record['dependencies']:
            children.setdefault(dep['id'], []).append(record['id'])
            target = by_id.get(dep['id'])
            if target is None or target['revision'] != dep['revision']:
                denied.add(record['id'])
    pending = list(denied)
    while pending:
        for child in children.get(pending.pop(), ()):
            if child not in denied:
                denied.add(child)
                pending.append(child)
    return [record for record in records if record['id'] not in denied]


def _material(owner, lane, data, scope, sources, consent):
    records = [record for record in data['records'].values() if record['scope_id'] == scope]
    # Hash all current scope records, not global revisions/activity. Captured text
    # is covered by its validated digest; source lifecycle/provenance also pins it.
    pins = {key: {field: value for field, value in item.items() if field != 'text'}
            for key, item in sources.items()}
    key = _digest([1, lane, asdict(owner), data['store_id'], scope,
                   sorted(records, key=lambda record: record['id']), pins, consent])
    return key, sorted(_visible(records, data, lane),
                       key=lambda record: (record['updated_at'], record['id']), reverse=True)


def _base(lane, key):
    return dict(lane=lane, snapshot_key=key, inspection_only=True,
                content_role='untrusted_memory_data')


def _bounded(result, limit):
    if len(json.dumps(result, ensure_ascii=True, allow_nan=False).encode()) > limit:
        _fail('inspection_limit', 'Wiki response exceeds the bounded human inspection limit')
    return result


class WikiRead:
    def __init__(self):
        self._lock = threading.RLock()
        self._active = True

    def close(self):
        with self._lock:
            self._active = False

    def _read(self, lane, render):
        if lane not in ('private', 'project'):
            _fail('invalid_payload', 'Unsupported wiki lane')
        from hermes_cli.plugin_memory import memory_owner, read_memory
        with self._lock:
            if not self._active:
                _fail('context_unavailable', 'Wiki reader is no longer active')
            owner = memory_owner(version=1)
            def inspect():
                with _view(owner, lane) as (data, scope, sources, consent):
                    key, records = _material(owner, lane, data, scope, sources, consent)
                    return render(key, records)
            return read_memory(owner, inspect)

    def index(self, lane, *, limit=16, before=None, expected_snapshot=None):
        from .workspace_records import _id
        if type(limit) is not int or not 1 <= limit <= 32:
            _fail('invalid_payload', 'Wiki limit must be one to thirty-two')
        if before is not None:
            _id(before)
            _snapshot(expected_snapshot)
        if expected_snapshot is not None:
            _snapshot(expected_snapshot)
        def render(key, records):
            if expected_snapshot is not None and key != expected_snapshot:
                _fail('stale_snapshot', 'Wiki changed; refresh the selected scope')
            if before is not None:
                positions = [i for i, record in enumerate(records) if record['id'] == before]
                if not positions:
                    _fail('stale_snapshot', 'Wiki cursor is unavailable; refresh the selected scope')
                records = records[positions[0] + 1:]
            fields = ('id', 'revision', 'title', 'domain', 'kind', 'basis', 'topic', 'sensitive', 'updated_at')
            result = dict(_base(lane, key), records=[], next_before=None, truncated=False)
            for record in records[:limit]:
                row = {field: record[field] for field in fields}
                trial = dict(result, records=result['records'] + [row])
                if len(json.dumps(trial, ensure_ascii=True).encode()) > 32000:
                    break
                result['records'].append(row)
            result['truncated'] = len(records) > len(result['records'])
            if result['truncated'] and result['records']:
                result['next_before'] = result['records'][-1]['id']
            if records and not result['records']:
                _fail('inspection_limit', 'Wiki summary exceeds the response limit')
            return _bounded(result, 32768)
        return self._read(lane, render)

    def selected(self, lane, record_id, expected_snapshot, *, evidence=False):
        from .workspace_records import _id
        _id(record_id)
        _snapshot(expected_snapshot)
        def render(key, records):
            if key != expected_snapshot:
                _fail('stale_snapshot', 'Wiki changed; refresh the selected scope')
            record = next((record for record in records if record['id'] == record_id), None)
            if record is None:
                _fail('record_not_found', 'Approved wiki record is unavailable in the selected scope')
            result = _base(lane, key)
            if evidence:
                result.update(record_id=record_id, record_revision=record['revision'],
                              sources=deepcopy(record['sources']), source_content='citation_quotes_only')
            else:
                result.update(record={field: deepcopy(value) for field, value in record.items() if field != 'sources'},
                              source_count=len(record['sources']))
            return _bounded(result, 65536)
        return self._read(lane, render)


def register_wiki_rpc(ctx):
    try:
        from hermes_cli.plugin_memory import memory_capabilities
    except ImportError:
        return False
    if not memory_capabilities().get('record_read'):
        return False
    register = getattr(ctx, 'register_rpc', None)
    if not callable(register):
        return False
    from .private_workspace_rpc import _fields
    service = WikiRead()
    def index(lane):
        def handler(params, **kwargs):
            _fields(params, (), ('limit', 'before', 'expected_snapshot'))
            return service.index(lane, **{key: value for key, value in params.items() if key != 'session_id'})
        return handler
    def selected(lane, evidence):
        def handler(params, **kwargs):
            _fields(params, ('record_id', 'expected_snapshot'))
            return service.selected(lane, params['record_id'], params['expected_snapshot'], evidence=evidence)
        return handler
    for lane in ('private', 'project'):
        register('wiki.' + lane + '.index', index(lane), memory_scope='local_read')
        register('wiki.' + lane + '.page', selected(lane, False), memory_scope='local_read')
        register('wiki.' + lane + '.evidence', selected(lane, True), memory_scope='local_read')
    unload = getattr(ctx, 'on_unload', None)
    if callable(unload):
        unload(service.close)
    return True
