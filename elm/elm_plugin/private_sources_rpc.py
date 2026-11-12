"""Human-reviewed private source capture/excerpts, never network or model tools."""
from .private_workspace_rpc import _fields


def register_private_sources_rpc(ctx):
    try:
        from hermes_cli.plugin_memory import memory_capabilities
    except ImportError:
        return False
    cap = memory_capabilities()
    register = getattr(ctx, 'register_rpc', None)
    if not callable(register) or not cap.get('record_read') or not cap.get('publication'):
        return False
    from .private_sources_v1 import PrivateSourcesV1
    service = PrivateSourcesV1()

    def preview(params, **kwargs):
        _fields(params, ('title', 'text'), ('reference', 'author', 'sensitive'))
        return service.preview(**{k:v for k,v in params.items() if k != 'session_id'})

    def apply(params, **kwargs):
        _fields(params, ('preview_token', 'confirm'))
        return service.apply(params['preview_token'], confirm=params['confirm'])

    def list_sources(params, **kwargs):
        _fields(params, (), ('limit', 'before'))
        return service.list(limit=params.get('limit', 16), before=params.get('before'))

    def get(params, **kwargs):
        _fields(params, ('source_id',))
        return service.get(params['source_id'])

    def withdraw(params, **kwargs):
        _fields(params, ('source_id', 'expected_revision', 'confirm'))
        return service.withdraw(params['source_id'], params['expected_revision'], confirm=params['confirm'])

    def excerpt_preview(params, **kwargs):
        _fields(params, ('source_id', 'quote'), ('occurrence', 'title'))
        return service.excerpt_preview(params['source_id'], params['quote'], occurrence=params.get('occurrence'), title=params.get('title'))

    def excerpt_apply(params, **kwargs):
        _fields(params, ('preview_token', 'confirm'))
        return service.excerpt_apply(params['preview_token'], confirm=params['confirm'])

    register('private.source.preview', preview, memory_scope='local_read')
    register('private.source.apply', apply)
    register('private.source.list', list_sources, memory_scope='local_read')
    register('private.source.get', get, memory_scope='local_read')
    register('private.source.withdraw', withdraw)
    register('private.excerpt.preview', excerpt_preview, memory_scope='local_read')
    register('private.excerpt.apply', excerpt_apply)
    on_unload = getattr(ctx, 'on_unload', None)
    if callable(on_unload):
        on_unload(service.close)
    return True
