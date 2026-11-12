"""Explicit current-chat logical filing. No model tools, legacy adoption or cwd changes."""

def register_chat_folders_rpc(ctx):
    try:
        from hermes_cli.plugin_chat_folders import chat_folder_capabilities, chat_folders
    except ImportError:
        return False
    if not chat_folder_capabilities()['available'] or not callable(getattr(ctx, 'register_rpc', None)):
        return False
    import threading
    lock = threading.Lock()
    active = True
    def close():
        nonlocal active
        with lock:
            active = False
    def handler(operation, fields):
        def run(params, **kwargs):
            with lock:
                if not active:
                    raise ValueError('Chat folders are unavailable')
                if type(params) is not dict or set(params) - {'session_id'} != set(fields):
                    raise ValueError('Invalid chat folder request fields')
                if operation != 'status' and params['confirm'] is not True:
                    raise ValueError('Explicit confirmation is required')
                return chat_folders(operation=operation,
                                    value=({'folder_id': params.get('folder_id'), 'label': params.get('label')}
                                           if operation == 'rename' else
                                           params.get('label') if operation == 'create' else params.get('folder_id')),
                                    expected_context=params.get('expected_context'),
                                    expected_revision=params.get('expected_revision'))
        return run
    ctx.register_rpc('chat_folders.status', handler('status', ()), memory_scope='local_read')
    common = ('expected_context', 'expected_revision', 'confirm')
    ctx.register_rpc('chat_folders.create', handler('create', (*common, 'label')))
    ctx.register_rpc('chat_folders.file', handler('file', (*common, 'folder_id')))
    ctx.register_rpc('chat_folders.rename', handler('rename', (*common, 'folder_id', 'label')))
    ctx.register_rpc('chat_folders.remove', handler('remove', (*common, 'folder_id')))
    ctx.register_rpc('chat_folders.undo', handler('undo', common))
    if callable(getattr(ctx, 'on_unload', None)):
        ctx.on_unload(close)
    return True
