"""ELM Wiki memory-provider entry point; a new instance for every load.

Uses only public Hermes plugin API (PluginContext, agent.memory_provider, hermes_constants).
The earlier workspace, scoped-recall, review-UI and skill-update layers needed a patched
Hermes host and were removed in 0.2.0-experimental.
"""


def register(ctx):
    from .elm_plugin.starter_skills import register_starter_skills
    register_starter_skills(ctx)
    from .elm_plugin.provider import ElmMemoryProvider
    ctx.register_memory_provider(ElmMemoryProvider())
