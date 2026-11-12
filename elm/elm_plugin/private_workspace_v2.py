"""Fresh principal-qualified PRIVATE CHAT records, never legacy/project adoption.

Only explicit human control RPCs may initialize, propose or approve records. Read
callbacks run under the native bounded ownership fence and never create files/scopes.
Project selection grants no access here. This is not provider/background recall.
Filesystem ownership is assumed; known symlink escapes are rejected, but this module
is not a sandbox against a hostile process concurrently replacing directory entries.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import uuid

from .workspace_records import RecordError, RecordStore, recall_records, _now, _id

_MAX_OUTPUT_BYTES = 32768
_MAX_STORE_BYTES = 4 * 1024 * 1024
_MAX_RECORDS = 512
_MARKER_OWNER = 'elm-private-workspace-v2'


def _fail(code, message):
    raise RecordError(code, message)


def _digest(values):
    return hashlib.sha256(json.dumps(values, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _trash_items(data):
    return data.get('private_trash', {}).get('items', {})


def _record_count(data):
    return len(data['records']) + sum(len(item['records']) for item in _trash_items(data).values())


def _retained_record(record_id, record, scope_id):
    authored = {'title', 'text', 'domain', 'kind', 'basis', 'sources', 'topic', 'state', 'dependencies', 'sensitive'}
    _id(record_id)
    if (not isinstance(record, dict) or set(record) != authored | {'id', 'revision', 'scope_id', 'created_at', 'updated_at'}
            or record['id'] != record_id or record['scope_id'] != scope_id
            or type(record['revision']) is not int or record['revision'] < 1):
        raise ValueError('Invalid retained record')
    RecordStore._fields(**{key: record[key] for key in authored})
    for field in ('created_at', 'updated_at'):
        if datetime.fromisoformat(record[field]).tzinfo is None:
            raise ValueError('Invalid retained timestamp')
    deps = record['dependencies']
    seen = set()
    for dep in deps:
        if (not isinstance(dep, dict) or set(dep) != {'id', 'revision'} or dep['id'] in seen
                or type(dep['revision']) is not int or dep['revision'] < 1):
            raise ValueError('Invalid retained dependency')
        _id(dep['id'])
        seen.add(dep['id'])
    pointers = {pointer for source in record['sources'] if (pointer := RecordStore._pointer(source['ref'])) is not None}
    if pointers != seen:
        raise ValueError('Invalid retained provenance')
    pins = {dep['id']: dep['revision'] for dep in deps}
    for source in record['sources']:
        pointer = RecordStore._pointer(source['ref'])
        if pointer is not None and 'revision' in source and source['revision'] != pins[pointer]:
            raise ValueError('Retained source revision mismatch')


class _PrivateRecordStore(RecordStore):
    """Private-v2-only additive trash envelope, atomically committed with native tombstones.

    Generic/legacy RecordStore remains unchanged and does not understand this extension.
    The surrounding service requires its principal/store marker before any operation.
    """
    def _validate_manifest(self, data):
        base = {key: value for key, value in data.items() if key not in ('private_trash', 'private_sources', 'private_recall', 'private_capture', 'private_curation', 'private_imports', 'reference_drafts', 'model_preferences')}
        super()._validate_manifest(base)
        from .private_sources_v1 import validate_sources
        validate_sources(data)
        from .scoped_recall import validate_recall_settings
        validate_recall_settings(data)
        from .conversation_capture import validate_capture
        validate_capture(data)
        from .curation_jobs import validate_jobs
        validate_jobs(data)
        from .private_import_v1 import validate_imports
        validate_imports(data)
        from .reference_drafts import validate_drafts
        validate_drafts(data)
        from .model_preferences import validate_model_preferences
        validate_model_preferences(data)
        if 'private_trash' not in data:
            return
        trash = data['private_trash']
        if (not isinstance(trash, dict) or set(trash) != {'schema', 'items'}
                or type(trash['schema']) is not int or trash['schema'] != 1 or not isinstance(trash['items'], dict)):
            raise ValueError('Invalid private trash schema')
        retained = set()
        for recovery_id, item in trash['items'].items():
            self._validate_envelope(data, recovery_id, item, retained)
        if _record_count(data) > _MAX_RECORDS:
            raise ValueError('Private record retention limit exceeded')

    def _validate_envelope(self, data, recovery_id, item, retained):
        _id(recovery_id)
        fields = {'id', 'store_id', 'scope_id', 'deleted_at', 'records', 'tombstone_revisions', 'digest'}
        if (not isinstance(item, dict) or set(item) != fields or item['id'] != recovery_id
                or item['store_id'] != data['store_id'] or not isinstance(item['records'], dict)
                or not item['records'] or not isinstance(item['tombstone_revisions'], dict)
                or set(item['records']) != set(item['tombstone_revisions'])):
            raise ValueError('Invalid private recovery envelope')
        if item['digest'] != _digest({key: value for key, value in item.items() if key != 'digest'}):
            raise ValueError('Private recovery checksum mismatch')
        scope = data['scopes'].get(item['scope_id'])
        if not scope or scope['kind'] != 'chat' or scope['private'] is not True or 'read_policy' in scope:
            raise ValueError('Invalid recovery ownership')
        if datetime.fromisoformat(item['deleted_at']).tzinfo is None:
            raise ValueError('Invalid recovery timestamp')
        for record_id, record in item['records'].items():
            _retained_record(record_id, record, item['scope_id'])
            revision = item['tombstone_revisions'][record_id]
            tombstone = data['tombstones'].get(record_id)
            if (record_id in retained or record_id in data['records'] or type(revision) is not int
                    or revision != record['revision'] + 1 or tombstone != dict(
                        id=record_id, scope_id=item['scope_id'], revision=revision, deleted_at=item['deleted_at'])):
                raise ValueError('Private recovery tombstone mismatch')
            retained.add(record_id)
            if record_id in self._ancestors({'records': item['records']}, record_id):
                raise ValueError('Private recovery dependency cycle')


def _paths(owner):
    from hermes_constants import get_hermes_home
    home = Path(get_hermes_home()).resolve()
    if not Path(owner.profile_id).is_absolute() or Path(owner.profile_id).resolve() != home:
        _fail('scope_changed', 'Private memory profile context does not match authenticated ownership')
    namespace = _digest([2, owner.profile_id, owner.principal_id])
    base = home / _MARKER_OWNER
    root = base / namespace
    records = root / 'records'
    known = (base, root, records, root / 'owner.json', records / 'manifest.json',
             records / '.records.lock', records / '.manifest.next')
    if any(path.is_symlink() for path in known):
        _fail('unowned_root', 'Private memory refuses symlinked ownership or record paths')
    if root.resolve().parent != base.resolve() or base.resolve().parent != home:
        _fail('unowned_root', 'Private memory root escaped its owning profile')
    chat = 'chat:' + _digest([2, owner.profile_id, owner.principal_id, owner.canonical_session_id])
    return root, _PrivateRecordStore(records), namespace, chat


def _marker(root, namespace, store_id):
    try:
        value = json.loads((root / 'owner.json').read_text(encoding='utf-8'))
    except (OSError, ValueError, UnicodeError) as exc:
        raise RecordError('unowned_root', 'Private memory ownership marker is missing or unreadable') from exc
    if value != {'owner': _MARKER_OWNER, 'schema': 2, 'namespace': namespace, 'store_id': store_id}:
        _fail('unowned_root', 'Private memory ownership marker does not match this principal store')


def _chat_scope(data, chat, *, create=False):
    scope = data['scopes'].get(chat)
    if scope is None and create:
        scope = data['scopes'][chat] = dict(id=chat, kind='chat', label='Private chat', private=True)
    if scope is not None and (scope['kind'] != 'chat' or scope['private'] is not True or 'read_policy' in scope):
        _fail('sharing_denied', 'Private chat memory refuses broader scopes or incoming read policies')
    if data['grants']:
        _fail('sharing_denied', 'This private memory lane does not accept record grants')
    return scope


@contextmanager
def _transaction(owner, *, write=False, create_chat=False):
    root, store, namespace, chat = _paths(owner)
    if not root.exists():
        _fail('not_initialized', 'Explicit fresh private-memory setup is required')
    try:
        size = (store.root / 'manifest.json').stat().st_size
    except OSError as exc:
        raise RecordError('not_initialized', 'Private memory setup is incomplete; no adoption or repair attempted') from exc
    if size > _MAX_STORE_BYTES:
        _fail('store_limit', 'Private memory exceeds this bounded prototype storage limit')
    with store._transaction(write=write) as data:
        if _record_count(data) > _MAX_RECORDS:
            _fail('store_limit', 'Private memory exceeds this bounded prototype record limit')
        _marker(root, namespace, data['store_id'])
        _chat_scope(data, chat, create=create_chat)
        yield store, data, chat
        # Recheck known redirects and marker before any write transaction publishes.
        _paths(owner)
        _marker(root, namespace, data['store_id'])
        if write:
            store._validate_manifest(data)
            pending = dict(data, revision=data['revision'] + 1)
            if len(json.dumps(pending, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')) + 1 > _MAX_STORE_BYTES:
                _fail('store_limit', 'Private memory is full; no change was saved')


def _chat_revision(data, chat):
    rows = sorted((r['id'], r['revision'], r['state']) for r in data['records'].values() if r['scope_id'] == chat)
    tombstones = sorted((item['id'], item['revision']) for item in data['tombstones'].values() if item['scope_id'] == chat)
    recoveries = sorted(key for key, item in _trash_items(data).items() if item['scope_id'] == chat)
    return _digest([chat, rows, tombstones, recoveries])


def _metadata(data, chat):
    records = [record for record in data['records'].values() if record['scope_id'] == chat]
    return {'initialized': True, 'chat_revision': _chat_revision(data, chat), 'private_chat_only': True,
            'pending_count': sum(record['state'] == 'pending' for record in records),
            'approved_count': sum(record['state'] == 'approved' for record in records),
            'trashed_count': sum(len(item['records']) for item in _trash_items(data).values() if item['scope_id'] == chat),
            'project_read_authorized': False, 'workspace_read_authorized': False,
            'migration': 'no_legacy_adoption', 'provider_recall': 'not_connected'}


def _authored_fields(title, text, sources, domain, kind, basis, topic, sensitive):
    if (not isinstance(title, str) or len(title.encode('utf-8')) > 512
            or not isinstance(text, str) or len(text.encode('utf-8')) > 8192
            or not isinstance(sources, list) or not 1 <= len(sources) <= 8):
        _fail('invalid_payload', 'A bounded title, text and one to eight sources are required')
    if len(json.dumps(sources, ensure_ascii=True).encode()) > 8192:
        _fail('invalid_payload', 'Source metadata exceeds the private record limit')
    return RecordStore._fields(title, text, domain, kind, basis, sources, topic, 'pending', None, sensitive)


def _owned_record(store, data, chat, record_id):
    _id(record_id)
    record = data['records'].get(record_id)
    if record is None or record['scope_id'] != chat:
        _fail('record_not_found', 'Record is not owned by the current private chat')
    return record


def _owned_closure(store, data, chat, record_id):
    _owned_record(store, data, chat, record_id)
    ids = {record_id} | store._dependents(data, {record_id})
    if any(data['records'][item]['scope_id'] != chat for item in ids):
        _fail('sharing_denied', 'Lifecycle changes cannot cross private-chat ownership')
    return sorted(ids)


def _deletion_preview(owner, store, data, chat, record_id):
    record = _owned_record(store, data, chat, record_id)
    ids = _owned_closure(store, data, chat, record_id)
    material = {'owner': asdict(owner), 'store_id': data['store_id'], 'chat': chat,
                'record_id': record_id, 'records': [data['records'][key] for key in ids]}
    return {'record_id': record_id, 'expected_revision': record['revision'],
            'preview_token': _digest(material), 'affected_record_ids': ids,
            'retention': 'until_restore_no_purge', 'purge_available': False,
            'notice': 'Deletion removes recall access but retains full bodies privately until restore; no permanent purge is provided.'}


def _restore_payload(store, data, chat, envelope):
    restored = deepcopy(envelope['records'])
    revisions = {key: envelope['tombstone_revisions'][key] + 1 for key in restored}
    for record_id, record in restored.items():
        if record['scope_id'] != chat or record_id in data['records']:
            _fail('record_not_found', 'Recovery is not available for the current private chat')
        for dep in record['dependencies']:
            if dep['id'] in restored:
                dep['revision'] = revisions[dep['id']]
            else:
                source = data['records'].get(dep['id'])
                if source is None or source['scope_id'] != chat or source['revision'] != dep['revision']:
                    _fail('dependency_changed', 'A surviving source changed; retained data was not restored or discarded')
        pins = {dep['id']: dep['revision'] for dep in record['dependencies']}
        for source in record['sources']:
            pointer = store._pointer(source['ref'])
            if pointer in revisions and 'revision' in source:
                source['revision'] = pins[pointer]
        record.update(state='pending', revision=revisions[record_id], updated_at=_now())
    return restored


class PrivateWorkspaceV2:
    """No caller-selected home/root/scope; every operation resolves authenticated host context."""

    def status(self):
        from hermes_cli.plugin_memory import memory_owner, read_memory
        owner = memory_owner(version=1)
        def inspect():
            root, _, _, _ = _paths(owner)
            if not root.exists():
                return {'initialized': False, 'private_chat_only': True, 'project_read_authorized': False,
                        'workspace_read_authorized': False, 'migration': 'no_legacy_adoption',
                        'provider_recall': 'not_connected'}
            with _transaction(owner) as (_, data, chat):
                return _metadata(data, chat)
        return read_memory(owner, inspect)

    def list(self, *, limit=16, state='all', before=None):
        """Human inspection summaries, including pending/sensitive records; never model recall."""
        if type(limit) is not int or not 1 <= limit <= 32:
            _fail('invalid_payload', 'Inspection limit must be an integer from one to thirty-two')
        if not isinstance(state, str) or state not in {'all', 'pending', 'approved', 'invalidated'}:
            _fail('invalid_payload', 'Unsupported inspection state filter')
        if before is not None:
            _id(before)
        from hermes_cli.plugin_memory import memory_owner, read_memory
        owner = memory_owner(version=1)
        def inspect_records():
            with _transaction(owner) as (_, data, chat):
                records = sorted((record for record in data['records'].values()
                                  if record['scope_id'] == chat and (state == 'all' or record['state'] == state)),
                                 key=lambda record: (record['updated_at'], record['id']), reverse=True)
                if before is not None:
                    positions = [index for index, record in enumerate(records) if record['id'] == before]
                    if not positions:
                        _fail('stale_preview', 'Inspection cursor is unavailable; refresh this chat list')
                    records = records[positions[0] + 1:]
                fields = ('id', 'revision', 'title', 'state', 'domain', 'kind', 'basis', 'topic', 'sensitive', 'updated_at')
                result = {'records': [], 'chat_revision': _chat_revision(data, chat),
                          'truncated': False, 'next_before': None, 'inspection_only': True}
                for record in records[:limit]:
                    result['records'].append({key: record[key] for key in fields})
                    if len(json.dumps(result, ensure_ascii=True).encode()) > _MAX_OUTPUT_BYTES - 256:
                        result['records'].pop()
                        break
                result['truncated'] = len(records) > len(result['records'])
                if records and not result['records']:
                    _fail('inspection_limit', 'Record summary exceeds this inspection response limit')
                if result['records'] and result['truncated']:
                    result['next_before'] = result['records'][-1]['id']
                return result
        return read_memory(owner, inspect_records)

    def get(self, record_id):
        """Return one full human-reviewed record or refuse; never silently truncate evidence."""
        from hermes_cli.plugin_memory import memory_owner, read_memory
        owner = memory_owner(version=1)
        def inspect_record():
            with _transaction(owner) as (store, data, chat):
                record = _owned_record(store, data, chat, record_id)
                from .private_sources_v1 import sources_active
                eligible = recall_records([item for item in data['records'].values() if item['scope_id'] == chat and sources_active(data, item)])
                result = {'record': deepcopy(record), 'recall_eligible': any(item['id'] == record_id for item in eligible),
                          'inspection_only': True, 'content_role': 'untrusted_memory_data'}
                if len(json.dumps(result, ensure_ascii=True).encode()) > 65536:
                    _fail('inspection_limit', 'Full record exceeds this inspection response limit; no partial review was returned')
                return result
        return read_memory(owner, inspect_record)

    def setup(self, *, confirm=False):
        if confirm is not True:
            _fail('confirmation_required', 'Explicit fresh private-memory setup confirmation is required')
        from hermes_cli.plugin_memory import memory_owner, publish_memory
        owner = memory_owner(version=1)
        def initialize():
            root, store, namespace, chat = _paths(owner)
            if root.exists():
                _fail('already_initialized', 'Existing private-memory roots are never adopted or replaced')
            root.parent.mkdir(exist_ok=True)
            root.mkdir()
            store.initialize()
            store.put_scope(chat, 'chat', 'Private chat', private=True)
            with store._transaction() as data:
                marker = {'owner': _MARKER_OWNER, 'schema': 2, 'namespace': namespace, 'store_id': data['store_id']}
                # Exclusive, never replaced. Partial setup is deliberately not auto-recovered.
                with (root / 'owner.json').open('x', encoding='utf-8') as stream:
                    json.dump(marker, stream, sort_keys=True)
                    stream.flush()
                    os.fsync(stream.fileno())
                return _metadata(data, chat)
        return publish_memory(owner, initialize)

    def create_pending(self, *, title, text, sources, domain='work', kind='reference',
                       basis='source_document', topic='facts', sensitive=False):
        fields = _authored_fields(title, text, sources, domain, kind, basis, topic, sensitive)
        from hermes_cli.plugin_memory import memory_owner, publish_memory
        owner = memory_owner(version=1)
        def create():
            with _transaction(owner, write=True, create_chat=True) as (store, data, chat):
                if _record_count(data) >= _MAX_RECORDS:
                    _fail('store_limit', 'Private memory has reached this prototype record limit')
                record_id, now = 'rec_' + uuid.uuid4().hex, _now()
                if record_id in data['records'] or record_id in data['tombstones']:
                    _fail('revision_conflict', 'Generated record identity collided')
                record = dict(id=record_id, revision=1, scope_id=chat, **fields, created_at=now, updated_at=now)
                store._dependencies(data, record)
                data['records'][record_id] = record
                return deepcopy(record)
        return publish_memory(owner, create)

    def approve(self, record_id, expected_revision, *, confirm=False):
        if confirm is not True:
            _fail('confirmation_required', 'Explicit record approval confirmation is required')
        from hermes_cli.plugin_memory import memory_owner, publish_memory
        owner = memory_owner(version=1)
        def approve_record():
            with _transaction(owner, write=True) as (store, data, chat):
                record = store._record(data, record_id)
                if record['scope_id'] != chat:
                    _fail('record_not_found', 'Record is not owned by the current private chat')
                store._expected(record, expected_revision)
                if record['state'] != 'pending':
                    _fail('invalid_state', 'Only the reviewed pending record can be approved')
                store._dependencies(data, record)
                from .private_sources_v1 import require_active_sources
                require_active_sources(data, record)
                record.update(state='approved', revision=record['revision'] + 1, updated_at=_now())
                store._invalidate(data, {record_id})
                store._reconcile_visibility(data)
                return deepcopy(record)
        return publish_memory(owner, approve_record)

    def correct(self, record_id, expected_revision, changes, *, confirm=False):
        allowed = {'title', 'text', 'sources', 'domain', 'kind', 'basis', 'topic', 'sensitive'}
        if confirm is not True:
            _fail('confirmation_required', 'Explicit record correction confirmation is required')
        if not isinstance(changes, dict) or not changes or not set(changes) <= allowed:
            _fail('invalid_changes', 'Corrections accept authored fields only, never scope, state or dependencies')
        from hermes_cli.plugin_memory import memory_owner, publish_memory
        owner = memory_owner(version=1)
        def correct_record():
            with _transaction(owner, write=True) as (store, data, chat):
                previous = _owned_record(store, data, chat, record_id)
                store._expected(previous, expected_revision)
                _owned_closure(store, data, chat, record_id)
                proposed = {**previous, **deepcopy(changes)}
                fields = _authored_fields(**{key: proposed[key] for key in allowed})
                fields['dependencies'] = deepcopy(previous['dependencies'])
                record = {**previous, **fields, 'revision': previous['revision'] + 1, 'updated_at': _now()}
                store._dependencies(data, record)
                data['records'][record_id] = record
                store._invalidate(data, {record_id})
                store._reconcile_visibility(data)
                return deepcopy(record)
        return publish_memory(owner, correct_record)

    def delete_preview(self, record_id):
        from hermes_cli.plugin_memory import memory_owner, read_memory
        owner = memory_owner(version=1)
        def preview():
            with _transaction(owner) as (store, data, chat):
                return _deletion_preview(owner, store, data, chat, record_id)
        return read_memory(owner, preview)

    def delete(self, record_id, expected_revision, preview_token, *, confirm=False):
        if confirm is not True:
            _fail('confirmation_required', 'Explicit recoverable deletion confirmation is required')
        if not isinstance(preview_token, str) or len(preview_token) != 64:
            _fail('stale_preview', 'A current deletion preview is required')
        from hermes_cli.plugin_memory import memory_owner, publish_memory
        owner = memory_owner(version=1)
        def delete_record():
            with _transaction(owner, write=True) as (store, data, chat):
                record = _owned_record(store, data, chat, record_id)
                store._expected(record, expected_revision)
                preview = _deletion_preview(owner, store, data, chat, record_id)
                if not hmac.compare_digest(preview_token, preview['preview_token']):
                    _fail('stale_preview', 'Deletion preview changed; explicitly review a new preview')
                recovery_id, when = 'recovery_' + uuid.uuid4().hex, _now()
                ids = preview['affected_record_ids']
                envelope = dict(id=recovery_id, store_id=data['store_id'], scope_id=chat, deleted_at=when,
                                records={key: deepcopy(data['records'][key]) for key in ids},
                                tombstone_revisions={key: data['records'][key]['revision'] + 1 for key in ids})
                envelope['digest'] = _digest(envelope)
                trash = data.setdefault('private_trash', {'schema': 1, 'items': {}})['items']
                if recovery_id in trash:
                    _fail('revision_conflict', 'Generated recovery identity collided')
                trash[recovery_id] = envelope
                for key in ids:
                    data['records'].pop(key)
                    data['tombstones'][key] = dict(id=key, scope_id=chat,
                        revision=envelope['tombstone_revisions'][key], deleted_at=when)
                return {'deleted_ids': ids, 'recovery_id': recovery_id,
                        'retention': 'until_restore_no_purge', 'purge_available': False,
                        'retained_copy': True, 'recall_removed': True}
        return publish_memory(owner, delete_record)

    def trash(self, *, limit=16, before=None):
        if type(limit) is not int or not 1 <= limit <= 32:
            _fail('invalid_payload', 'Trash limit must be an integer from one to thirty-two')
        if before is not None:
            _id(before)
        from hermes_cli.plugin_memory import memory_owner, read_memory
        owner = memory_owner(version=1)
        def inspect_trash():
            with _transaction(owner) as (_, data, chat):
                items = sorted((item for item in _trash_items(data).values() if item['scope_id'] == chat),
                               key=lambda item: (item['deleted_at'], item['id']), reverse=True)
                if before is not None:
                    positions = [index for index, item in enumerate(items) if item['id'] == before]
                    if not positions:
                        _fail('stale_preview', 'Trash cursor is unavailable; refresh the current chat trash list')
                    items = items[positions[0] + 1:]
                page = items[:limit]
                result = []
                for item in page:
                    ids = sorted(item['records'])
                    result.append({'recovery_id': item['id'], 'deleted_at': item['deleted_at'],
                                   'record_count': len(ids), 'record_ids': ids[:8],
                                   'record_ids_truncated': len(ids) > 8})
                truncated = len(items) > limit
                return {'items': result, 'truncated': truncated,
                        'next_before': page[-1]['id'] if page and truncated else None,
                        'retention': 'until_restore_no_purge', 'purge_available': False}
        return read_memory(owner, inspect_trash)

    def restore(self, recovery_id, *, confirm=False):
        if confirm is not True:
            _fail('confirmation_required', 'Explicit private recovery confirmation is required')
        from hermes_cli.plugin_memory import memory_owner, publish_memory
        owner = memory_owner(version=1)
        def restore_records():
            with _transaction(owner, write=True) as (store, data, chat):
                _id(recovery_id)
                envelope = _trash_items(data).get(recovery_id)
                if envelope is None or envelope['scope_id'] != chat:
                    _fail('record_not_found', 'Recovery is not available for the current private chat')
                restored = _restore_payload(store, data, chat, envelope)
                from .private_sources_v1 import require_active_sources
                for record in restored.values():
                    require_active_sources(data, record)
                data['records'].update(restored)
                for key in restored:
                    data['tombstones'].pop(key)
                data['private_trash']['items'].pop(recovery_id)
                return {'restored_ids': sorted(restored), 'records': [{'id': item['id'], 'revision': item['revision'], 'state': item['state']}
                                    for item in restored.values()],
                        'retained_copy': False, 'state': 'pending', 'approval_required': True}
        return publish_memory(owner, restore_records)

    def recall(self, *, limit=10):
        if type(limit) is not int or not 1 <= limit <= 20:
            _fail('invalid_payload', 'Recall limit must be an integer from one to twenty')
        from hermes_cli.plugin_memory import memory_owner, read_memory
        owner = memory_owner(version=1)
        def read():
            with _transaction(owner) as (_, data, chat):
                # Never invoke generic incoming-policy/grant expansion. Revision-pinned
                # dependencies and sensitive/user-inference exclusions still apply.
                from .private_sources_v1 import sources_active
                records = recall_records([deepcopy(record) for record in data['records'].values()
                                          if record['scope_id'] == chat and sources_active(data, record)])
                records.sort(key=lambda record: (record['updated_at'], record['id']), reverse=True)
                result = {'chat_revision': _chat_revision(data, chat), 'records': [], 'truncated': False,
                          'content_role': 'untrusted_memory_data', 'private_chat_only': True,
                          'project_read_authorized': False, 'workspace_read_authorized': False,
                          'source_status': 'declared_provenance_not_independently_verified'}
                for record in records:
                    if len(result['records']) >= limit:
                        result['truncated'] = True
                        break
                    result['records'].append(record)
                    if len(json.dumps(result, ensure_ascii=True).encode()) > _MAX_OUTPUT_BYTES:
                        result['records'].pop()
                        result['truncated'] = True
                        break
                return result
        return read_memory(owner, read)
