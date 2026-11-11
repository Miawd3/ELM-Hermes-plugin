"""Profile-owned authored records; no retrieval, model tools or executable skills.

The inspectable JSON manifest embeds the current source records so records,
scopes and governance commit in ONE atomic replacement. There are no historical
content copies or indexes here. Host adapters authenticate identities and must
scope exact reads using snapshot/visible_records; get() is a human-store API.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import uuid


class RecordError(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(message)


def _fail(code, message):
    raise RecordError(code, message)


def _string(value, name, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or '\x00' in value:
        _fail('invalid_value', f'{name} must be a nonempty string of at most {limit} characters')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError as exc:
        raise RecordError('invalid_value', f'{name} must be valid UTF-8 text') from exc
    return value


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', value):
        _fail('invalid_id', 'Identifier must be 1-128 ASCII letters, digits, dot, colon, dash or underscore')
    return value


def _now():
    return datetime.now(timezone.utc).isoformat()


def recall_eligible(record):
    """Model-facing type restriction, not human inspection or collection consent."""
    return (record['state'] == 'approved' and record['sensitive'] is False
            and (record['domain'] != 'user' or
                 (record['topic'] == 'communication' and record['basis'] == 'explicit_statement'
                  and record['kind'] in ('explicit_fact', 'preference'))))


def recall_records(records):
    """Narrow an already scope-authorized snapshot, including its provenance DAG.

    A visible summary cannot launder a withheld source. No foreign body fetch,
    grant inference, relabeling or change to the durable human inspector records.
    """
    by_id = {r['id']: r for r in records}
    dependents = {}
    denied = {r['id'] for r in records if not recall_eligible(r)}
    for record in records:
        for dep in record['dependencies']:
            dependents.setdefault(dep['id'], []).append(record['id'])
            if dep['id'] not in by_id or by_id[dep['id']]['revision'] != dep['revision']:
                denied.add(record['id'])
    pending = list(denied)
    while pending:
        for child in dependents.get(pending.pop(), []):
            if child not in denied:
                denied.add(child)
                pending.append(child)
    return [r for r in records if r['id'] not in denied]


class RecordStore:
    """Explicitly initialized local repository with nonblocking OS-owned locks.

    A contending caller gets store_busy, never a silent mutation retry. Killing
    a process releases its file lock. The lock inode is never removed/replaced.
    Filesystem permissions are the host's responsibility, not a security sandbox.
    """
    def __init__(self, root: Path):
        self.root = Path(root)
        if not self.root.is_absolute():
            _fail('invalid_root', 'An explicit absolute profile-local root is required')

    @contextmanager
    def _locked(self, *, create=False):
        try:
            stream = (self.root / '.records.lock').open('a+b' if create else 'r+b')
        except OSError as exc:
            raise RecordError('storage_error', 'Cannot open record lock') from exc
        locked = False
        try:
            if os.name == 'nt':
                import msvcrt
                stream.seek(0)
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    raise RecordError('store_busy', 'Another record operation owns the store lock') from exc
            else:
                import fcntl
                try:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise RecordError('store_busy', 'Another record operation owns the store lock') from exc
            locked = True
            yield
        finally:
            if locked:
                if os.name == 'nt':
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            stream.close()

    def _load(self):
        path = self.root / 'manifest.json'
        if not path.exists():
            _fail('not_initialized', 'Explicit fresh-store initialization is required')
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if (data['owner'] != 'elm-workspace-records' or type(data['schema']) is not int
                    or data['schema'] != 1 or type(data['revision']) is not int or data['revision'] < 0
                    or any(not isinstance(data[key], dict) for key in ('scopes', 'records', 'tombstones'))
                    or not isinstance(data['grants'], list)):
                raise ValueError('Invalid schema')
            self._validate_manifest(data)
            return data
        except (OSError, ValueError, KeyError, TypeError, AttributeError, RecordError, RecursionError) as exc:
            raise RecordError('corrupt_store', 'Record manifest is unreadable or has an unsupported schema; no repair attempted') from exc

    def _validate_manifest(self, data):
        if (set(data) != {'owner', 'schema', 'revision', 'store_id', 'scopes', 'records', 'grants', 'tombstones'}
                or not isinstance(data['store_id'], str) or not re.fullmatch(r'[0-9a-f]{32}', data['store_id'])):
            raise ValueError('Invalid store identity or fields')
        for scope_id, scope in data['scopes'].items():
            _id(scope_id)
            if (not {'id', 'kind', 'label', 'private'} <= set(scope)
                    or not set(scope) <= {'id', 'kind', 'label', 'private', 'read_policy'} or scope['id'] != scope_id
                    or scope['kind'] not in ('personal', 'workspace', 'chat') or type(scope['private']) is not bool):
                raise ValueError('Invalid scope')
            _string(scope['label'], 'label', 256)
            if 'read_policy' in scope:
                policy = scope['read_policy']
                if (scope['kind'] != 'chat' or scope['private'] is not True
                        or not isinstance(policy, dict) or set(policy) != {'revision', 'workspace_scope_id'}
                        or not isinstance(policy['revision'], str)
                        or re.fullmatch('[0-9a-f]{32}', policy['revision']) is None
                        or (policy['workspace_scope_id'] is not None and
                            data['scopes'].get(policy['workspace_scope_id'], {}).get('kind') != 'workspace')):
                    raise ValueError('Invalid directional read policy')
        authored = {'title', 'text', 'domain', 'kind', 'basis', 'sources', 'topic', 'state', 'dependencies', 'sensitive'}
        for record_id, record in data['records'].items():
            _id(record_id)
            if (set(record) != authored | {'id', 'revision', 'scope_id', 'created_at', 'updated_at'}
                    or record['id'] != record_id or record['scope_id'] not in data['scopes']
                    or type(record['revision']) is not int or record['revision'] < 1):
                raise ValueError('Invalid record shape')
            self._fields(**{key: record[key] for key in authored})
            for key in ('created_at', 'updated_at'):
                _string(record[key], key, 128)
                if datetime.fromisoformat(record[key]).tzinfo is None:
                    raise ValueError('Missing timestamp timezone')
            deps = record['dependencies']
            seen = set()
            for dep in deps:
                if (set(dep) != {'id', 'revision'} or dep['id'] not in data['records']
                        or dep['id'] in seen or type(dep['revision']) is not int or dep['revision'] < 1):
                    raise ValueError('Invalid dependency')
                seen.add(dep['id'])
            pointers = {p for source in record['sources'] if (p := self._pointer(source['ref'])) is not None}
            if pointers != seen or record_id in self._ancestors(data, record_id):
                raise ValueError('Missing provenance or cyclic dependencies')
            pins = {dep['id']: dep['revision'] for dep in deps}
            for source in record['sources']:
                pointer = self._pointer(source['ref'])
                # Invalidated history pins the old revision, not the current body.
                if (pointer is not None and 'revision' in source
                        and source['revision'] != pins[pointer]):
                    raise ValueError('Source revision differs from dependency pin')
        if set(data['records']) & set(data['tombstones']):
            raise ValueError('Deleted record body retained')
        for record_id, tombstone in data['tombstones'].items():
            _id(record_id)
            if (set(tombstone) != {'id', 'scope_id', 'revision', 'deleted_at'} or tombstone['id'] != record_id
                    or tombstone['scope_id'] not in data['scopes'] or type(tombstone['revision']) is not int
                    or tombstone['revision'] < 1 or datetime.fromisoformat(tombstone['deleted_at']).tzinfo is None):
                raise ValueError('Invalid tombstone')
        grant_keys = set()
        for grant in data['grants']:
            if (set(grant) != {'source_scope', 'target_scope', 'record_id', 'record_revision'}
                    or grant['source_scope'] not in data['scopes'] or grant['target_scope'] not in data['scopes']
                    or grant['source_scope'] == grant['target_scope'] or type(grant['record_revision']) is not int
                    or not self._grant_valid(data, grant)):
                raise ValueError('Invalid grant')
            key = (grant['source_scope'], grant['target_scope'], grant['record_id'])
            if key in grant_keys:
                raise ValueError('Duplicate grant')
            grant_keys.add(key)
        for record in data['records'].values():
            if record['state'] == 'approved' and not self._is_visible(data, record, record['scope_id']):
                raise ValueError('Approved record has unavailable dependencies')

    def _save(self, data):
        # One exact owned staging name; never scan or delete unrelated files.
        path = self.root / '.manifest.next'
        try:
            with path.open('w', encoding='utf-8', newline='\n') as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(path, self.root / 'manifest.json')
            if os.name != 'nt':
                fd = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        except OSError as exc:
            raise RecordError('storage_error', 'Atomic record commit failed; inspect current revision before retrying') from exc
        finally:
            if path.exists():
                path.unlink()

    @contextmanager
    def _transaction(self, write=False):
        if not (self.root / 'manifest.json').exists():
            _fail('not_initialized', 'Explicit fresh-store initialization is required')
        with self._locked():
            data = self._load()
            yield data
            if write:
                data['revision'] += 1
                self._save(data)

    def initialize(self):
        if self.root.exists():
            names = {p.name for p in self.root.iterdir()}
            if 'manifest.json' in names:
                _fail('already_initialized', 'A store or manifest already exists; initialization never adopts it')
            if names - {'.records.lock'}:
                _fail('unowned_root', 'Initialization refuses a nonempty unrelated root')
        else:
            self.root.mkdir(parents=True, exist_ok=True)
        with self._locked(create=True):
            if (self.root / 'manifest.json').exists():
                _fail('already_initialized', 'Store was already initialized')
            if {p.name for p in self.root.iterdir()} - {'.records.lock'}:
                _fail('unowned_root', 'Initialization refuses a nonempty unrelated root')
            self._save(dict(owner='elm-workspace-records', schema=1, revision=0, store_id=uuid.uuid4().hex,
                            scopes={}, records={}, grants=[], tombstones={}))
        return self.status()

    def status(self):
        if not (self.root / 'manifest.json').exists():
            return {'schema': 1, 'revision': 0, 'initialized': False}
        with self._transaction() as data:
            return {'schema': 1, 'revision': data['revision'], 'initialized': True}

    @staticmethod
    def _scope(data, scope_id):
        _id(scope_id)
        if scope_id not in data['scopes']:
            _fail('scope_not_found', 'Scope does not exist in this store')
        return data['scopes'][scope_id]

    @staticmethod
    def _record(data, record_id):
        _id(record_id)
        if record_id not in data['records']:
            _fail('record_not_found', 'Record does not exist or has been deleted')
        return data['records'][record_id]

    def put_scope(self, scope_id, kind, label, private=True):
        _id(scope_id)
        if kind not in ('personal', 'workspace', 'chat') or type(private) is not bool:
            _fail('invalid_scope', 'Scope kind or privacy flag is invalid')
        _string(label, 'label', 256)
        with self._transaction(write=True) as data:
            old = data['scopes'].get(scope_id)
            if old and old['kind'] != kind:
                _fail('scope_conflict', 'An existing scope cannot change kind')
            if old and 'read_policy' in old and not private:
                _fail('privacy_broadening_denied', 'Directional private-chat ownership cannot become outward sharing')
            if old and old['private'] and not private and kind == 'chat' and any(
                    r['scope_id'] == scope_id for r in [*data['records'].values(), *data['tombstones'].values()]):
                _fail('privacy_broadening_denied', 'A populated private chat cannot be broadened; use a fresh chat')
            scope = dict(id=scope_id, kind=kind, label=label, private=private)
            if old and 'read_policy' in old:
                scope['read_policy'] = deepcopy(old['read_policy'])
            data['scopes'][scope_id] = scope
            self._reconcile_visibility(data)
        return deepcopy(scope)

    def get_scope(self, scope_id):
        with self._transaction() as data:
            return deepcopy(self._scope(data, scope_id))

    def set_read_policy(self, chat_scope_id, workspace_scope_id, expected_policy_revision):
        """Human service only: the service authenticates current host membership.

        Missing metadata is legacy, not an implicit migration or pool grant.
        This opt-in never changes private ownership or existing record grants.
        """
        with self._transaction(write=True) as data:
            chat = self._scope(data, chat_scope_id)
            if chat['kind'] != 'chat' or chat['private'] is not True:
                _fail('sharing_denied', 'Directional ingress requires a private chat')
            previous = chat.get('read_policy', {}).get('revision')
            if expected_policy_revision != previous:
                _fail('revision_conflict', 'Read policy changed; inspect before explicitly retrying')
            if workspace_scope_id is not None and self._scope(data, workspace_scope_id)['kind'] != 'workspace':
                _fail('sharing_denied', 'Only the current host workspace pool is supported')
            chat['read_policy'] = dict(revision=uuid.uuid4().hex, workspace_scope_id=workspace_scope_id)
            self._reconcile_visibility(data)
        return deepcopy(chat['read_policy'])

    def list_scopes(self):
        with self._transaction() as data:
            return deepcopy(list(data['scopes'].values()))

    @staticmethod
    def _fields(title, text, domain, kind, basis, sources, topic, state, dependencies, sensitive):
        _string(title, 'title', 512)
        _string(text, 'text', 262144)
        _string(topic, 'topic', 128)
        labels = {'explicit_fact': ('explicit_statement', 'source_document'),
                  'preference': ('explicit_statement',), 'observation': ('direct_observation',),
                  'interpretation': ('inference',), 'summary': ('source_document', 'inference'),
                  'procedure': ('source_document', 'inference'), 'reference': ('source_document',)}
        if (domain not in ('user', 'work', 'reference') or not isinstance(kind, str)
                or kind not in labels or basis not in labels[kind]):
            _fail('invalid_evidence', 'Domain, kind and basis must be coherent declared evidence labels')
        if state not in ('pending', 'approved', 'invalidated') or type(sensitive) is not bool:
            _fail('invalid_value', 'Record state or sensitive flag is invalid')
        if domain == 'user' and sensitive and basis != 'explicit_statement':
            _fail('sensitive_inference', 'Sensitive user records require explicit self-report metadata, not inference')
        if not isinstance(sources, list) or not 1 <= len(sources) <= 64:
            _fail('invalid_sources', 'One to 64 source entries are required')
        for source in sources:
            if not isinstance(source, dict) or not set(source) <= {'ref', 'quote', 'sha256', 'revision'} or 'ref' not in source:
                _fail('invalid_sources', 'Sources preserve ref and optional quote, sha256, revision only')
            _string(source['ref'], 'source ref', 2048)
            if 'quote' in source:
                _string(source['quote'], 'source quote', 16384)
            if 'sha256' in source and (not isinstance(source['sha256'], str) or not re.fullmatch(r'[0-9a-fA-F]{64}', source['sha256'])):
                _fail('invalid_sources', 'Source sha256 must contain exactly 64 hexadecimal characters')
            if 'revision' in source and (type(source['revision']) is not int or source['revision'] < 1):
                _fail('invalid_sources', 'Source revision must be a positive integer')
        if dependencies is None:
            dependencies = []
        if not isinstance(dependencies, list) or len(dependencies) > 64:
            _fail('invalid_dependencies', 'Dependencies must be a list of at most 64 revision-pinned records')
        return dict(title=title, text=text, domain=domain, kind=kind, basis=basis, sources=deepcopy(sources),
                    topic=topic, state=state, dependencies=deepcopy(dependencies), sensitive=sensitive)

    def put_record(self, scope_id, *, title, text, domain, kind, basis, sources,
                   topic='facts', state='pending', dependencies=None, sensitive=False):
        fields = self._fields(title, text, domain, kind, basis, sources, topic, state, dependencies, sensitive)
        with self._transaction(write=True) as data:
            self._scope(data, scope_id)
            record_id = 'rec_' + uuid.uuid4().hex
            now = _now()
            record = dict(id=record_id, revision=1, scope_id=scope_id, **fields, created_at=now, updated_at=now)
            self._dependencies(data, record)
            data['records'][record_id] = record
        return deepcopy(record)

    def create_many(self, scope_id, records):
        """Trusted-human atomic create, in input order; never a model tool.

        Accept 1-10,000 authored-field dictionaries (the same fields/defaults as
        put_record). IDs, revision and timestamps remain store-owned. Identical
        payloads create distinct records, not upserts or deduplication. Dependencies
        must pin already-existing visible records; no caller-assigned batch IDs.
        One OS lock, validated load and atomic commit cover the entire batch.
        Failure before replacement leaves the manifest/revision unchanged. A
        storage_error can be post-replacement: inspect before any explicit retry.
        Host adapters still own authentication and derived-index invalidation.
        """
        if not isinstance(records, list) or not 1 <= len(records) <= 10000:
            _fail('invalid_batch', 'A batch requires one to 10000 authored record dictionaries')
        required = {'title', 'text', 'domain', 'kind', 'basis', 'sources'}
        defaults = dict(topic='facts', state='pending', dependencies=None, sensitive=False)
        allowed = required | defaults.keys()
        created = []
        with self._transaction(write=True) as data:
            self._scope(data, scope_id)
            for payload in records:
                if (not isinstance(payload, dict) or not required <= payload.keys()
                        or not payload.keys() <= allowed):
                    _fail('invalid_payload', 'Batch creation accepts complete authored fields only')
                fields = self._fields(**{**defaults, **payload})
                record_id = 'rec_' + uuid.uuid4().hex
                if record_id in data['records'] or record_id in data['tombstones']:
                    _fail('duplicate_record', 'Generated record identity collides; no batch was committed')
                now = _now()
                record = dict(id=record_id, revision=1, scope_id=scope_id, **fields,
                              created_at=now, updated_at=now)
                self._dependencies(data, record)
                data['records'][record_id] = record
                created.append(record)
            # Validate the complete proposed state as well as each authored row;
            # this is store-owned authority, never an evaluator manifest bypass.
            self._validate_manifest(data)
        return deepcopy(created)

    def get(self, record_id):
        """Unscoped human inspector API, NEVER expose directly to a model."""
        with self._transaction() as data:
            return deepcopy(self._record(data, record_id))

    def list_records(self, scope_id, include_pending=True):
        if type(include_pending) is not bool:
            _fail('invalid_value', 'include_pending must be boolean')
        with self._transaction() as data:
            self._scope(data, scope_id)
            return deepcopy([r for r in data['records'].values() if r['scope_id'] == scope_id
                             and (include_pending or r['state'] != 'pending')])

    @staticmethod
    def _pointer(ref):
        # Only this reserved syntax denotes a local authored-record reference.
        # External refs stay opaque provenance; never dereference them here.
        if ref.startswith('record:'):
            record_id = ref[len('record:'):]
            _id(record_id)
            return record_id
        return None

    def _dependencies(self, data, record):
        deps = record['dependencies']
        seen = set()
        source_ids = {}
        for source in record['sources']:
            pointer = self._pointer(source['ref'])
            if pointer is not None:
                source_ids.setdefault(pointer, []).append(source)
        for dep in deps:
            if (not isinstance(dep, dict) or set(dep) != {'id', 'revision'} or not isinstance(dep['id'], str)
                    or type(dep['revision']) is not int or dep['revision'] < 1 or dep['id'] in seen):
                _fail('invalid_dependencies', 'Dependencies are unique {id, revision} entries')
            _id(dep['id'])
            seen.add(dep['id'])
            target = data['records'].get(dep['id'])
            if target is None or dep['id'] not in source_ids:
                _fail('invalid_dependencies', 'Every dependency must be an existing sourced record')
            if dep['revision'] != target['revision'] or any(
                    'revision' in s and s['revision'] != target['revision'] for s in source_ids[dep['id']]):
                _fail('stale_dependency', 'Referenced source revision is no longer current')
            if not self._is_visible(data, target, record['scope_id']):
                _fail('dependency_not_visible', 'A source pointer does not grant source body access')
            if dep['id'] == record['id'] or record['id'] in self._ancestors(data, dep['id']):
                _fail('dependency_cycle', 'Record dependency cycles are not allowed')
        if set(source_ids) - seen:
            _fail('undeclared_dependency', 'Local record sources must declare a pinned dependency')

    @staticmethod
    def _ancestors(data, record_id):
        found, pending = set(), [record_id]
        while pending:
            current = pending.pop()
            for dep in data['records'].get(current, {}).get('dependencies', []):
                if dep['id'] not in found:
                    found.add(dep['id'])
                    pending.append(dep['id'])
        return found

    @staticmethod
    def _dependents(data, record_ids):
        found = set(record_ids)
        while True:
            more = {r['id'] for r in data['records'].values()
                    if any(d['id'] in found for d in r['dependencies'])} - found
            if not more:
                return found - set(record_ids)
            found.update(more)

    def _invalidate(self, data, record_ids):
        for record_id in self._dependents(data, record_ids):
            record = data['records'][record_id]
            record.update(state='invalidated', revision=record['revision'] + 1, updated_at=_now())

    @staticmethod
    def _expected(record, expected_revision):
        if type(expected_revision) is not int or expected_revision != record['revision']:
            _fail('revision_conflict', 'Record changed; refresh and explicitly review before retrying')

    def approve(self, record_id, expected_revision):
        """Trusted human API; never register as a model tool."""
        with self._transaction(write=True) as data:
            record = self._record(data, record_id)
            self._expected(record, expected_revision)
            self._dependencies(data, record)
            record.update(state='approved', revision=record['revision'] + 1, updated_at=_now())
            self._invalidate(data, {record_id})
            self._reconcile_visibility(data)
        return deepcopy(record)

    def correct(self, record_id, expected_revision, changes):
        """Human correction keeps the prior approval, not model-proposal approval."""
        allowed = {'title', 'text', 'domain', 'kind', 'basis', 'sources', 'topic', 'dependencies', 'sensitive'}
        if not isinstance(changes, dict) or not changes or not set(changes) <= allowed:
            _fail('invalid_changes', 'Corrections may change authored fields only, not identity, state or activation')
        with self._transaction(write=True) as data:
            previous = self._record(data, record_id)
            self._expected(previous, expected_revision)
            proposed = {**previous, **deepcopy(changes)}
            fields = self._fields(**{key: proposed[key] for key in allowed | {'state'}})
            record = {**previous, **fields, 'revision': previous['revision'] + 1, 'updated_at': _now()}
            self._dependencies(data, record)
            data['records'][record_id] = record
            self._invalidate(data, {record_id})
            self._reconcile_visibility(data)
        return deepcopy(record)

    @staticmethod
    def _communication(record):
        return (record['state'] == 'approved' and record['sensitive'] is False and record['domain'] == 'user'
                and record['kind'] == 'preference' and record['topic'] == 'communication'
                and record['basis'] == 'explicit_statement')

    def _share_allowed(self, data, record, source_scope, target_scope):
        source = data['scopes'][source_scope]
        target = data['scopes'][target_scope]
        if record['scope_id'] != source_scope or record['state'] != 'approved':
            return False
        if source['kind'] in ('workspace', 'chat') and source['private']:
            return False
        if source['kind'] == 'personal' or target['private']:
            return self._communication(record)
        return True

    def _grant_valid(self, data, grant):
        record = data['records'].get(grant['record_id'])
        return (record is not None and record['revision'] == grant['record_revision']
                and self._share_allowed(data, record, grant['source_scope'], grant['target_scope']))

    def _reconcile_visibility(self, data):
        data['grants'] = [g for g in data['grants'] if self._grant_valid(data, g)]
        invalid = set()
        for record in data['records'].values():
            if record['state'] == 'invalidated':
                continue
            for dep in record['dependencies']:
                source = data['records'].get(dep['id'])
                if (source is None or source['revision'] != dep['revision']
                        or not self._is_visible(data, source, record['scope_id'])):
                    invalid.add(record['id'])
                    break
        invalid |= self._dependents(data, invalid)
        for record_id in invalid:
            record = data['records'][record_id]
            if record['state'] != 'invalidated':
                record.update(state='invalidated', revision=record['revision'] + 1, updated_at=_now())
        data['grants'] = [g for g in data['grants'] if self._grant_valid(data, g)]

    @staticmethod
    def _grant_ids(record_ids):
        if (not isinstance(record_ids, list) or not 1 <= len(record_ids) <= 64
                or any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', v) for v in record_ids)
                or len(set(record_ids)) != len(record_ids)):
            _fail('invalid_grant', 'Grant requires one to 64 unique explicit record identifiers, never a wildcard')
        return set(record_ids)

    def grant(self, source_scope, target_scope, record_ids):
        """Explicit record-level human grant, revision-pinned; no model exposure."""
        ids = self._grant_ids(record_ids)
        with self._transaction(write=True) as data:
            self._scope(data, source_scope)
            self._scope(data, target_scope)
            if source_scope == target_scope:
                _fail('invalid_grant', 'A grant requires distinct source and target scopes')
            records = [self._record(data, record_id) for record_id in sorted(ids)]
            for record in records:
                if not self._share_allowed(data, record, source_scope, target_scope):
                    _fail('sharing_denied', 'Only individually approved allowed cards may cross this boundary; private source containers never share')
            data['grants'] = [g for g in data['grants'] if not (g['source_scope'] == source_scope
                              and g['target_scope'] == target_scope and g['record_id'] in ids)]
            for record in records:
                data['grants'].append(dict(source_scope=source_scope, target_scope=target_scope,
                                           record_id=record['id'], record_revision=record['revision']))
            for record in records:
                if not self._is_visible(data, record, target_scope):
                    _fail('sharing_denied', 'A grant cannot expose hidden or stale dependent source material')
            receipt = dict(source_scope=source_scope, target_scope=target_scope,
                           record_ids=sorted(ids), revision=data['revision'] + 1)
        return receipt

    def revoke(self, source_scope, target_scope, record_ids):
        ids = self._grant_ids(record_ids)
        with self._transaction(write=True) as data:
            self._scope(data, source_scope)
            self._scope(data, target_scope)
            if any(self._record(data, record_id)['scope_id'] != source_scope for record_id in ids):
                _fail('sharing_denied', 'A revoke must name records owned by its declared source scope')
            data['grants'] = [g for g in data['grants'] if not (g['source_scope'] == source_scope
                              and g['target_scope'] == target_scope and g['record_id'] in ids)]
            self._reconcile_visibility(data)
            receipt = dict(source_scope=source_scope, target_scope=target_scope,
                           record_ids=sorted(ids), revision=data['revision'] + 1)
        return receipt

    def _is_visible(self, data, record, scope_id):
        # Iterative postorder avoids recursion limits and repeated expansion of
        # shared provenance DAGs. A visited-on-entry set alone would hide cycles.
        done, visiting = set(), set()
        pending = [(record, False)]
        while pending:
            current, exiting = pending.pop()
            record_id = current['id']
            if exiting:
                visiting.remove(record_id)
                done.add(record_id)
                continue
            if record_id in done:
                continue
            if record_id in visiting or current['state'] != 'approved':
                return False
            incoming = data['scopes'][scope_id].get('read_policy', {}).get('workspace_scope_id')
            if current['scope_id'] not in (scope_id, incoming) and not any(
                    g['target_scope'] == scope_id and g['record_id'] == record_id
                    and self._grant_valid(data, g) for g in data['grants']):
                return False
            visiting.add(record_id)
            pending.append((current, True))
            for dep in current['dependencies']:
                target = data['records'].get(dep['id'])
                if target is None or target['revision'] != dep['revision']:
                    return False
                pending.append((target, False))
        return True

    def _visible(self, data, scope_id):
        self._scope(data, scope_id)
        return [r for r in data['records'].values() if self._is_visible(data, r, scope_id)]

    def _preview(self, data, record_id):
        self._record(data, record_id)
        preview = dict(record_id=record_id, revision=data['revision'],
                       dependent_ids=sorted(self._dependents(data, {record_id})))
        # Store-specific stale-plan CAS, NOT a substitute for host authentication.
        payload = json.dumps(preview, sort_keys=True, separators=(',', ':')).encode('utf-8')
        preview['preview_token'] = hmac.new(data['store_id'].encode('ascii'), payload, hashlib.sha256).hexdigest()
        return preview

    def delete_preview(self, record_id):
        with self._transaction() as data:
            return self._preview(data, record_id)

    def delete(self, record_id, preview_token):
        with self._transaction(write=True) as data:
            preview = self._preview(data, record_id)
            if (not isinstance(preview_token, str) or not re.fullmatch(r'[0-9a-f]{64}', preview_token)
                    or not hmac.compare_digest(preview['preview_token'], preview_token)):
                _fail('stale_preview', 'Deletion preview is stale or mismatched; explicitly preview again, no automatic retry')
            deleted = set(preview['dependent_ids']) | {record_id}
            when = _now()
            for item in deleted:
                record = data['records'].pop(item)
                data['tombstones'][item] = dict(id=item, scope_id=record['scope_id'],
                                               revision=record['revision'] + 1, deleted_at=when)
            data['grants'] = [g for g in data['grants'] if g['record_id'] not in deleted]
            receipt = dict(record_id=record_id, revision=data['revision'] + 1, deleted_ids=sorted(deleted),
                           outside_operation='Host-owned derived indexes require refresh/purge by the adapter; '
                           'host transcripts, unknown exports and backups are outside this repository operation.')
        return receipt

    def visible_records(self, scope_id):
        with self._transaction() as data:
            return deepcopy(self._visible(data, scope_id))

    def snapshot(self, scope_id):
        with self._transaction() as data:
            return {'revision': data['revision'], 'records': deepcopy(self._visible(data, scope_id))}
