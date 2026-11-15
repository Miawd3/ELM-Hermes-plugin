"""ELM stock-Hermes entrypoint. Does not load patched-host modules.

One directory, two roles (plugin.yaml declares `kind: standalone`):
- general plugin: `/elm`, `elm_memory` tool, hooks, `hermes elm` CLI, skills, Desktop page,
  routing backend (`delegation.backend: elm`);
- memory provider: selected with `memory.provider: elm` (`hermes memory setup elm`).

Hermes's memory loader calls register() again on every agent build with a collector context
that only supports `register_*` (no session surface, no model API). Registering the tool,
command or CLI through it would rebind them to a runtime that cannot work, so there we register
only the provider and the two lifecycle hooks that must also run in memory-only mode.
"""


def _is_plugin_context(ctx):
    return callable(getattr(type(ctx), 'session_surface', None))


def register(ctx):
    try:
        from .elm_plugin.memory_provider import ElmMemoryProvider
    except ImportError:  # Hermes without the MemoryProvider API: general plugin only
        ElmMemoryProvider = None
    if _is_plugin_context(ctx):
        from .elm_plugin.stock_runtime import register_stock
        runtime = register_stock(ctx)
    else:
        from .elm_plugin.stock_runtime import register_lifecycle_hooks
        runtime = register_lifecycle_hooks(ctx)
    if ElmMemoryProvider is not None and hasattr(ctx, 'register_memory_provider'):
        ctx.register_memory_provider(ElmMemoryProvider())  # a NEW instance on every register() call
    return runtime
