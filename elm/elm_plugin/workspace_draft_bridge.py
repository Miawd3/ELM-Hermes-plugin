"""Human pending-draft bridge through a general PluginContext's host-owned llm.

Call registration from the plugin entrypoint. The memory-provider collector has
no llm facade and intentionally skips this secondary registration. General
plugin discovery must actually load the entrypoint (exclusive manifests do not).
The authenticated HUMAN API owns inspector scope selection; never register this
helper as a model tool, nor use its payload as approval or recall authority.
"""
from __future__ import annotations

import json
from pathlib import Path

from hermes_constants import get_hermes_home
from hermes_cli.plugins import get_plugin_command_handler, get_plugin_commands

from .workspace_learning import WorkspaceLearning
from .workspace_records import RecordError
from .workspace_service import WorkspaceService, ServiceError

PLUGIN_ID = 'elm'
DRAFT_COMMAND = 'elm-workspace-pending-draft'


def _refusal(code, message):
    return {'ok': False, 'code': code, 'message': message}


def _profile(home):
    home = Path(home).resolve()
    if get_hermes_home().resolve() != home:
        raise ServiceError('profile_mismatch', 'The host must bind the selected profile before drafting')
    return home


def _owned_handler(home):
    handler = get_plugin_command_handler(DRAFT_COMMAND)
    metadata = get_plugin_commands().get(DRAFT_COMMAND)
    if handler is None or metadata is None:
        raise ServiceError('draft_bridge_unavailable', 'General plugin draft registration is unavailable')
    # The host's dashboard loader imports this package under a separate,
    # path-qualified namespace. Class identity is therefore not an ownership
    # test. Require this exact implementation's code AND source file, in
    # addition to host ownership metadata and captured home. This prevents
    # accidental dispatch, not malicious in-process Python tampering.
    code = getattr(getattr(type(handler), '__call__', None), '__code__', None)
    ours = _DraftHandler.__call__.__code__
    same_implementation = (code is not None and code == ours
                           and Path(code.co_filename).resolve() == Path(__file__).resolve())
    if (metadata.get('plugin_key') != PLUGIN_ID or metadata.get('plugin') != PLUGIN_ID
            or metadata.get('handler') is not handler
            or not same_implementation or getattr(handler, 'home', None) != home):
        raise ServiceError('draft_bridge_collision', 'The draft command is not owned by this plugin and profile')
    return handler


def _parse_request(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate field')
            result[key] = value
        return result
    try:
        if not isinstance(raw, str) or len(raw.encode('utf-8')) > 8192:
            raise ValueError('request size')
        data = json.loads(raw, object_pairs_hook=unique)
        if (not isinstance(data, dict) or not {'scope_id', 'record_ids', 'kind'} <= set(data)
                or not set(data) <= {'scope_id', 'record_ids', 'kind', 'session_id', 'model_route'}):
            raise ValueError('request fields')
        if 'session_id' in data and (not isinstance(data['session_id'], str) or not 1 <= len(data['session_id']) <= 256):
            raise ValueError('session shape')
        if not isinstance(data['scope_id'], str) or not 1 <= len(data['scope_id']) <= 256:
            raise ValueError('scope shape')
        ids = data['record_ids']
        if (not isinstance(ids, list) or not 1 <= len(ids) <= 8
                or any(not isinstance(i, str) or not 1 <= len(i) <= 256 for i in ids)
                or len(set(ids)) != len(ids)):
            raise ValueError('selection shape')
        if not isinstance(data['kind'], str) or data['kind'] not in {'summary', 'observation', 'procedure'}:
            raise ValueError('kind')
        return data
    except (ValueError, TypeError, RecursionError):
        raise ServiceError('invalid_draft_request', 'Supply only scope_id, 1-8 distinct record_ids and summary/observation/procedure kind') from None


class _DraftHandler:
    def __init__(self, home, llm):
        self.home = home
        self.llm = llm

    def __call__(self, raw_args):
        try:
            _profile(self.home)
            if _owned_handler(self.home) is not self:
                raise ServiceError('draft_bridge_collision', 'The registered draft handler changed')
            payload = _parse_request(raw_args)
            result = WorkspaceLearning(WorkspaceService(self.home), self.llm).draft(
                payload['scope_id'], payload['record_ids'], payload['kind'], session_id=payload.get('session_id'),model_route=payload.get('model_route'))
            answer = {'ok': True, 'result': result}
        except RecordError as exc:
            answer = _refusal(exc.code, str(exc))
        except Exception:
            answer = _refusal('draft_failed', 'Draft failed; inspect records before retrying. No automatic retry occurred.')
        return json.dumps(answer, ensure_ascii=False)


def register_workspace_draft_command(ctx):
    """Return registered/skipped status; never construct a model facade ourselves."""
    llm = getattr(ctx, 'llm', None)
    if llm is None:
        return {'registered': False, 'reason': 'context_has_no_llm'}
    if getattr(ctx, 'plugin_id', None) != PLUGIN_ID:
        # Refuse this secondary surface without disabling the independently
        # registered memory provider. Incomplete/foreign contexts receive no
        # handler, host state lookup, model call, or ownership exception.
        return {'registered': False, 'reason': 'foreign_plugin_context'}
    home = get_hermes_home().resolve()  # host loader binds the manager's home around register()
    existing = get_plugin_commands().get(DRAFT_COMMAND)
    if existing is not None:
        _owned_handler(home)  # collision fails closed, never displaces another command
        return {'registered': True, 'command': DRAFT_COMMAND}
    handler = _DraftHandler(home, llm)
    ctx.register_command(name=DRAFT_COMMAND, handler=handler,
        description='Create a source-backed pending workspace draft (human selection only)',
        args_hint='<scope_id/record_ids/kind JSON>', argument_mode='text')
    if _owned_handler(home) is not handler:
        raise ServiceError('draft_bridge_unavailable', 'The host did not retain the draft registration')
    return {'registered': True, 'command': DRAFT_COMMAND}


def draft_via_host_command(profile_home, payload):
    """For an authenticated human API only; profile_home comes from the host.

    Does not switch profiles, select a fallback, initialize storage, grant
    consent, approve records or expose model-selected scope/root arguments.
    Returns the command's structured JSON envelope as a dictionary.
    """
    try:
        home = _profile(profile_home)
        handler = _owned_handler(home)
        return json.loads(handler(json.dumps(payload, ensure_ascii=False)))
    except RecordError as exc:
        return _refusal(exc.code, str(exc))
    except Exception:
        return _refusal('draft_bridge_unavailable', 'Host draft bridge unavailable; no fallback was attempted')
