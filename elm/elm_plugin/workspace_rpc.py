"""Authenticated project-selection workflow, NOT workspace record authorization.

This isolated lane never opens/adopts legacy records, builds indexes, enables recall,
changes read policy, or grants sharing. Project selection is stored host metadata only.
Confirmation previews are process-local, short-lived, one-use capabilities: restart or
reload invalidates them. No callback or mutation is transported to a plugin subprocess.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import secrets
import threading
import time

_TTL_SECONDS = 300
_MAX_PREVIEWS = 256
_NOTICE = ('Project selection does not authorize workspace reads, share records, '
           'adopt existing memory, or enable provider recall.')


def _fields(params, expected):
    if (not isinstance(params, dict) or not set(expected) <= set(params)
            or set(params) - set(expected) - {'session_id'}):
        raise ValueError('Invalid workspace request fields')


def _scope_key(kind, owner, identifier):
    raw = json.dumps([1, kind, owner.profile_id, owner.principal_id, identifier],
                     ensure_ascii=True, separators=(',', ':'))
    return kind + ':' + hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _state(owner):
    from hermes_constants import get_hermes_home
    from hermes_cli.plugin_memory import memory_capabilities
    return {
        'schema': 1,
        'workspace_setup_present': (Path(get_hermes_home()) / 'elm-workspaces').exists(),
        'selected_project_id': owner.project_id,
        'project_binding_revision': owner.project_revision,
        'chat_scope_id': _scope_key('chat', owner, owner.canonical_session_id),
        'project_scope_id': (_scope_key('workspace', owner, owner.project_id)
                             if owner.project_id is not None else None),
        'record_access': 'not_connected',
        'project_read_authorized': False,
        'workspace_read_authorized': False,
        'catalog_eligibility': 'not_checked',
        'selection_available': memory_capabilities().get('project_binding') is True,
        'notice': _NOTICE,
    }


@dataclass(frozen=True)
class _Preview:
    owner: object
    project_id: str | None
    expires_at: float


class _WorkspaceRPC:
    def __init__(self):
        self._previews = {}
        self._lock = threading.Lock()
        self._active = True

    def close(self):
        with self._lock:
            self._active = False
            self._previews.clear()

    def _expire(self, now):
        self._previews = {token: value for token, value in self._previews.items() if value.expires_at > now}
        if not self._active:
            raise ValueError('Workspace selection context is unavailable')

    def status(self, params, *, session_id=None, **kwargs):
        _fields(params, ())
        from hermes_cli.plugin_memory import memory_owner
        with self._lock:
            self._expire(time.monotonic())
        owner = memory_owner(version=1)
        with self._lock:
            self._expire(time.monotonic())
            return _state(owner)

    def preview(self, params, *, session_id=None, **kwargs):
        _fields(params, ('project_id',))
        from hermes_cli.plugin_memory import memory_capabilities, memory_owner
        if memory_capabilities().get('project_binding') is not True:
            raise ValueError('Workspace selection requires an in-process control RPC')
        project_id = params['project_id']
        if project_id is not None and (not isinstance(project_id, str) or not project_id
                or len(project_id) > 256 or any(ord(char) < 32 for char in project_id)):
            raise ValueError('An exact project ID or null is required')
        owner = memory_owner(version=1)
        now = time.monotonic()
        with self._lock:
            self._expire(now)
            if len(self._previews) >= _MAX_PREVIEWS:
                raise ValueError('Too many pending workspace previews')
            token = secrets.token_urlsafe(32)
            self._previews[token] = _Preview(owner, project_id, now + _TTL_SECONDS)
        return {'preview_token': token, 'expires_in_seconds': _TTL_SECONDS,
                'current_project_id': owner.project_id, 'target_project_id': project_id,
                'operation': 'unbind' if project_id is None else 'bind',
                'target_validation': 'on_apply', 'confirmation_required': True,
                'project_read_authorized': False,
        'workspace_read_authorized': False, 'notice': _NOTICE}

    def apply(self, params, *, session_id=None, **kwargs):
        _fields(params, ('preview_token', 'confirm'))
        token = params['preview_token']
        if params['confirm'] is not True or not isinstance(token, str) or not 1 <= len(token) <= 128:
            raise ValueError('A valid preview token and explicit confirmation are required')
        from hermes_cli.plugin_memory import bind_memory_project, memory_capabilities, memory_owner
        if memory_capabilities().get('project_binding') is not True:
            raise ValueError('Workspace selection requires an in-process control RPC')
        current = memory_owner(version=1)
        with self._lock:
            self._expire(time.monotonic())
            preview = self._previews.get(token)
            if preview is None:
                raise ValueError('Workspace preview expired, was consumed, or is unavailable')
            identity_fields = ('profile_id', 'principal_id', 'canonical_session_id')
            if any(getattr(current, key) != getattr(preview.owner, key) for key in identity_fields):
                # A foreign caller cannot burn another conversation's outstanding preview.
                raise ValueError('Workspace preview is unavailable for this conversation')
            self._previews.pop(token)
            if current != preview.owner:
                raise ValueError('Workspace ownership changed; obtain a new preview')
            # Consumed before the single bounded host mutation. Keep the workflow lock
            # through it so unload linearizes after this attempt, never between redemption
            # and commit. The native binder must not re-enter this workflow. Expiry is
            # checked at redemption; it does not cancel an already admitted operation.
            # Exceptions/uncertain outcomes release the lock but never restore the token.
            updated = bind_memory_project(preview.owner, preview.project_id)
        try:
            return {'applied': True, 'status': _state(updated), 'notice': _NOTICE}
        except Exception:
            # The binder returned success. A display failure must not invite another write.
            return {'applied': True, 'status': None, 'refresh_required': True,
                    'warning': 'Project selection was applied; status refresh failed. Do not repeat the write.',
                    'notice': _NOTICE}


def register_workspace_rpc(ctx):
    try:
        from hermes_cli.plugin_memory import memory_capabilities
    except ImportError:
        return False
    capabilities = memory_capabilities()
    register = getattr(ctx, 'register_rpc', None)
    if capabilities.get('local_read_rpc') is not True or not callable(register):
        return False
    workflow = _WorkspaceRPC()
    register('workspace.status', workflow.status, memory_scope='local_read')
    if capabilities.get('project_binding') is True:
        register('workspace.project.preview', workflow.preview)
        register('workspace.project.apply', workflow.apply)
    on_unload = getattr(ctx, 'on_unload', None)
    if callable(on_unload):
        on_unload(workflow.close)
    return True
