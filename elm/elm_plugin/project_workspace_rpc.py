"""Explicit authenticated project consent RPCs; not model tools or a human-click proof."""
from .private_workspace_rpc import _fields


def register_project_workspace_rpc(ctx):
    try:
        from hermes_cli.plugin_memory import memory_capabilities
    except ImportError:
        return False
    cap = memory_capabilities()
    register = getattr(ctx, 'register_rpc', None)
    if not callable(register) or not all(cap.get(k) for k in ('record_read', 'publication', 'project_binding')):
        return False
    from .project_workspace_v1 import ProjectWorkspaceV1
    service = ProjectWorkspaceV1()

    def status(params, **kwargs):
        _fields(params)
        return service.status()

    def preview(params, **kwargs):
        _fields(params, ('action',))
        return service.consent_preview(action=params['action'])

    def apply(params, **kwargs):
        _fields(params, ('preview_token', 'confirm'))
        return service.consent_apply(params['preview_token'], confirm=params['confirm'])

    def create(params, **kwargs):
        _fields(params, ('title', 'text', 'sources'), ('domain', 'kind', 'basis', 'topic', 'sensitive', 'expected_consent_revision'))
        return service.create_pending(**{k: v for k, v in params.items() if k != 'session_id'})

    def approve(params, **kwargs):
        _fields(params, ('record_id', 'expected_revision', 'confirm'), ('expected_consent_revision',))
        return service.approve(params['record_id'], params['expected_revision'], confirm=params['confirm'], expected_consent_revision=params.get('expected_consent_revision'))

    def recall(params, **kwargs):
        _fields(params, (), ('limit',))
        return service.recall(limit=params.get('limit', 6))

    def list_records(params, **kwargs):
        _fields(params, (), ('limit', 'state', 'before'))
        return service.list(limit=params.get('limit', 16), state=params.get('state', 'all'), before=params.get('before'))

    def get_record(params, **kwargs):
        _fields(params, ('record_id',))
        return service.get(params['record_id'])

    def correct(params, **kwargs):
        _fields(params, ('record_id', 'expected_revision', 'changes', 'confirm', 'expected_consent_revision'))
        return service.correct(params['record_id'], params['expected_revision'], params['changes'], confirm=params['confirm'], expected_consent_revision=params['expected_consent_revision'])

    def delete_preview(params, **kwargs):
        _fields(params, ('record_id',))
        return service.delete_preview(params['record_id'])

    def delete(params, **kwargs):
        _fields(params, ('record_id', 'expected_revision', 'preview_token', 'confirm', 'expected_consent_revision'))
        return service.delete(params['record_id'], params['expected_revision'], params['preview_token'], confirm=params['confirm'], expected_consent_revision=params['expected_consent_revision'])

    def trash(params, **kwargs):
        _fields(params, (), ('limit', 'before'))
        return service.trash(limit=params.get('limit', 16), before=params.get('before'))

    def restore(params, **kwargs):
        _fields(params, ('recovery_id', 'confirm', 'expected_consent_revision'))
        return service.restore(params['recovery_id'], confirm=params['confirm'], expected_consent_revision=params['expected_consent_revision'])

    register('project.status', status, memory_scope='local_read')
    register('project.consent.preview', preview, memory_scope='local_read')
    register('project.consent.apply', apply)
    register('project.create', create)
    register('project.approve', approve)
    register('project.recall', recall, memory_scope='local_read')
    register('project.list', list_records, memory_scope='local_read')
    register('project.get', get_record, memory_scope='local_read')
    register('project.correct', correct)
    register('project.delete_preview', delete_preview, memory_scope='local_read')
    register('project.delete', delete)
    register('project.trash', trash, memory_scope='local_read')
    register('project.restore', restore)
    on_unload = getattr(ctx, 'on_unload', None)
    if callable(on_unload):
        on_unload(service.close)
    return True
