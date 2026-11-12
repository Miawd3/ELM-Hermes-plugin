"""Human control and explicit read endpoints for the fresh private-chat-only store.

No model tools, arbitrary scope selectors, project access, grant creation or legacy adoption.
"""


def _fields(params, required=(), optional=()):
    if (not isinstance(params, dict) or not set(required) <= set(params)
            or set(params) - set(required) - set(optional) - {'session_id'}):
        raise ValueError('Invalid private-memory fields; caller scope/root/identity is not accepted')


def register_private_workspace_rpc(ctx):
    try:
        from hermes_cli.plugin_memory import memory_capabilities
    except ImportError:
        return False
    cap = memory_capabilities()
    register = getattr(ctx, 'register_rpc', None)
    if not callable(register) or not cap.get('record_read') or not cap.get('publication'):
        return False
    from .private_workspace_v2 import PrivateWorkspaceV2
    service = PrivateWorkspaceV2()

    def status(params, **kwargs):
        _fields(params)
        return service.status()

    def list_records(params, **kwargs):
        _fields(params, (), ('limit', 'state', 'before'))
        return service.list(limit=params.get('limit', 16), state=params.get('state', 'all'), before=params.get('before'))

    def get_record(params, **kwargs):
        _fields(params, ('record_id',))
        return service.get(params['record_id'])

    def setup(params, **kwargs):
        _fields(params, ('confirm',))
        return service.setup(confirm=params['confirm'])

    def create(params, **kwargs):
        _fields(params, ('title', 'text', 'sources'), ('domain', 'kind', 'basis', 'topic', 'sensitive'))
        return service.create_pending(**{key: value for key, value in params.items() if key != 'session_id'})

    def approve(params, **kwargs):
        _fields(params, ('record_id', 'expected_revision', 'confirm'))
        return service.approve(params['record_id'], params['expected_revision'], confirm=params['confirm'])

    def correct(params, **kwargs):
        _fields(params, ('record_id', 'expected_revision', 'changes', 'confirm'))
        return service.correct(params['record_id'], params['expected_revision'], params['changes'], confirm=params['confirm'])

    def delete_preview(params, **kwargs):
        _fields(params, ('record_id',))
        return service.delete_preview(params['record_id'])

    def delete(params, **kwargs):
        _fields(params, ('record_id', 'expected_revision', 'preview_token', 'confirm'))
        return service.delete(params['record_id'], params['expected_revision'], params['preview_token'], confirm=params['confirm'])

    def trash(params, **kwargs):
        _fields(params, (), ('limit', 'before'))
        return service.trash(limit=params.get('limit', 16), before=params.get('before'))

    def restore(params, **kwargs):
        _fields(params, ('recovery_id', 'confirm'))
        return service.restore(params['recovery_id'], confirm=params['confirm'])

    def recall(params, **kwargs):
        _fields(params, (), ('limit',))
        return service.recall(limit=params.get('limit', 6))

    register('private.status', status, memory_scope='local_read')
    register('private.list', list_records, memory_scope='local_read')
    register('private.get', get_record, memory_scope='local_read')
    register('private.recall', recall, memory_scope='local_read')
    register('private.setup', setup)
    register('private.create', create)
    register('private.approve', approve)
    register('private.correct', correct)
    register('private.delete_preview', delete_preview, memory_scope='local_read')
    register('private.delete', delete)
    register('private.restore', restore)
    register('private.trash', trash, memory_scope='local_read')
    return True
