"""Explicit per-chat consent for a separate principal-qualified project record store.

Selection is not consent. No legacy/private adoption, native project ACL assumption,
model tools, or provider injection. Native fences must enclose every store operation.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
import hmac
from pathlib import Path
from functools import wraps
import json
import os
import secrets
import threading
import time
import uuid

from .private_workspace_v2 import _digest, _fail, _authored_fields, _retained_record
from .workspace_records import RecordError, RecordStore, recall_records, _now, _id

_OWNER = 'elm-project-workspace-v1'
_MAX_BYTES = 4 * 1024 * 1024
_MAX_RECORDS = 512
_MAX_CONSENTS = 512


def _project_authored_fields(*args, **kwargs):
    fields = _authored_fields(*args, **kwargs)
    if any(source['ref'].startswith('elm-snapshot-v1:') for source in fields['sources']):
        _fail('private_source_reference', 'Private captured-source references cannot be authored into project records')
    return fields


def _chat(owner):
    return _digest([1, owner.profile_id, owner.principal_id, owner.canonical_session_id])


def _scope(owner):
    return 'project:' + _digest([1, owner.profile_id, owner.principal_id, owner.project_id, owner.project_fingerprint])


def _empty():
    return dict(revision=0, granted=False, project_id=None, binding_revision=0, fingerprint=None, policy_version=1)


def _consent(data, owner):
    item = data.get('project_consents', {}).get('items', {}).get(_chat(owner), _empty())
    return {**item, 'policy_version': item.get('policy_version', 1)}


def _expected_consent(data, owner, revision):
    if type(revision) is not int or revision != _consent(data, owner)['revision']:
        _fail('consent_changed', 'Project consent changed; refresh and explicitly review again')


def _authorized(consent, owner):
    return (consent['granted'] and owner.project_id is not None
            and consent['project_id'] == owner.project_id
            and consent['binding_revision'] == owner.project_revision
            and consent['fingerprint'] == owner.project_fingerprint)


def _trash_items(data):
    return data.get('project_trash', {}).get('items', {})


def _record_count(data):
    return len(data['records']) + sum(len(item['records']) for item in _trash_items(data).values())


def _project_revision(data, scope):
    active = sorted((r['id'], r['revision'], r['state']) for r in data['records'].values() if r['scope_id'] == scope)
    tombstones = sorted((r['id'], r['revision']) for r in data['tombstones'].values() if r['scope_id'] == scope)
    recoveries = sorted(k for k, v in _trash_items(data).items() if v['scope_id'] == scope)
    return _digest([scope, active, tombstones, recoveries])


def _owned_record(store, data, chat, record_id):
    _id(record_id)
    record = data['records'].get(record_id)
    if record is None or record['scope_id'] != chat:
        _fail('record_not_found', 'Record is not owned by the current project generation')
    return record


def _owned_closure(store, data, chat, record_id):
    _owned_record(store, data, chat, record_id)
    ids = {record_id} | store._dependents(data, {record_id})
    if any(data['records'][item]['scope_id'] != chat for item in ids):
        _fail('sharing_denied', 'Lifecycle changes cannot cross project-generation ownership')
    return sorted(ids)


def _deletion_preview(owner, store, data, chat, record_id):
    record = _owned_record(store, data, chat, record_id)
    ids = _owned_closure(store, data, chat, record_id)
    material = {'owner': asdict(owner), 'store_id': data['store_id'], 'project_scope': chat,
                'consent': deepcopy(_consent(data, owner)), 'record_id': record_id, 'records': [data['records'][key] for key in ids]}
    return {'record_id': record_id, 'expected_revision': record['revision'],
            'preview_token': _digest(material), 'affected_record_ids': ids, 'consent_revision': _consent(data, owner)['revision'], 'context_key': _context_key(owner, _consent(data, owner), data['store_id']),
            'retention': 'until_restore_no_purge', 'purge_available': False,
            'notice': 'Deletion removes recall access but retains full bodies privately until restore; no permanent purge is provided.'}


def _restore_payload(store, data, chat, envelope):
    restored = deepcopy(envelope['records'])
    revisions = {key: envelope['tombstone_revisions'][key] + 1 for key in restored}
    for record_id, record in restored.items():
        if record['scope_id'] != chat or record_id in data['records']:
            _fail('record_not_found', 'Recovery is not available for the current project generation')
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


class _ProjectStore(RecordStore):
    def _validate_manifest(self, data):
        super()._validate_manifest({k: v for k, v in data.items() if k not in ('project_consents', 'project_trash', 'reference_drafts')})
        if data['grants']:
            raise ValueError('Project lane refuses generic grants')
        if _record_count(data) > _MAX_RECORDS or len(data['scopes']) > _MAX_RECORDS:
            raise ValueError('Project record limit')
        for scope in data['scopes'].values():
            if scope['kind'] != 'workspace' or scope.get('private') is not True or 'read_policy' in scope:
                raise ValueError('Invalid project scope')
        self._validate_trash(data)
        from .reference_drafts import validate_drafts
        validate_drafts(data)
        all_records = dict(data['records'])
        for envelope in _trash_items(data).values():
            all_records.update(envelope['records'])
        for record in all_records.values():
            for dep in record['dependencies']:
                target = all_records.get(dep['id'])
                if target is None or target['scope_id'] != record['scope_id']:
                    raise ValueError('Project dependencies cannot cross scope generations')
        extension = data.get('project_consents')
        if extension is None:
            return
        if (type(extension) is not dict or set(extension) != {'schema', 'items'}
                or type(extension['schema']) is not int or extension['schema'] != 1
                or type(extension['items']) is not dict or len(extension['items']) > _MAX_CONSENTS):
            raise ValueError('Invalid project consent schema')
        for key, item in extension['items'].items():
            if (type(key) is not str or len(key) != 64 or any(c not in '0123456789abcdef' for c in key)
                    or type(item) is not dict or set(item) not in (set(_empty()), set(_empty()) - {'policy_version'})
                    or type(item.get('policy_version', 1)) is not int or item.get('policy_version', 1) not in (1, 2)
                    or type(item['revision']) is not int or item['revision'] < 1
                    or type(item['granted']) is not bool
                    or type(item['binding_revision']) is not int or item['binding_revision'] < 0):
                raise ValueError('Invalid project consent')
            if item['project_id'] is not None and (type(item['project_id']) is not str or not item['project_id']):
                raise ValueError('Invalid consent project')
            fp = item['fingerprint']
            if fp is not None and (type(fp) is not str or len(fp) != 64 or any(c not in '0123456789abcdef' for c in fp)):
                raise ValueError('Invalid consent fingerprint')
            if item['granted'] and (item['project_id'] is None or fp is None or item['binding_revision'] < 1):
                raise ValueError('Unbound grant')


    def _validate_trash(self, data):
        trash = data.get('project_trash', {'schema': 1, 'items': {}})
        if (type(trash) is not dict or set(trash) != {'schema', 'items'}
                or type(trash['schema']) is not int or trash['schema'] != 1 or type(trash['items']) is not dict):
            raise ValueError('Invalid project trash schema')
        retained = set()
        for recovery_id, item in trash['items'].items():
            self._validate_envelope(data, recovery_id, item, retained)
        if retained != set(data['tombstones']):
            raise ValueError('Project tombstones require exact retained recovery bodies')

    def _validate_envelope(self, data, recovery_id, item, retained):
        _id(recovery_id)
        fields = {'id', 'store_id', 'scope_id', 'deleted_at', 'records', 'tombstone_revisions', 'digest'}
        if (not isinstance(item, dict) or set(item) != fields or item['id'] != recovery_id
                or item['store_id'] != data['store_id'] or not isinstance(item['records'], dict)
                or not item['records'] or not isinstance(item['tombstone_revisions'], dict)
                or set(item['records']) != set(item['tombstone_revisions'])):
            raise ValueError('Invalid project recovery envelope')
        if item['digest'] != _digest({key: value for key, value in item.items() if key != 'digest'}):
            raise ValueError('Project recovery checksum mismatch')
        scope = data['scopes'].get(item['scope_id'])
        if not scope or scope['kind'] != 'workspace' or scope['private'] is not True or 'read_policy' in scope:
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
                raise ValueError('Project recovery tombstone mismatch')
            retained.add(record_id)
            if record_id in self._ancestors({'records': item['records']}, record_id):
                raise ValueError('Project recovery dependency cycle')


def _paths(owner):
    from hermes_constants import get_hermes_home
    home = Path(get_hermes_home()).resolve()
    if not Path(owner.profile_id).is_absolute() or Path(owner.profile_id).resolve() != home:
        _fail('scope_changed', 'Authenticated project profile does not match current profile')
    namespace = _digest([1, owner.profile_id, owner.principal_id])
    base, root = home / _OWNER, home / _OWNER / namespace
    records = root / 'records'
    if any(p.is_symlink() for p in (base, root, records, root / 'owner.json', records / 'manifest.json',
                                    records / '.records.lock', records / '.manifest.next')):
        _fail('unowned_root', 'Project memory refuses symlinked ownership paths')
    if root.resolve().parent != base.resolve() or base.resolve().parent != home:
        _fail('unowned_root', 'Project memory root escaped authenticated profile')
    return root, _ProjectStore(records), namespace


def _marker(root, namespace, store_id):
    try:
        marker = json.loads((root / 'owner.json').read_text(encoding='utf-8'))
    except (OSError, ValueError, UnicodeError) as exc:
        raise RecordError('unowned_root', 'Project ownership marker is missing or unreadable') from exc
    if marker != dict(owner=_OWNER, schema=1, namespace=namespace, store_id=store_id):
        _fail('unowned_root', 'Project ownership marker does not match principal store')


@contextmanager
def _transaction(owner, *, write=False, access=False):
    root, store, namespace = _paths(owner)
    if not root.exists():
        _fail('not_initialized', 'Explicit project consent initialization is required')
    try:
        if (store.root / 'manifest.json').stat().st_size > _MAX_BYTES:
            _fail('store_limit', 'Project memory exceeds bounded store capacity')
        with store._transaction(write=write) as data:
            _marker(root, namespace, data['store_id'])
            if access:
                scope = data['scopes'].get(_scope(owner))
                if (not _authorized(_consent(data, owner), owner) or scope is None
                        or scope['kind'] != 'workspace' or scope['private'] is not True or 'read_policy' in scope):
                    _fail('consent_required', 'Current chat needs explicit consent for this exact project binding')
                if access == 'expanded' and _consent(data, owner)['policy_version'] < 2:
                    _fail('consent_upgrade_required', 'Explicit expanded project inspection and lifecycle consent is required')
            yield store, data
            _paths(owner)
            _marker(root, namespace, data['store_id'])
            if write:
                store._validate_manifest(data)
                pending = dict(data, revision=data['revision'] + 1)
                if len(json.dumps(pending, ensure_ascii=False, indent=2, allow_nan=False).encode()) + 1 > _MAX_BYTES:
                    _fail('store_limit', 'Project memory capacity exceeded; no change saved')
    except OSError as exc:
        raise RecordError('store_unavailable', 'Project memory storage is unavailable') from exc


def _context_key(owner, consent, store_id):
    return _digest([asdict(owner), consent, store_id])


def _status(owner, consent, initialized, store_id=None):
    return dict(context_key=_context_key(owner, consent, store_id), initialized=initialized, consent_revision=consent['revision'],
                consent_granted=consent['granted'], project_read_authorized=_authorized(consent, owner),
                selected_project_id=owner.project_id, project_binding_revision=owner.project_revision, provider_recall='not_connected',
                consent_version=consent['policy_version'], reconsent_required=consent['policy_version'] < 2,
                permissions=(['recall', 'create', 'approve'] + (['inspect', 'correct', 'delete', 'restore'] if consent['policy_version'] >= 2 else [])) if _authorized(consent, owner) else [],
                migration='no_legacy_or_private_adoption', cross_principal_sharing=False)


def _snapshot(owner):
    root, _, _ = _paths(owner)
    if not root.exists():
        return _empty(), False, None
    with _transaction(owner) as (_, data):
        return deepcopy(_consent(data, owner)), True, data['store_id']


def _initialize(owner):
    root, store, namespace = _paths(owner)
    if root.exists():
        _fail('already_initialized', 'Existing project roots are never adopted or replaced')
    try:
        root.parent.mkdir(exist_ok=True)
        root.mkdir()
        store.initialize()
        with store._transaction() as data:
            marker = dict(owner=_OWNER, schema=1, namespace=namespace, store_id=data['store_id'])
            with (root / 'owner.json').open('x', encoding='utf-8') as stream:
                json.dump(marker, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
    except OSError as exc:
        raise RecordError('store_unavailable', 'Project initialization incomplete; no automatic adoption or retry') from exc


def _admitted(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        # Close linearizes after admitted native work. Do not re-enter this service
        # from a native callback. Expiry never cancels an admitted mutation.
        with self._lock:
            self._live()
            return method(self, *args, **kwargs)
    return call


class ProjectWorkspaceV1:
    def __init__(self):
        self._lock = threading.Lock()
        self._previews = {}
        self._active = True

    def close(self):
        with self._lock:
            self._active = False
            self._previews.clear()

    def _live(self):
        if not self._active:
            _fail('context_expired', 'Project workflow is no longer active')

    def status(self):
        from hermes_cli.plugin_memory import memory_owner, read_memory
        owner = memory_owner(version=1)
        with self._lock:
            self._live()
            return read_memory(owner, lambda: _status(owner, *_snapshot(owner)))

    def consent_preview(self, *, action):
        if action not in ('grant', 'revoke'):
            _fail('invalid_payload', 'Consent action must be grant or revoke')
        from hermes_cli.plugin_memory import memory_owner, read_memory
        owner = memory_owner(version=1)
        if action == 'grant' and owner.project_id is None:
            _fail('project_required', 'Select an exact native project before granting consent')
        with self._lock:
            self._live()
            consent, initialized, store_id = read_memory(owner, lambda: _snapshot(owner))
            now = time.monotonic()
            self._previews = {k: v for k, v in self._previews.items() if v[0] > now}
            if len(self._previews) >= 256:
                _fail('preview_limit', 'Too many outstanding project consent previews')
            token = secrets.token_urlsafe(32)
            self._previews[token] = (now + 300, owner, consent, initialized, action, store_id)
            return dict(preview_token=token, action=action, expires_in_seconds=300,
                        target_project_id=owner.project_id if action == 'grant' else consent['project_id'],
                        consent_revision=consent['revision'], initializes_store=not initialized and action == 'grant',
                        notice=('Grant permits this chat to read eligible records previously contributed under consent by chats of this same principal/project generation, create and approve pending project records, inspect full pending and sensitive records, correct contributions, recoverably delete them, and restore them pending. These expanded rights apply to all contributions in this same-principal project generation. Revoking another chat does not remove its contributions. No other principal, private record or legacy tree is included.'
                                if action == 'grant' else 'Revoke this chat consent only; project records remain retained for independently consenting chats.'))

    def consent_apply(self, preview_token, *, confirm=False):
        if confirm is not True:
            _fail('confirmation_required', 'Explicit consent confirmation is required')
        if type(preview_token) is not str or len(preview_token) > 128:
            _fail('stale_preview', 'Consent preview is unavailable')
        from hermes_cli.plugin_memory import memory_owner, publish_memory
        owner = memory_owner(version=1)
        with self._lock:
            self._live()
            preview = self._previews.get(preview_token)
            if preview is None:
                _fail('stale_preview', 'Consent preview is unavailable; preview again')
            deadline, expected, prior, initialized, action, store_id = preview
            if (owner.profile_id, owner.principal_id, owner.canonical_session_id) != (expected.profile_id, expected.principal_id, expected.canonical_session_id):
                _fail('stale_preview', 'Consent preview is not owned by this chat')
            del self._previews[preview_token]
            if time.monotonic() >= deadline or owner != expected:
                _fail('stale_preview', 'Consent context changed or expired; preview again')
            def apply():
                current, exists, current_store = _snapshot(owner)
                if current != prior or exists != initialized or current_store != store_id:
                    _fail('stale_preview', 'Consent changed; preview again')
                if not exists:
                    if action == 'revoke':
                        return _status(owner, _empty(), False)
                    _initialize(owner)
                with _transaction(owner, write=True) as (_, data):
                    if _consent(data, owner) != prior or (initialized and data['store_id'] != store_id):
                        _fail('stale_preview', 'Consent changed; preview again')
                    item = dict(revision=prior['revision'] + 1, granted=action == 'grant',
                                project_id=owner.project_id if action == 'grant' else prior['project_id'],
                                binding_revision=owner.project_revision if action == 'grant' else prior['binding_revision'],
                                fingerprint=owner.project_fingerprint if action == 'grant' else prior['fingerprint'],
                                policy_version=2 if action == 'grant' else prior['policy_version'])
                    data.setdefault('project_consents', dict(schema=1, items={}))['items'][_chat(owner)] = item
                    if action == 'grant':
                        scope = _scope(owner)
                        data['scopes'].setdefault(scope, dict(id=scope, kind='workspace', label='Consented project', private=True))
                    return _status(owner, item, True, data['store_id'])
            return publish_memory(owner, apply)

    @_admitted
    def create_pending(self, *, title, text, sources, domain='work', kind='reference', basis='source_document', topic='facts', sensitive=False, expected_consent_revision=None):
        fields = _project_authored_fields(title, text, sources, domain, kind, basis, topic, sensitive)
        from hermes_cli.plugin_memory import memory_owner, publish_memory
        owner = memory_owner(version=1)
        def create():
            with _transaction(owner, write=True, access=True) as (store, data):
                if expected_consent_revision is not None:
                    _expected_consent(data, owner, expected_consent_revision)
                if _record_count(data) >= _MAX_RECORDS:
                    _fail('store_limit', 'Project record capacity reached')
                record_id, now = 'rec_' + uuid.uuid4().hex, _now()
                if record_id in data['records'] or record_id in data['tombstones']:
                    _fail('revision_conflict', 'Generated record identity collided')
                record = dict(id=record_id, revision=1, scope_id=_scope(owner), **fields, created_at=now, updated_at=now)
                store._dependencies(data, record)
                data['records'][record_id] = record
                return deepcopy(record)
        return publish_memory(owner, create)

    @_admitted
    def approve(self, record_id, expected_revision, *, confirm=False, expected_consent_revision=None):
        if confirm is not True:
            _fail('confirmation_required', 'Explicit pending-record approval is required')
        from hermes_cli.plugin_memory import memory_owner, publish_memory
        owner = memory_owner(version=1)
        def approve_record():
            with _transaction(owner, write=True, access=True) as (store, data):
                if expected_consent_revision is not None:
                    _expected_consent(data, owner, expected_consent_revision)
                _id(record_id)
                record = data['records'].get(record_id)
                if record is None or record['scope_id'] != _scope(owner):
                    _fail('record_not_found', 'Record is not owned by this consented project generation')
                store._expected(record, expected_revision)
                _owned_closure(store, data, _scope(owner), record_id)
                if record['state'] != 'pending':
                    _fail('invalid_state', 'Only pending records can be approved')
                store._dependencies(data, record)
                record.update(state='approved', revision=record['revision'] + 1, updated_at=_now())
                store._invalidate(data, {record_id})
                store._reconcile_visibility(data)
                return deepcopy(record)
        return publish_memory(owner, approve_record)

    @_admitted
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
            with _transaction(owner, access='expanded') as (_, data):
                chat = _scope(owner)
                records = sorted((record for record in data['records'].values()
                                  if record['scope_id'] == chat and (state == 'all' or record['state'] == state)),
                                 key=lambda record: (record['updated_at'], record['id']), reverse=True)
                if before is not None:
                    positions = [index for index, record in enumerate(records) if record['id'] == before]
                    if not positions:
                        _fail('stale_preview', 'Inspection cursor is unavailable; refresh this chat list')
                    records = records[positions[0] + 1:]
                fields = ('id', 'revision', 'title', 'state', 'domain', 'kind', 'basis', 'topic', 'sensitive', 'updated_at')
                result = {'records': [], 'project_revision': _project_revision(data, chat),
                          'truncated': False, 'next_before': None, 'inspection_only': True, 'consent_revision': _consent(data, owner)['revision'], 'context_key': _context_key(owner, _consent(data, owner), data['store_id'])}
                for record in records[:limit]:
                    result['records'].append({key: record[key] for key in fields})
                    if len(json.dumps(result, ensure_ascii=True).encode()) > 32768 - 256:
                        result['records'].pop()
                        break
                result['truncated'] = len(records) > len(result['records'])
                if records and not result['records']:
                    _fail('inspection_limit', 'Record summary exceeds this inspection response limit')
                if result['records'] and result['truncated']:
                    result['next_before'] = result['records'][-1]['id']
                return result
        return read_memory(owner, inspect_records)

    @_admitted
    def get(self, record_id):
        """Return one full human-reviewed record or refuse; never silently truncate evidence."""
        from hermes_cli.plugin_memory import memory_owner, read_memory
        owner = memory_owner(version=1)
        def inspect_record():
            with _transaction(owner, access='expanded') as (store, data):
                chat = _scope(owner)
                record = _owned_record(store, data, chat, record_id)
                eligible = recall_records([item for item in data['records'].values() if item['scope_id'] == chat])
                result = {'record': deepcopy(record), 'recall_eligible': any(item['id'] == record_id for item in eligible),
                          'inspection_only': True, 'content_role': 'untrusted_memory_data', 'consent_revision': _consent(data, owner)['revision'], 'context_key': _context_key(owner, _consent(data, owner), data['store_id'])}
                if len(json.dumps(result, ensure_ascii=True).encode()) > 65536:
                    _fail('inspection_limit', 'Full record exceeds this inspection response limit; no partial review was returned')
                return result
        return read_memory(owner, inspect_record)

    @_admitted
    def correct(self, record_id, expected_revision, changes, *, expected_consent_revision, confirm=False):
        allowed = {'title', 'text', 'sources', 'domain', 'kind', 'basis', 'topic', 'sensitive'}
        if confirm is not True:
            _fail('confirmation_required', 'Explicit record correction confirmation is required')
        if not isinstance(changes, dict) or not changes or not set(changes) <= allowed:
            _fail('invalid_changes', 'Corrections accept authored fields only, never scope, state or dependencies')
        from hermes_cli.plugin_memory import memory_owner, publish_memory
        owner = memory_owner(version=1)
        def correct_record():
            with _transaction(owner, write=True, access='expanded') as (store, data):
                _expected_consent(data, owner, expected_consent_revision)
                chat = _scope(owner)
                previous = _owned_record(store, data, chat, record_id)
                store._expected(previous, expected_revision)
                _owned_closure(store, data, chat, record_id)
                proposed = {**previous, **deepcopy(changes)}
                fields = _project_authored_fields(**{key: proposed[key] for key in allowed})
                fields['dependencies'] = deepcopy(previous['dependencies'])
                record = {**previous, **fields, 'revision': previous['revision'] + 1, 'updated_at': _now()}
                store._dependencies(data, record)
                data['records'][record_id] = record
                store._invalidate(data, {record_id})
                store._reconcile_visibility(data)
                return deepcopy(record)
        return publish_memory(owner, correct_record)

    @_admitted
    def delete_preview(self, record_id):
        from hermes_cli.plugin_memory import memory_owner, read_memory
        owner = memory_owner(version=1)
        def preview():
            with _transaction(owner, access='expanded') as (store, data):
                chat = _scope(owner)
                return _deletion_preview(owner, store, data, chat, record_id)
        return read_memory(owner, preview)

    @_admitted
    def delete(self, record_id, expected_revision, preview_token, *, expected_consent_revision, confirm=False):
        if confirm is not True:
            _fail('confirmation_required', 'Explicit recoverable deletion confirmation is required')
        if not isinstance(preview_token, str) or len(preview_token) != 64:
            _fail('stale_preview', 'A current deletion preview is required')
        from hermes_cli.plugin_memory import memory_owner, publish_memory
        owner = memory_owner(version=1)
        def delete_record():
            with _transaction(owner, write=True, access='expanded') as (store, data):
                _expected_consent(data, owner, expected_consent_revision)
                chat = _scope(owner)
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
                trash = data.setdefault('project_trash', {'schema': 1, 'items': {}})['items']
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

    @_admitted
    def trash(self, *, limit=16, before=None):
        if type(limit) is not int or not 1 <= limit <= 32:
            _fail('invalid_payload', 'Trash limit must be an integer from one to thirty-two')
        if before is not None:
            _id(before)
        from hermes_cli.plugin_memory import memory_owner, read_memory
        owner = memory_owner(version=1)
        def inspect_trash():
            with _transaction(owner, access='expanded') as (_, data):
                chat = _scope(owner)
                items = sorted((item for item in _trash_items(data).values() if item['scope_id'] == chat),
                               key=lambda item: (item['deleted_at'], item['id']), reverse=True)
                if before is not None:
                    positions = [index for index, item in enumerate(items) if item['id'] == before]
                    if not positions:
                        _fail('stale_preview', 'Trash cursor is unavailable; refresh the current project generation trash list')
                    items = items[positions[0] + 1:]
                page = items[:limit]
                result = []
                for item in page:
                    ids = sorted(item['records'])
                    result.append({'recovery_id': item['id'], 'deleted_at': item['deleted_at'],
                                   'record_count': len(ids), 'record_ids': ids[:8],
                                   'record_ids_truncated': len(ids) > 8})
                truncated = len(items) > limit
                return {'items': result, 'truncated': truncated, 'consent_revision': _consent(data, owner)['revision'], 'context_key': _context_key(owner, _consent(data, owner), data['store_id']),
                        'next_before': page[-1]['id'] if page and truncated else None,
                        'retention': 'until_restore_no_purge', 'purge_available': False}
        return read_memory(owner, inspect_trash)

    @_admitted
    def restore(self, recovery_id, *, expected_consent_revision, confirm=False):
        if confirm is not True:
            _fail('confirmation_required', 'Explicit project recovery confirmation is required')
        from hermes_cli.plugin_memory import memory_owner, publish_memory
        owner = memory_owner(version=1)
        def restore_records():
            with _transaction(owner, write=True, access='expanded') as (store, data):
                _expected_consent(data, owner, expected_consent_revision)
                chat = _scope(owner)
                _id(recovery_id)
                envelope = _trash_items(data).get(recovery_id)
                if envelope is None or envelope['scope_id'] != chat:
                    _fail('record_not_found', 'Recovery is not available for the current project generation')
                restored = _restore_payload(store, data, chat, envelope)
                data['records'].update(restored)
                for key in restored:
                    data['tombstones'].pop(key)
                data['project_trash']['items'].pop(recovery_id)
                return {'restored_ids': sorted(restored), 'records': [{'id': item['id'], 'revision': item['revision'], 'state': item['state']}
                                    for item in restored.values()],
                        'retained_copy': False, 'state': 'pending', 'approval_required': True}
        return publish_memory(owner, restore_records)

    @_admitted
    def recall(self, *, limit=6):
        if type(limit) is not int or not 1 <= limit <= 20:
            _fail('invalid_payload', 'Recall limit must be one to twenty')
        from hermes_cli.plugin_memory import memory_owner, read_memory
        owner = memory_owner(version=1)
        def read():
            with _transaction(owner, access=True) as (_, data):
                records = recall_records([r for r in data['records'].values() if r['scope_id'] == _scope(owner)])
                result = dict(records=[], content_role='untrusted_memory_data', project_read_authorized=True,
                              consent_revision=_consent(data, owner)['revision'], provider_recall='not_connected',
                              provenance='declared_sources_not_verified', truncated=False)
                for record in records[:limit]:
                    result['records'].append(deepcopy(record))
                    if len(json.dumps(result, ensure_ascii=True).encode()) > 32768 - 128:
                        result['records'].pop()
                        break
                result['truncated'] = len(records) > len(result['records'])
                return result
        return read_memory(owner, read)
