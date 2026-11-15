"""ELM in Hermes's memory-provider slot (`memory.provider: elm`).

Exactly the same permission rule as the general plugin: recall and capture only for a chat the
owner granted from a terminal (`local` Desktop/TUI chats) or turned on with `/elm on` where
that is allowed; never for ACP, messaging, cron, subagents or flush forks. No model or network
call happens here. While this provider serves a chat, the general `pre_llm_call` /
`post_llm_call` hooks step aside for it (`serving.py`), so nothing is injected or captured twice.
"""
import threading

from agent.memory_provider import MemoryProvider, RecallStatus

from . import serving
from .stock_runtime import Runtime, content_terms, plain_text, trivial

PROVIDER_NAME = 'elm'
DB_FILE = 'stock-v1.sqlite3'
# The surfaces the general plugin's hooks accept (stock_store.LOCAL plus unified `local`); `gui` is Desktop.
RECALL_SURFACES = frozenset(('local', 'cli', 'tui', 'desktop', 'gui'))


def surface_for(platform):
    """The agent's platform as ELM's permission surface; None = never recall (ACP, messaging, cron...)."""
    return platform if platform in RECALL_SURFACES else None


def bound_connection(hermes_home):
    """Connection factory pinned to one profile's home (provider contract: bind at initialize)."""
    def connect():
        from hermes_constants import reset_hermes_home_override, set_hermes_home_override
        from plugins.plugin_storage import plugin_db
        token = set_hermes_home_override(hermes_home)
        try:
            return plugin_db(PROVIDER_NAME, DB_FILE)
        finally:
            reset_hermes_home_override(token)
    return connect


class _NoCtx:
    """The provider never relies on ambient plugin context: it passes the surface explicitly."""
    def session_surface(self):
        return ''


class ElmMemoryProvider(MemoryProvider):
    def __init__(self, store_factory=None):
        # store_factory(hermes_home) -> Store; tests inject one. One instance per agent/profile.
        self._store_factory = store_factory
        self._runtime = None
        self._home = ''
        self._session = ''
        self._surface = None
        self._primary = False
        self._last = None
        self._lock = threading.Lock()

    @property
    def name(self):
        return PROVIDER_NAME

    def is_available(self):
        return True  # standard library + Hermes plugin storage only

    def initialize(self, session_id, **kwargs):
        from .stock_store import Store
        home = kwargs.get('hermes_home') or ''
        if not home:
            return  # never fall back to an ambient profile: stay inactive
        store = self._store_factory(home) if self._store_factory else Store(bound_connection(home))
        self._runtime = Runtime(_NoCtx(), store, provider_selected=lambda _sid: False)
        self._home, self._session = home, session_id or ''
        self._surface = surface_for(kwargs.get('platform'))
        # Subagents, cron runs and flush forks never read or write ELM memory.
        self._primary = kwargs.get('agent_context', 'primary') == 'primary'
        if self._active():
            serving.mark(self._home, self._session)

    def _active(self):
        return bool(self._runtime and self._primary and self._surface)

    def system_prompt_block(self):
        return ''  # static prompt stays cache-stable; recall goes through prefetch()

    def get_tool_schemas(self):
        return []  # `elm_memory` stays a general tool so the `memory` toolset gate cannot hide it

    def _key(self, session_id):
        return self._runtime.sid(session_id or self._session, platform=self._surface)

    def prefetch(self, query, *, session_id=''):
        with self._lock:
            self._last = None
        if not self._active():
            return ''
        try:
            message = plain_text(query)
            if trivial(message):
                return ''
            terms = content_terms(message)
            if not terms:
                return ''
            sid = self._key(session_id)  # raises when the chat has no grant / is not on
            search = ' '.join(terms).encode()[:512].decode('utf-8', errors='ignore').strip()
            output = self._runtime._recall(sid, search, automatic=True, terms=terms)
        except Exception:
            return ''
        if not output:
            return ''
        context = output['context']
        with self._lock:
            self._last = RecallStatus('ELM', context.count('"id":'))
        return context

    def recall_status(self):
        with self._lock:
            return self._last

    def sync_turn(self, user_content, assistant_content, *, session_id='', messages=None, turn_author=None):
        # Hermes already runs sync_turn on its serialized memory worker: write in order, here.
        if not self._active():
            return
        try:
            sid = self._key(session_id)
        except Exception:
            return
        try:
            self._runtime.remember_injected_from(sid, messages)  # no repeats after a restart
        except Exception:
            pass
        try:  # opt-in per chat; the store refuses when capture is off or the grant ended
            self._runtime.store.capture_turn(sid, plain_text(user_content), plain_text(assistant_content))
        except Exception:
            return

    def on_session_switch(self, new_session_id, *, parent_session_id='', reset=False, rewound=False, **kwargs):
        old, new = self._session, new_session_id or self._session
        if not self._runtime:
            return
        if self._active() and new != old:
            serving.unmark(self._home, old)
            serving.mark(self._home, new)
        self._session = new
        try:
            if kwargs.get('reason') == 'compression':
                # Only compression carries a chat's grant to a new ID; /branch and /resume do not.
                parent = parent_session_id or old
                if parent and parent != new:
                    self._runtime.store.link_rotation(parent, new)
                # Earlier injections may have been summarized away: allow them again.
                self._runtime._forget_injected(*(self._runtime.store.resolve_quiet(i) for i in (new, parent) if i))
            elif reset or rewound:
                self._runtime._forget_injected(self._runtime.store.resolve_quiet(new))
        except Exception:
            return

    def on_pre_compress(self, messages):
        return ''  # approved notes live in ELM's store already; nothing to hand the summarizer

    def shutdown(self):
        if self._active():
            serving.unmark(self._home, self._session)
        self._runtime = None
