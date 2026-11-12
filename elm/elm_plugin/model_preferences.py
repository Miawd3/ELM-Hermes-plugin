"""Inert, current-chat model-role preferences. No route or credential resolution."""
from copy import deepcopy
from dataclasses import asdict
import json
import re
import secrets
import threading
import time
from urllib.parse import urlsplit, urlunsplit

from .private_workspace_v2 import _digest, _fail, _paths, _transaction
from .wiki_read import _snapshot

_NOTICE = ('Save declared preferences only for this chat: search and organizer are separate future roles. '
           'These identifiers and HTTPS endpoint are not verified provider capabilities or approved recipients. '
           'The confirmed save may add current-chat metadata within an already initialized private store. '
           'No model, credential resolver, network probe, or default chat-model change is invoked. '
           'Dispatch remains unavailable; saving is not egress consent and enables no fallback. '
           'Future execution would require exact recipient, payload, credential and cost review. '
           'Never paste credentials or secrets; arbitrary identifiers cannot be guaranteed secret-free.')
_PATHS = {'/v1/chat/completions', '/chat/completions', '/api/v1/chat/completions', '/openai/v1/chat/completions'}
_SECRET = re.compile(r'sk[-_]|bearer|api[_-]?key|access[_-]?token|password|secret', re.I)


def _identifier(value, *, model=False):
    pattern = r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}' if model else r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}'
    if type(value) is not str or re.fullmatch(pattern, value) is None or _SECRET.search(value):
        _fail('invalid_selection', 'Use a bounded declared provider/model identifier, never credentials')
    return value


def _endpoint(value):
    if (type(value) is not str or len(value) > 256 or not value
            or any(ord(char) < 33 or ord(char) > 126 for char in value)
            or any(char in value for char in ('\\', '%', '?', '#', '@')) or _SECRET.search(value)):
        _fail('invalid_selection', 'Use a credential-free HTTPS chat-completions endpoint')
    try:
        parts = urlsplit(value)
        host, port = parts.hostname, parts.port
        if (parts.scheme != 'https' or parts.username is not None or parts.password is not None
                or not host or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?', host)
                or '..' in host or any(not label or len(label) > 63 or label.startswith('-') or label.endswith('-') for label in host.split('.'))
                or (port is not None and not 1 <= port <= 65535) or parts.path not in _PATHS
                or parts.query or parts.fragment or parts.netloc.endswith(':')):
            raise ValueError('endpoint')
        # Canonical spelling is shown in preview before any storage confirmation.
        authority = host.lower() + (':' + str(port) if port is not None else '')
        return urlunsplit(('https', authority, parts.path, '', ''))
    except ValueError:
        _fail('invalid_selection', 'Use a credential-free HTTPS chat-completions endpoint with a valid port')


def _selection(value):
    if value is None:
        return None
    if type(value) is not dict or set(value) != {'provider', 'model', 'endpoint'}:
        _fail('invalid_selection', 'Selection must contain only provider, model and endpoint, or be null')
    return dict(provider=_identifier(value['provider']), model=_identifier(value['model'], model=True),
                endpoint=_endpoint(value['endpoint']))


def _row(data, chat):
    return data.get('model_preferences', {'schema': 1, 'items': {}})['items'].get(
        chat, {'revision': 0, 'search': None, 'organizer': None})


def validate_model_preferences(data):
    ext = data.get('model_preferences', {'schema': 1, 'items': {}})
    if (type(ext) is not dict or set(ext) != {'schema', 'items'} or type(ext['schema']) is not int
            or ext['schema'] != 1 or type(ext['items']) is not dict or len(ext['items']) > 512):
        raise ValueError('Invalid model preference registry')
    for chat, row in ext['items'].items():
        scope = data['scopes'].get(chat)
        if (not scope or scope['kind'] != 'chat' or scope.get('private') is not True or 'read_policy' in scope
                or type(row) is not dict or set(row) != {'revision', 'search', 'organizer'}
                or type(row['revision']) is not int or not 1 <= row['revision'] < 2**53):
            raise ValueError('Invalid model preference ownership/revision')
        if any(_selection(row[role]) != row[role] for role in ('search', 'organizer')):
            raise ValueError('Noncanonical model preference')


def _routing_readiness(row):
    # Audited implementation gaps, not runtime probes or credential inspection.
    blockers = [
        'credential_route_dispatch_binding_unavailable',
        'production_pinned_dispatch_unavailable',
        'explicit_egress_execution_unavailable',
        'provider_compatibility_unverified',
        'enforceable_cost_bound_unavailable',
    ]
    return {
        role: dict(selection_saved=row[role] is not None, dispatch_supported=False,
                   blockers=blockers + (['search_result_contract_unavailable'] if role == 'search' else []))
        for role in ('search', 'organizer')
    }


def _status(owner, initialized, store_id, chat, row):
    return dict(initialized=initialized, setup_required=not initialized, revision=row['revision'],
                context_key=_digest([asdict(owner), store_id, chat, row]),
                roles={role: deepcopy(row[role]) for role in ('search', 'organizer')},
                dispatch_supported=False, external_egress_enabled=False, scope='current_chat',
                reason='routing_unavailable', notice=_NOTICE, routing_readiness=_routing_readiness(row))


