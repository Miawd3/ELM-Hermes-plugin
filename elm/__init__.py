"""ELM native memory-provider entry point; a new instance for every load."""
from .elm_plugin.provider import ElmMemoryProvider


def register(ctx):
    from hermes_constants import get_hermes_home
    from .elm_plugin.workspace_service import WorkspaceService
    if WorkspaceService.mode_present(get_hermes_home()):
        from .elm_plugin.workspace_provider import WorkspaceMemoryProvider
        ctx.register_memory_provider(WorkspaceMemoryProvider())
    else:
        ctx.register_memory_provider(ElmMemoryProvider())
    # The general host owns ctx.llm. Memory-only discovery has no facade and
    # deliberately skips this human-only secondary registration.
    from .elm_plugin.workspace_draft_bridge import register_workspace_draft_command
    register_workspace_draft_command(ctx)
