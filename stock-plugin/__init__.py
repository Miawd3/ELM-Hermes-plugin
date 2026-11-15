"""ELM stock-Hermes entrypoint. Does not load patched-host modules.

One directory, two roles (plugin.yaml declares `kind: standalone`):
- general plugin: `/elm`, `elm_memory` tool, hooks, `hermes elm` CLI, skills, Desktop page;
- memory provider: selected with `memory.provider: elm` (`hermes memory setup elm`).
"""
def register(ctx):
    from .elm_plugin.stock_runtime import register_stock
    runtime = register_stock(ctx)
    try:
        from .elm_plugin.memory_provider import ElmMemoryProvider
    except ImportError:  # Hermes without the MemoryProvider API: general plugin only
        return runtime
    ctx.register_memory_provider(ElmMemoryProvider())  # a NEW instance on every register() call
    return runtime
