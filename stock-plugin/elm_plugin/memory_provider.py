"""ELM in Hermes's memory-provider slot (`memory.provider: elm`).

The same permission model as the general plugin applies: recall only for a chat that the
owner granted from a terminal (Desktop/TUI/ACP) or turned on with `/elm on` (classic CLI).
No model or network call happens here. When this provider is selected, the general
`pre_llm_call` / `post_llm_call` hooks step aside so a note is never injected twice.
"""
import threading

from agent.memory_provider import MemoryProvider, RecallStatus, spawn_context_thread

from .stock_runtime import Runtime, content_terms, plain_text, trivial

PROVIDER_NAME = 'elm'
DB_FILE = 'stock-v1.sqlite3'
# Clients whose chats are "local" sessions in unified Hermes: they need an exact-chat terminal grant.
GRANT_SURFACES = frozenset(('local', 'gui', 'desktop', 'tui', 'acp'))


def surface_for(platform):
    """Map the agent's platform to ELM's permission surface; None = never recall (messaging, cron...)."""
    if platform == 'cli':
        return 'cli'
    if platform in GRANT_SURFACES:
        return 'local'
    return None


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
        store = self._store_factory(home) if self._store_factory else Store(bound_connection(home))
        self._runtime = Runtime(_NoCtx(), store)
        self._session = session_id or ''
        self._surface = surface_for(kwargs.get('platform'))
        # Subagents, cron runs and flush forks never read or write ELM memory.
        self._primary = kwargs.get('agent_context', 'primary') == 'primary'

    def system_prompt_block(self):
        return ''  # static prompt stays cache-stable; recall goes through prefetch()

    def get_tool_schemas(self):
        return []  # `elm_memory` stays a general tool so the `memory` toolset gate cannot hide it

    def _key(self, session_id):
        return self._runtime.sid(session_id or self._session, platform=self._surface)

    def prefetch(self, query, *, session_id=''):
        with self._lock:
            self._last = None
        if not (self._runtime and self._primary and self._surface):
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
        count = context.count('"id":')
        with self._lock:
            self._last = RecallStatus('ELM', count)
        return context

    def recall_status(self):
        with self._lock:
            return self._last

    def sync_turn(self, user_content, assistant_content, *, session_id='', messages=None, turn_author=None):
        if not (self._runtime and self._primary and self._surface):
            return
        runtime, surface, target = self._runtime, self._surface, session_id or self._session

        def capture():
            try:  # opt-in per chat; store refuses when capture is off or the grant ended
                runtime.store.capture_turn(runtime.sid(target, platform=surface),
                                           plain_text(user_content), plain_text(assistant_content))
            except Exception:
                return
        spawn_context_thread(capture, name='elm-sync-turn').start()

    def on_session_switch(self, new_session_id, *, parent_session_id='', reset=False, rewound=False, **kwargs):
        old, self._session = self._session, new_session_id or self._session
        if not self._runtime:
            return
        try:
            if kwargs.get('reason') == 'compression':
                # Only compression carries a chat's grant to a new ID; /branch and /resume do not.
                parent = parent_session_id or old
                if parent and parent != new_session_id:
                    self._runtime.store.link_rotation(parent, new_session_id)
                # Earlier injections may have been summarized away: allow them again.
                self._runtime._forget_injected(*(self._runtime.store.resolve_quiet(i)
                                                 for i in (new_session_id, parent) if i))
            elif reset or rewound:
                self._runtime._forget_injected(self._runtime.store.resolve_quiet(new_session_id))
        except Exception:
            return

    def on_pre_compress(self, messages):
        return ''  # approved notes live in ELM's store already; nothing to hand the summarizer

    def shutdown(self):
        self._runtime = None
