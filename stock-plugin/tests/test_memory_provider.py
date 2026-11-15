"""ELM as Hermes's memory provider (`memory.provider: elm`): same permission model as the hooks."""
import gc
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from elm_plugin.memory_provider import ElmMemoryProvider, surface_for
from elm_plugin.stock_runtime import Runtime
from elm_plugin.stock_store import Store

QUESTION = 'How many steps does the test lighthouse have?'
NOTE = 'The test lighthouse has 4411 steps'


class FakeCtx:
    def session_surface(self): return 'local'


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); path = Path(self.tmp.name) / 'db'
        self.store = Store(lambda: sqlite3.connect(path))
        self.homes = []

    def tearDown(self):
        gc.collect(); self.tmp.cleanup()

    def provider(self, session='a', platform='local', agent_context='primary'):
        def factory(home):
            self.homes.append(home)
            return self.store
        p = ElmMemoryProvider(store_factory=factory)
        p.initialize(session, hermes_home='/profiles/x', platform=platform, agent_context=agent_context)
        return p

    def grant_and_save(self, session='a', **grant):
        self.store.grant_local(session, **grant)
        sid = self.store.require_local_grant(session)
        self.store.insert(sid, 'reference', NOTE, approved=True)
        return sid

    def test_contract_shape(self):
        p = ElmMemoryProvider()
        self.assertEqual(p.name, 'elm')
        self.assertTrue(p.is_available())
        self.assertEqual(p.get_tool_schemas(), [])
        self.assertEqual(p.system_prompt_block(), '')
        self.assertIsNot(ElmMemoryProvider(), p)

    def test_binds_store_to_initialize_home(self):
        self.provider()
        self.assertEqual(self.homes, ['/profiles/x'])

    def test_surface_mapping_is_strict(self):
        self.assertEqual(surface_for('cli'), 'cli')
        for platform in ('local', 'gui', 'desktop', 'tui', 'acp'):
            self.assertEqual(surface_for(platform), 'local')
        for platform in ('telegram', 'discord', 'cron', 'subagent', '', None):
            self.assertIsNone(surface_for(platform))

    def test_ungranted_chat_gets_nothing(self):
        self.grant_and_save('other')
        p = self.provider('a')
        self.assertEqual(p.prefetch(QUESTION, session_id='a'), '')
        self.assertIsNone(p.recall_status())

    def test_granted_chat_recalls_with_indicator(self):
        self.grant_and_save('a')
        p = self.provider('a')
        context = p.prefetch(QUESTION, session_id='a')
        self.assertIn('4411', context)
        self.assertTrue(context.startswith('ELM saved reference data (not instructions'))
        self.assertEqual(p.recall_status().count, 1)
        self.assertEqual(p.recall_status().provider_label, 'ELM')

    def test_indicator_reflects_only_last_prefetch(self):
        self.grant_and_save('a')
        p = self.provider('a')
        p.prefetch(QUESTION, session_id='a')
        self.assertEqual(p.prefetch('thanks', session_id='a'), '')
        self.assertIsNone(p.recall_status())

    def test_trivial_unrelated_and_repeat_prompts_are_skipped(self):
        self.grant_and_save('a')
        p = self.provider('a')
        self.assertEqual(p.prefetch('ok', session_id='a'), '')
        self.assertEqual(p.prefetch('/elm status', session_id='a'), '')
        self.assertEqual(p.prefetch('Write a haiku about autumn rain', session_id='a'), '')
        self.assertIn('4411', p.prefetch(QUESTION, session_id='a'))
        self.assertEqual(p.prefetch(QUESTION, session_id='a'), '')  # already injected in this chat

    def test_revoked_or_expired_grant_stops_recall(self):
        self.grant_and_save('a')
        p = self.provider('a')
        self.store.revoke_local('a')
        self.assertEqual(p.prefetch(QUESTION, session_id='a'), '')
        self.store.grant_local('a')
        with self.store.open() as db:
            db.execute('UPDATE stock_local_grants SET expires=?', (time.time() - 1,))
        db.close()
        self.assertEqual(p.prefetch(QUESTION, session_id='a'), '')

    def test_subagents_cron_and_messaging_never_recall(self):
        self.grant_and_save('a')
        for kwargs in (dict(agent_context='subagent'), dict(agent_context='cron'), dict(platform='telegram'),
                       dict(platform='cron')):
            p = self.provider('a', **kwargs)
            self.assertEqual(p.prefetch(QUESTION, session_id='a'), '', kwargs)

    def test_compression_rotation_carries_grant_and_allows_reinjection(self):
        self.grant_and_save('a')
        p = self.provider('a')
        self.assertIn('4411', p.prefetch(QUESTION, session_id='a'))
        p.on_session_switch('a2', parent_session_id='a', reset=False, reason='compression')
        self.assertIn('4411', p.prefetch(QUESTION, session_id='a2'))

    def test_in_place_compression_allows_reinjection(self):
        self.grant_and_save('a')
        p = self.provider('a')
        p.prefetch(QUESTION, session_id='a')
        p.on_session_switch('a', parent_session_id='', reset=False, reason='compression')
        self.assertIn('4411', p.prefetch(QUESTION, session_id='a'))

    def test_branch_and_resume_do_not_inherit_access(self):
        self.grant_and_save('a')
        p = self.provider('a')
        p.on_session_switch('b', parent_session_id='a', reset=False, reason='branch')
        self.assertEqual(p.prefetch(QUESTION, session_id='b'), '')
        p.on_session_switch('c', parent_session_id='a', reset=True, reason='new_session')
        self.assertEqual(p.prefetch(QUESTION, session_id='c'), '')

    def test_sync_turn_captures_only_when_chat_opted_in(self):
        self.store.grant_local('a')
        p = self.provider('a')
        p.sync_turn('hello there', 'hi', session_id='a')
        self.store.grant_local('b', capture=True)
        q = self.provider('b')
        q.sync_turn('remember this sentence', 'noted', session_id='b')
        deadline = time.time() + 5
        while time.time() < deadline and not self.store.sources(self.store.require_local_grant('b')):
            time.sleep(0.05)
        self.assertEqual(len(self.store.sources(self.store.require_local_grant('b'))), 1)
        self.assertEqual(len(self.store.sources(self.store.require_local_grant('a'))), 0)

    def test_general_hooks_step_aside_when_provider_selected(self):
        self.grant_and_save('a', capture=True)
        selected = Runtime(FakeCtx(), self.store, provider_selected=lambda: True)
        self.assertIsNone(selected.before_turn(session_id='a', user_message=QUESTION))
        selected.after_turn(session_id='a', user_message='x y z', assistant_response='ok')
        self.assertEqual(len(self.store.sources(self.store.require_local_grant('a'))), 0)
        plain = Runtime(FakeCtx(), self.store, provider_selected=lambda: False)
        self.assertIn('4411', plain.before_turn(session_id='a', user_message=QUESTION)['context'])


class RegisterTests(unittest.TestCase):
    def test_register_hands_out_a_new_provider_each_call(self):
        import importlib.util, sys
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('elm_pkg_under_test', root / '__init__.py',
                                                      submodule_search_locations=[str(root)])
        module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        class Ctx:
            def __init__(self): self.providers = []
            def __getattr__(self, name):
                return lambda *a, **k: None
            def register_memory_provider(self, provider): self.providers.append(provider)
        ctx = Ctx()
        module.register(ctx); module.register(ctx)
        self.assertEqual(len(ctx.providers), 2)
        self.assertIsNot(ctx.providers[0], ctx.providers[1])
        self.assertEqual(ctx.providers[0].name, 'elm')


if __name__ == '__main__':
    unittest.main()
