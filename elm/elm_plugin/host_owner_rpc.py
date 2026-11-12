"""Read-only proof of the experimental host memory contract; never a write grant."""
from dataclasses import asdict


def inspect_host_owner(params, *, session_id, **kwargs):
    from hermes_cli.plugin_memory import memory_owner
    # The session argument is not an identity source. The host binds authenticated
    # context itself. Client-supplied home, profile and principal are never forwarded.
    return asdict(memory_owner(version=1, alias=params.get('alias')))


def register_host_owner_rpc(ctx):
    try:
        from hermes_cli.plugin_memory import memory_capabilities
    except ImportError:
        return False  # Stock hosts retain normal registration; no new keyword is sent.
    if not memory_capabilities().get('local_read_rpc'):
        return False
    register = getattr(ctx, 'register_rpc', None)
    if callable(register):
        register('memory.owner', inspect_host_owner, memory_scope='local_read')

    return callable(register)