def _current(owner, change=None):
    root, _, _, chat = _paths(owner)
    if not root.exists():
        return _status(owner, False, None, chat, {'revision': 0, 'search': None, 'organizer': None})
    with _transaction(owner) as (_, data, chat):
        row = _row(data, chat)
        if change is not None:
            if row['revision'] >= 2**53 - 1:
                _fail('preference_limit', 'Preference revision limit reached')
            items = dict(data.get('model_preferences', {'items': {}})['items'])
            if chat not in items and len(items) >= 512:
                _fail('preference_limit', 'Preference registry is full')
            updated = dict(row, revision=row['revision'] + 1)
            updated[change[0]] = change[1]
            items[chat] = updated
            scopes = dict(data['scopes'])
            scopes.setdefault(chat, dict(id=chat, kind='chat', label='Private chat', private=True))
            projected = dict(data, revision=data['revision'] + 1, scopes=scopes,
                             model_preferences={'schema': 1, 'items': items})
            if len(json.dumps(projected, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')) + 1 > 4 * 1024 * 1024:
                _fail('preference_limit', 'Preferences would exceed store capacity; no preview was issued')
        return _status(owner, True, data['store_id'], chat, row)


class ModelPreferences:
    def __init__(self):
        self._lock = threading.RLock()
        self._active = True
        self._previews = {}

    def close(self):
        with self._lock:
            self._active = False
            self._previews.clear()

    def _live(self):
        if not self._active:
            _fail('context_unavailable', 'Model preference service is no longer active')
        now = time.monotonic()
        self._previews = {key: value for key, value in self._previews.items() if value['expires'] > now}

    def status(self):
        from hermes_cli.plugin_memory import memory_owner, read_memory
        with self._lock:
            self._live()
            owner = memory_owner(version=1)
            return read_memory(owner, lambda: _current(owner))

    def preview(self, role, selection, expected_revision, expected_context):
        from hermes_cli.plugin_memory import memory_owner, read_memory
        if role not in ('search', 'organizer') or type(role) is not str:
            _fail('invalid_selection', 'Choose search or organizer')
        selected = _selection(selection)
        if type(expected_revision) is not int or not 0 <= expected_revision < 2**53:
            _fail('invalid_payload', 'Expected revision must be a nonnegative integer')
        _snapshot(expected_context)
        with self._lock:
            self._live()
            if len(self._previews) >= 16:
                _fail('preview_limit', 'Too many preference previews; wait for expiry')
            owner = memory_owner(version=1)
            current = read_memory(owner, lambda: _current(owner, (role, selected)))
            if not current['initialized']:
                _fail('not_initialized', 'Explicit private-memory setup is required before saving chat preferences')
            if current['revision'] != expected_revision or current['context_key'] != expected_context:
                _fail('stale_preview', 'Preferences or owner changed; refresh before previewing')
            if current['roles'][role] == selected:
                _fail('unchanged', 'This role already has that declared preference')
            token = secrets.token_urlsafe(32)
            self._previews[token] = dict(owner=owner, role=role, selection=selected, current=current,
                                         expires=time.monotonic() + 300)
            return dict(preview_token=token, expires_in_seconds=300, role=role, selection=deepcopy(selected),
                        previous_selection=current['roles'][role], notice=_NOTICE,
                        dispatch_supported=False, external_egress_enabled=False)

    def apply(self, preview_token, *, confirm=False):
        from hermes_cli.plugin_memory import memory_owner, publish_memory
        if confirm is not True:
            _fail('confirmation_required', 'Explicit preference-storage confirmation is required')
        if type(preview_token) is not str or len(preview_token) > 128:
            _fail('invalid_payload', 'Invalid preference preview token')
        with self._lock:
            self._live()
            owner = memory_owner(version=1)
            pending = self._previews.get(preview_token)
            if pending is None:
                _fail('preview_unavailable', 'Preview expired or was consumed; refresh status before trying again')
            previous_owner = pending['owner']
            if (owner.profile_id, owner.principal_id, owner.canonical_session_id) != (
                    previous_owner.profile_id, previous_owner.principal_id, previous_owner.canonical_session_id):
                _fail('preview_unavailable', 'Preview is unavailable for this chat')
            self._previews.pop(preview_token)
            if owner != previous_owner:
                _fail('stale_preview', 'Owner changed; preview again')
            def commit():
                with _transaction(owner, write=True, create_chat=True) as (_, data, chat):
                    row = _row(data, chat)
                    current = _status(owner, chat in data['scopes'], data['store_id'], chat, row)
                    if not current['initialized'] or current['context_key'] != pending['current']['context_key']:
                        _fail('stale_preview', 'Preferences changed; refresh and preview again')
                    items = data.setdefault('model_preferences', {'schema': 1, 'items': {}})['items']
                    if chat not in items and len(items) >= 512:
                        _fail('preference_limit', 'Preference registry is full')
                    updated = dict(row, revision=row['revision'] + 1)
                    updated[pending['role']] = deepcopy(pending['selection'])
                    items[chat] = updated
                    result = _status(owner, True, data['store_id'], chat, updated)
                return dict(saved=True, status=result)
            return publish_memory(owner, commit)


def register_model_preferences_rpc(ctx):
    try:
        from hermes_cli.plugin_memory import memory_capabilities
    except ImportError:
        return False
    caps = memory_capabilities()
    register = getattr(ctx, 'register_rpc', None)
    if not callable(register) or not caps.get('record_read') or not caps.get('publication'):
        return False
    from .private_workspace_rpc import _fields
    service = ModelPreferences()
    def status(params, **kwargs):
        _fields(params)
        return service.status()
    def preview(params, **kwargs):
        _fields(params, ('role', 'selection', 'expected_revision', 'expected_context'))
        return service.preview(**{key: value for key, value in params.items() if key != 'session_id'})
    def apply(params, **kwargs):
        _fields(params, ('preview_token', 'confirm'))
        return service.apply(params['preview_token'], confirm=params['confirm'])
    register('model_preferences.status', status, memory_scope='local_read')
    register('model_preferences.preview', preview, memory_scope='local_read')
    register('model_preferences.apply', apply)
    unload = getattr(ctx, 'on_unload', None)
    if callable(unload):
        unload(service.close)
    return True
