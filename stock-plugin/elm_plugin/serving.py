"""Which chats the ELM memory provider is serving right now, in this process.

The general hooks step aside exactly for those chats, so a note is never injected (or a turn
captured) twice, even right after `memory.provider` was changed and before Hermes rebuilt the
agent. Hermes can import this plugin twice (general loader and memory loader, under different
module names), so the set lives in one shared `sys.modules` entry. Keys are (profile home,
session id): one gateway process can serve several profiles.
"""
import os
import sys
import threading
import types

_KEY = '_elm_hermes_plugin_serving'


def _registry():
    module = sys.modules.get(_KEY)
    if module is None:
        fresh = types.ModuleType(_KEY)
        fresh.lock, fresh.sessions = threading.Lock(), {}
        module = sys.modules.setdefault(_KEY, fresh)
    return module


def _home_key(home):
    return os.path.normcase(os.path.realpath(str(home))) if home else ''


def mark(home, session_id):
    if not (home and session_id):
        return
    registry = _registry()
    key = (_home_key(home), session_id)
    with registry.lock:
        registry.sessions[key] = registry.sessions.get(key, 0) + 1


def unmark(home, session_id):
    if not (home and session_id):
        return
    registry = _registry()
    key = (_home_key(home), session_id)
    with registry.lock:
        count = registry.sessions.get(key, 0) - 1
        if count > 0:
            registry.sessions[key] = count
        else:
            registry.sessions.pop(key, None)


def serving(home, session_id):
    if not (home and session_id):
        return False
    registry = _registry()
    with registry.lock:
        return (_home_key(home), session_id) in registry.sessions


def current_home():
    try:
        from hermes_constants import get_hermes_home
        return str(get_hermes_home())
    except Exception:
        return ''
