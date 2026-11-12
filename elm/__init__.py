"""ELM native memory-provider entry point; a new instance for every load."""


def register(ctx):
    from .elm_plugin.starter_skills import register_starter_skills
    register_starter_skills(ctx)
    from .elm_plugin.scoped_recall import ScopedMemoryProvider, register_recall_settings_rpc
    ctx.register_memory_provider(ScopedMemoryProvider())
    register_recall_settings_rpc(ctx)
    # Scoped mode intentionally does not register the legacy global draft command.
    # Its inactive source remains for reference; it is not a model-routing fallback.
    # Read-only diagnostic; legacy provider paths are not silently upgraded.
    from .elm_plugin.host_owner_rpc import register_host_owner_rpc
    register_host_owner_rpc(ctx)
    # Workspace selection is explicit; it never enables legacy project recall.
    from .elm_plugin.workspace_rpc import register_workspace_rpc
    register_workspace_rpc(ctx)
    from .elm_plugin.chat_folders_rpc import register_chat_folders_rpc
    register_chat_folders_rpc(ctx)
    # Fresh principal-qualified records remain private-chat-only and opt-in.
    from .elm_plugin.private_workspace_rpc import register_private_workspace_rpc
    register_private_workspace_rpc(ctx)
    # Separate project records require explicit per-chat consent, never selection alone.
    from .elm_plugin.project_workspace_rpc import register_project_workspace_rpc
    register_project_workspace_rpc(ctx)
    # Explicit captured bytes and reviewed exact excerpts remain private-chat-only.
    from .elm_plugin.private_sources_rpc import register_private_sources_rpc
    register_private_sources_rpc(ctx)
    # Local capture consent is independent of request recall or external egress.
    from .elm_plugin.conversation_capture import register_capture_rpc
    register_capture_rpc(ctx)
    # Read-only egress planning: real model dispatch remains explicitly unavailable.
    from .elm_plugin.curation_foundation import register_curation_rpc
    register_curation_rpc(ctx)
    from .elm_plugin.curation_jobs import register_curation_jobs_rpc
    register_curation_jobs_rpc(ctx)
    from .elm_plugin.private_import_v1 import register_private_import_rpc
    register_private_import_rpc(ctx)

    from .elm_plugin.wiki_read import register_wiki_rpc
    register_wiki_rpc(ctx)

    from .elm_plugin.reference_drafts import register_reference_drafts_rpc
    register_reference_drafts_rpc(ctx)

    from .elm_plugin.model_preferences import register_model_preferences_rpc
    register_model_preferences_rpc(ctx)

    from .elm_plugin.lexical_search import register_search_rpc
    register_search_rpc(ctx)
