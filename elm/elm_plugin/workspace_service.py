"""Host-owned workspace service; inspector selection never grants model recall.

This is the shared boundary for the human REST inspector and the native memory
provider. Its caller supplies the *host's* profile home. Model-facing callers
only receive a captured session and cannot supply a root, scope or approval.
"""
from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from .host_identity import HostIdentity, IdentityError
from .workspace_records import RecordStore, RecordError, recall_records
from .storage import atomic_json


class ServiceError(RecordError):
    pass


def scope_key(kind, identifier):
    return kind + ':' + hashlib.sha256(identifier.encode('utf-8')).hexdigest()


class WorkspaceService:
    def __init__(self, home):
        self.home = Path(home).resolve()
        self.base = self.home / 'elm-workspaces'
        if self.base.resolve().parent != self.home or (self.base/'records').resolve().parent != self.base.resolve():
            raise ServiceError('unowned_root', 'Workspace memory cannot redirect outside this profile')
        self.store = RecordStore(self.base/'records')
        self.identity = HostIdentity(self.home)
        self.cache_root = self.base/'index-cache'

    @classmethod
    def mode_present(cls, home):
        # An interrupted setup must not silently fall back to a broader legacy grant.
        return (Path(home).resolve()/'elm-workspaces').exists()

    def setup(self, *, confirm=False):
        if confirm is not True:
            raise ServiceError('confirmation_required', 'Explicit fresh-store confirmation is required')
        if self.base.exists():
            raise ServiceError('already_initialized', 'Workspace path exists; setup never adopts or replaces it')
        return self.store.initialize()

    def _require_setup(self):
        status = self.store.status()
        if not status['initialized']:
            raise ServiceError('not_initialized', 'Explicit fresh workspace setup is required')
        return status

    def _ensure_scopes(self, identity):
        proposed = [dict(id='personal', kind='personal', label='Personal', private=True)]
        for project in self.identity.list_projects():
            proposed.append(dict(id=scope_key('workspace', project['id']), kind='workspace',
                                 label=project['name'], private=True))
        proposed.append(dict(id=scope_key('chat', identity['chat_id']), kind='chat',
                             label='Chat ' + identity['chat_id'][:48], private=True))
        if any(not isinstance(s['label'], str) or not 1 <= len(s['label']) <= 256 for s in proposed):
            raise ServiceError('host_metadata_unavailable', 'The host returned an invalid scope label')
        existing = {s['id']: s for s in self.store.list_scopes()}
        if all(s['id'] in existing for s in proposed):
            return
        # The store's owned transaction is the atomic boundary for host-created
        # scopes. Never perform a read-then-upsert that resets a concurrent human
        # privacy choice. No records or grants are altered by registration.
        with self.store._transaction(write=True) as data:
            for scope in proposed:
                data['scopes'].setdefault(scope['id'], scope)

    @contextmanager
    def operation(self):
        """Serialize index publication with mutations; distinct from store commits.

        Without this outer OS-owned lock an in-flight query could recreate an old
        content-bearing index *after* deletion purged it. No wait/retry or stale
        PID-lock recovery. Host scope/consent still needs final revalidation.
        """
        self._require_setup()
        with (self.base/'.operations.lock').open('a+b') as handle:
            if handle.tell() == 0:
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise ServiceError('operation_busy', 'Memory is busy; no mutation was retried') from exc
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _index(self):
        from .workspace_index import WorkspaceIndex
        return WorkspaceIndex(self.home, self.cache_root)

    def _cleanup_index(self):
        if not self.cache_root.exists():
            return {'complete': True, 'held': [], 'removed': 0}
        try:
            receipt = self._index().purge()
            # The bridge deliberately retains non-content owner/lock metadata.
            # Directory existence is not evidence that erased content remains.
            complete = (receipt.get('removed') is True and receipt.get('copies_retained') is False
                        and receipt.get('held_paths') == [])
            held = [] if complete else receipt.get('held_paths') or [str(self.cache_root)]
            return {'complete': complete, 'held': held, 'held_paths': held, 'receipt': receipt}
        except (RecordError, RuntimeError, OSError, ValueError) as exc:
            return {'complete': False, 'held': [str(self.cache_root)],
                    'code': getattr(exc, 'code', 'index_cleanup_failed')}

    def _mutate(self, method, *args, **kwargs):
        with self.operation():
            result = method(*args, **kwargs)
            cleanup = self._cleanup_index()
            result = {**result, 'index_cleanup': cleanup}
            if not cleanup['complete']:
                result['warning'] = 'The record change committed; some derived index copies remain. Do not repeat the write.'
            return result

    def grants(self):
        # Human-only metadata view. No source bodies or new recall authority.
        with self.store._transaction() as data:
            return deepcopy(data['grants'])

    def _binding(self, session_id):
        self._require_setup()
        identity = self.identity.resolve(session_id)
        self._ensure_scopes(identity)
        chat_id = scope_key('chat', identity['chat_id'])
        workspace_id = scope_key('workspace', identity['project_id']) if identity['project_id'] else None
        chat = self.store.get_scope(chat_id)
        effective = chat_id if chat['private'] or workspace_id is None else workspace_id
        current = self.store.get_scope(effective)
        policy = chat.get('read_policy')
        if policy and policy['workspace_scope_id'] not in (None, workspace_id):
            raise ServiceError('scope_changed', 'Incoming workspace membership changed; review the read policy')
        context = dict(session_id=session_id, chat_scope_id=chat_id, workspace_scope_id=workspace_id,
                       recall_scope_id=effective, label=current['label'], private=chat['private'],
                       boundary=('Private chat only; no workspace or general history' if chat['private']
                                 else 'This workspace only' if workspace_id else 'This chat only'),
                       communication='Only individually approved communication cards explicitly shared here')
        if policy:
            context.update(policy_revision=policy['revision'], authored_scope_id=chat_id,
                           incoming_workspace_scope_id=policy['workspace_scope_id'],
                           boundary=('Private chat ownership; explicit current-workspace incoming reads only'
                                     if policy['workspace_scope_id'] else 'Private chat only; no workspace or general history'))
        return identity, context

    def capture(self, session_id):
        identity, context = self._binding(session_id)
        snapshot = self.store.snapshot(context['recall_scope_id'])
        result = dict(session_id=session_id, identity=identity['fingerprint'], context=context,
                      scope_id=context['recall_scope_id'], revision=snapshot['revision'],
                      records=recall_records(snapshot['records']))
        self.assert_current(result)
        return result

    def assert_current(self, captured):
        identity = self.identity.resolve(captured['session_id'])
        chat = self.store.get_scope(captured['context']['chat_scope_id'])
        effective = (chat['id'] if chat['private'] or captured['context']['workspace_scope_id'] is None
                     else captured['context']['workspace_scope_id'])
        status = self.store.status()
        policy = chat.get('read_policy', {})
        if (identity['fingerprint'] != captured['identity'] or not status['initialized']
                or status['revision'] != captured['revision'] or effective != captured['scope_id']
                or chat['private'] != captured['context']['private']
                or policy.get('revision') != captured['context'].get('policy_revision')
                or policy.get('workspace_scope_id') != captured['context'].get('incoming_workspace_scope_id')):
            raise ServiceError('scope_changed', 'Chat ownership or memory changed; stale results were withheld')

    def _recall(self, session_id, method, value, **kwargs):
        # A trusted host session is the only selector. Serialize projection
        # publication with all destructive operations, then recheck host metadata.
        with self.operation():
            captured = self.capture(session_id)
            result = getattr(self._index(), method)(captured['scope_id'], captured['records'], value, **kwargs)
            try:
                self.assert_current(captured)
            except RecordError:
                self._cleanup_index()
                raise
            return {**result, 'scope_id': captured['scope_id'], 'store_revision': captured['revision'],
                    'context': captured['context'], 'content_role': 'untrusted_memory_data',
                    '_publication': self.publication_token(captured)}

    @staticmethod
    def publication_token(captured):
        # Server-internal handoff, removed before model output. No source bodies.
        return {k:deepcopy(captured[k]) for k in ('session_id','identity','context','scope_id','revision')}

    def query(self, session_id, query, *, limit=6):
        return self._recall(session_id, 'query', query, limit=limit)

    def read(self, session_id, section):
        return self._recall(session_id, 'read', section)

    def index_status(self, scope_id):
        # Human inspection validates the current approved snapshot; never builds.
        from .workspace_index import IndexError as WorkspaceIndexError
        with self.operation():
            snapshot = self.store.snapshot(scope_id)
            try:
                result = self._index().status(scope_id, records=snapshot['records'])
            except WorkspaceIndexError as exc:
                return dict(scope_id=scope_id, index_state='unavailable', code=exc.code,
                            snapshot_current=False, generation=None)
            if self.store.status()['revision'] != snapshot['revision']:
                raise ServiceError('scope_changed', 'Memory changed during index inspection')
            return {**result, 'scope_id':scope_id,
                    'index_state':'not_built' if result['state']=='missing' else result['state']}

    def rebuild(self, scope_id, *, confirm=False):
        if confirm is not True:
            raise ServiceError('confirmation_required', 'Explicit index rebuild confirmation is required')
        with self.operation():
            snapshot = self.store.snapshot(scope_id)
            result = self._index().build(scope_id, snapshot['records'], force=True)
            if self.store.status()['revision'] != snapshot['revision']:
                self._cleanup_index()
                raise ServiceError('scope_changed', 'Memory changed during rebuild; stale projection withheld')
            return {**result, 'scope_id':scope_id, 'index_state':'ready', 'snapshot_current':True}

    def overview(self, session_id, scope_id=None):
        status = self.store.status()
        identity = self.identity.resolve(session_id)
        if not status['initialized']:
            return dict(schema=1, setup=False, revision=0,
                        context=dict(session_id=session_id, chat_scope_id=None, workspace_scope_id=None,
                                     label='Not configured', private=True, boundary='Memory is not configured'),
                        scopes=[], selected_scope_id=None, records=[],
                        status=dict(index_state='not_built', learning_enabled=False))
        captured = self.capture(session_id)
        selected = scope_id if scope_id is not None else captured['scope_id']
        self.store.get_scope(selected)
        result = dict(schema=1, setup=True, revision=captured['revision'], context=captured['context'],
                      scopes=self.store.list_scopes(), selected_scope_id=selected,
                      records=self.store.list_records(selected),
                      grants=self.grants(),
                      status={**self.index_status(selected), 'learning_enabled':self.settings()['learning_enabled']})
        model_policy=self.model_policy(selected,session_id)
        if model_policy is not None:
            result['model_policy']=model_policy['settings']['private_workspace' if model_policy['kind']=='workspace_member' else 'private_chat']['memory']
        self.assert_current(captured)
        return result

    def model_policy(self,scope_id,session_id=None):
        from .private_controls import PrivateControls
        from .result_inbox import InboxError
        import sqlite3
        try:
            controls=PrivateControls(self.home)
            scope=self.store.get_scope(scope_id)
            if scope['kind']=='workspace':return controls.workspace_model_policy(scope_id)
            if session_id is not None and scope_id==scope_key('chat',self.identity.resolve(session_id)['chat_id']):
                return controls.chat_model_policy(session_id)
            return None
        except (InboxError,OSError,sqlite3.Error):
            raise ServiceError('model_policy_unavailable','Cannot verify selected-area model policy; no model call made') from None

    def create_record(self, payload):
        self._require_setup()
        allowed = {'scope_id','title','text','domain','kind','basis','topic','sources','state','dependencies','sensitive'}
        if not isinstance(payload, dict) or not set(payload) <= allowed or 'scope_id' not in payload:
            raise ServiceError('invalid_payload', 'Human record creation accepts authored record fields only')
        fields = {k:v for k,v in payload.items() if k != 'scope_id'}
        required = {'title','text','domain','kind','basis','sources'}
        if not required <= fields.keys():
            raise ServiceError('invalid_payload', 'Title, text, evidence labels and sources are required')
        return self._mutate(self.store.put_record, payload['scope_id'], **fields)

    def propose(self, session_id, payload):
        allowed = {'title','text','domain','kind','basis','topic','sources','dependencies','sensitive'}
        if not isinstance(payload, dict) or not set(payload) <= allowed:
            raise ServiceError('invalid_payload', 'Model proposals cannot select a scope, root, state or approval')
        required = {'title','text','domain','kind','basis','sources'}
        if not required <= payload.keys():
            raise ServiceError('invalid_payload', 'A sourced proposal with evidence labels is required')
        with self.operation():
            captured = self.capture(session_id)
            self.assert_current(captured)
            return self.store.put_record(captured['scope_id'], **payload, state='pending')

    def set_privacy(self, scope_id, private):
        scope = self.store.get_scope(scope_id)
        return self._mutate(self.store.put_scope, scope_id, scope['kind'], scope['label'], private=private)

    def read_policy(self, session_id):
        """Human readback, including recoverable membership mismatch; no bodies."""
        self._require_setup()
        identity = self.identity.resolve(session_id)
        self._ensure_scopes(identity)
        chat_id = scope_key('chat', identity['chat_id'])
        workspace = scope_key('workspace', identity['project_id']) if identity['project_id'] else None
        chat = self.store.get_scope(chat_id)
        policy = chat.get('read_policy', {})
        incoming = policy.get('workspace_scope_id')
        return dict(session_id=session_id, identity=identity['fingerprint'], private=chat['private'],
                    authored_scope_id=chat_id, workspace_scope_id=workspace,
                    configured_workspace_scope_id=incoming, policy_revision=policy.get('revision'),
                    workspace_enabled=incoming is not None and incoming == workspace,
                    membership_current=incoming in (None, workspace))

    def set_read_policy(self, session_id, workspace_enabled, expected_identity, expected_policy_revision):
        if type(workspace_enabled) is not bool or not isinstance(expected_identity, str):
            raise ServiceError('invalid_payload', 'An explicit boolean and current host identity are required')
        if expected_policy_revision is not None and (not isinstance(expected_policy_revision, str)
                or len(expected_policy_revision) != 32):
            raise ServiceError('invalid_payload', 'An exact policy revision or legacy null is required')
        def commit():
            view = self.read_policy(session_id)
            if view['identity'] != expected_identity:
                raise ServiceError('scope_changed', 'Host identity changed; inspect before explicitly retrying')
            if workspace_enabled and view['workspace_scope_id'] is None:
                raise ServiceError('sharing_denied', 'This host chat has no current workspace pool')
            self.store.set_read_policy(view['authored_scope_id'],
                view['workspace_scope_id'] if workspace_enabled else None, expected_policy_revision)
            # Read back this exact policy target. A host change fails closed on
            # recall; a committed mutation is never silently retried.
            return self.read_policy(session_id)
        return self._mutate(commit)

    def approve(self, record_id, expected_revision):
        return self._mutate(self.store.approve, record_id, expected_revision)

    def correct(self, record_id, expected_revision, changes):
        return self._mutate(self.store.correct, record_id, expected_revision, changes)

    def grant(self, source_scope, target_scope, record_ids):
        return self._mutate(self.store.grant, source_scope, target_scope, record_ids)

    def revoke(self, source_scope, target_scope, record_ids):
        return self._mutate(self.store.revoke, source_scope, target_scope, record_ids)

    def delete_preview(self, record_id):
        return self.store.delete_preview(record_id)

    def delete(self, record_id, preview_token):
        return self._mutate(self.store.delete, record_id, preview_token)

    def settings(self):
        path = self.base/'settings.json'
        if not path.exists():
            return {'schema':1, 'learning_enabled':False, 'revision':None}
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
            if (not isinstance(value, dict) or set(value) != {'schema','learning_enabled','revision'}
                    or type(value['schema']) is not int or value['schema'] != 1
                    or type(value['learning_enabled']) is not bool
                    or not isinstance(value['revision'], str) or len(value['revision']) != 32):
                raise ValueError('Invalid consent metadata')
            return value
        except (OSError, ValueError) as exc:
            raise ServiceError('settings_unavailable', 'Cannot verify learning consent; generation is disabled') from exc

    def set_learning(self, enabled):
        if type(enabled) is not bool:
            raise ServiceError('invalid_payload', 'Learning consent must be an explicit boolean')
        with self.operation():
            self.settings()
            value = {'schema':1, 'learning_enabled':enabled, 'revision':uuid4().hex}
            atomic_json(self.base/'settings.json', value)
            return value
