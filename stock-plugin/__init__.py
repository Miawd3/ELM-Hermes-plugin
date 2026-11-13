"""ELM stock-Hermes entrypoint. Does not load patched-host modules."""
def register(ctx):
    from .elm_plugin.stock_runtime import register_stock
    return register_stock(ctx)
