"""Memory-aware routing (delegation.backend: elm): routes, learning, privacy and purge.

Several tests reproduce defects found by an independent privacy review (numbers in comments)."""
import gc
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from elm_plugin.routing import ElmDelegationProvider, configured_agents, score_agents
from elm_plugin.stock_runtime import Runtime, routing_terms
from elm_plugin.stock_store import Store

AGENTS = {
    'quick': {'description': 'Small, fast tasks', 'model': 'flash', 'provider': 'deepseek'},
    'deep': {'description': 'Hard reasoning', 'model': 'pro', 'provider': 'deepseek', 'reasoning_effort': 'high'},
    'coder': {'description': 'Code changes', 'profile': 'coder'},
}
GOAL = 'Refactor the payment parser module and add unit tests'
SIMILAR = 'Add unit tests for the payment parser'


def config(agents=AGENTS, **settings):
    return {'backend': 'elm', 'model': 'parent-model', 'service_tier': 'fast',
            'backends': {'elm': dict(settings, agents=agents)}}


class Ctx:
    def __init__(self): self.surface = 'local'
    def session_surface(self): return self.surface


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); path = Path(self.tmp.name) / 'db'
        self.store = Store(lambda: sqlite3.connect(path))
        self.ctx = Ctx()
        self.runtime = Runtime(self.ctx, self.store, provider_selected=lambda _sid: False)
        self.caller = 'chat-a'
        self.provider = ElmDelegationProvider(runtime=self.runtime, session_id=lambda: self.caller)

    def tearDown(self):
        gc.collect(); self.tmp.cleanup()

    def route(self, goal, agent=None, cfg=None, parent='chat-a'):
        self.caller = parent
        task = {'goal': goal, 'context': '', 'index': 0}
        if agent:
            task['agent'] = agent
        return self.provider.route_task(task, cfg or config(default='quick'))

    def start(self, goal, child, parent='chat-a'):
        self.runtime.subagent_started(parent_session_id=parent, child_session_id=child, child_goal=goal)

    def stop(self, child, status='completed'):
        self.runtime.subagent_stopped(child_session_id=child, child_status=status, duration_ms=1200)

    def run_child(self, goal, child, status='completed', parent='chat-a', agent=None, cfg=None):
        route = self.route(goal, agent, cfg, parent)
        self.start(goal, child, parent)
        self.stop(child, status)
        return route

    def outcomes(self):
        with self.store.open() as db:
            rows = db.execute('SELECT agent,session,terms,ok FROM stock_route_outcomes ORDER BY id').fetchall()
        db.close()
        return rows

    # -- routes ---------------------------------------------------------------------------------

    def test_agents_are_validated(self):
        agents = configured_agents({'agents': {
            'ok': {'model': 'm', 'label': 'x', 'evil': 1}, 'Bad Name': {'model': 'm'}, 'empty': {},
            'nope': 'string', '../x': {'model': 'm'}}})
        self.assertEqual(list(agents), ['ok'])
        self.assertEqual(agents['ok']['route'], {'model': 'm'})
        self.assertEqual(configured_agents({}), {})
        self.assertEqual(configured_agents({'agents': ['a']}), {})

    def test_schema_and_description_are_deterministic(self):
        params = self.provider.task_parameters(config())
        self.assertEqual(params['agent']['enum'], ['coder', 'deep', 'quick'])
        self.assertEqual(params, self.provider.task_parameters(config()))
        description = self.provider.description(config())
        self.assertIn('- deep: Hard reasoning', description)
        self.assertEqual(description, self.provider.description(config()))
        self.assertEqual(self.provider.task_parameters(config(agents={})), {})
        self.assertEqual(self.provider.description(config(agents={})), '')

    def test_explicit_choice_and_profile_route(self):
        route = self.provider.route_task({'goal': 'x', 'agent': 'deep'}, config())
        self.assertEqual(route, {'model': 'pro', 'provider': 'deepseek', 'reasoning_effort': 'high', 'label': 'ELM: deep'})
        self.assertEqual(self.provider.route_task({'goal': 'x', 'agent': 'coder'}, config())['profile'], 'coder')

    def test_fallbacks_default_then_parent(self):
        self.assertEqual(self.provider.route_task({'goal': 'x'}, config(default='quick'))['label'], 'ELM: quick (default)')
        self.assertEqual(self.provider.route_task({'goal': 'x'}, config()), {'model': 'parent-model', 'label': 'ELM: parent model'})
        self.assertEqual(self.provider.route_task({'goal': 'x'}, config(agents={})), {'model': 'parent-model'})

    # -- learning -------------------------------------------------------------------------------

    def test_learns_from_results_in_a_granted_chat(self):
        self.store.grant_local('chat-a')
        self.run_child(GOAL, 'c1', agent='coder')
        self.run_child(GOAL, 'c2', agent='coder')
        route = self.route(SIMILAR)
        self.assertEqual(route['label'], 'ELM: coder (past results)')
        self.assertEqual(route['profile'], 'coder')
        self.assertEqual(self.route('Summarize this poem about autumn')['label'], 'ELM: quick (default)')

    def test_failures_count_against_an_agent_interrupts_do_not(self):
        self.store.grant_local('chat-a')
        goal = 'Translate the onboarding guide into Spanish'
        self.run_child(goal, 'c1', agent='quick', status='failed')
        self.run_child(goal, 'c2', agent='deep')
        self.run_child(goal, 'c3', agent='deep', status='interrupted')
        self.assertEqual([r[0] for r in self.outcomes()], ['quick', 'deep'])
        self.assertEqual(self.route(goal)['label'], 'ELM: deep (past results)')

    def test_learn_false_records_nothing(self):
        self.store.grant_local('chat-a')
        cfg = config(learn=False, default='quick')
        self.run_child(GOAL, 'c1', agent='coder', cfg=cfg)
        self.assertEqual(self.store.route_stats(), [])
        self.assertEqual(self.route(SIMILAR, cfg=cfg)['label'], 'ELM: quick (default)')

    # -- privacy (review findings) --------------------------------------------------------------

    def test_ungranted_local_chat_neither_records_nor_uses_history(self):
        self.store.grant_local('chat-a')
        self.run_child(GOAL, 'c1', agent='coder')
        self.run_child(GOAL, 'c2', parent='not-granted', agent='coder')
        self.assertEqual(len(self.outcomes()), 1)
        self.assertEqual(self.route(SIMILAR, parent='not-granted')['label'], 'ELM: quick (default)')  # review 4

    def test_desktop_and_cli_surfaces_need_elm_on(self):  # review 1
        for surface in ('cli', 'tui', 'desktop'):
            self.ctx.surface = surface
            self.run_child('Draft a letter about the rent dispute', 'x-' + surface, parent='off-' + surface, agent='deep')
        self.assertEqual(self.outcomes(), [])
        self.ctx.surface = 'desktop'
        self.runtime.command('on', session_id='on-desktop', platform='desktop')
        self.run_child('Draft a letter about the rent dispute', 'y', parent='on-desktop', agent='deep')
        self.assertEqual(len(self.outcomes()), 1)

    def test_same_goal_batch_is_credited_in_order(self):  # review 2
        self.store.grant_local('chat-a')
        self.route(GOAL, 'quick'); self.route(GOAL, 'deep'); self.route(GOAL)  # one batch: routes first
        self.start(GOAL, 'c1'); self.start(GOAL, 'c2'); self.start(GOAL, 'c3')  # then children in order
        self.stop('c1'); self.stop('c2'); self.stop('c3')
        self.assertEqual([r[0] for r in self.outcomes()], ['quick', 'deep', 'quick'])

    def test_other_chats_routes_are_never_consumed(self):  # review 3
        self.store.grant_local('chat-a'); self.store.grant_local('chat-b')
        self.route('Compare the two vendor contracts', 'deep', parent='chat-b')
        self.start('Compare the two vendor contracts', 'c1', parent='chat-a')
        self.stop('c1', 'failed')
        self.assertEqual(self.outcomes(), [])

    def test_parent_route_keeps_queue_aligned(self):
        self.store.grant_local('chat-a')
        self.route(GOAL, cfg=config()); self.route(GOAL, 'deep', cfg=config())  # parent route, then deep
        self.start(GOAL, 'c1'); self.start(GOAL, 'c2')
        self.stop('c1'); self.stop('c2')
        self.assertEqual([r[0] for r in self.outcomes()], ['deep'])

    def test_revoked_while_running_records_nothing(self):  # review 6
        self.store.grant_local('chat-a')
        self.route(GOAL, 'deep'); self.start(GOAL, 'c1')
        self.store.revoke_local('chat-a')
        self.stop('c1')
        self.assertEqual(self.outcomes(), [])

    def test_keywords_are_plain_words_only(self):  # review 5
        terms = routing_terms('Call api key sk_live_9fa7zqx2pklm phone 5551234567 about the invoice 2026')
        self.assertEqual(terms, ['call', 'api', 'key', 'phone', 'invoice'])
        self.assertLessEqual(len(routing_terms(' '.join(f'word{"x" * i}' for i in range(30)))), 12)

    def test_history_is_scoped_like_notes(self):  # review 4
        self.store.grant_local('chat-a'); self.store.grant_local('chat-b')
        self.run_child(GOAL, 'c1', agent='coder', parent='chat-a')
        self.assertEqual(self.route(SIMILAR, parent='chat-b')['label'], 'ELM: quick (default)')
        self.store.grant_local('chat-a', project='Payments'); self.store.grant_local('chat-b', project='Payments')
        self.assertEqual(self.route(SIMILAR, parent='chat-b')['label'], 'ELM: coder (past results)')
        self.store.grant_local('chat-c', user=True)
        self.assertEqual(self.route(SIMILAR, parent='chat-c')['label'], 'ELM: quick (default)')

    def test_no_task_text_is_stored(self):
        self.store.grant_local('chat-a')
        self.run_child('Write the quarterly report summary for finance', 'c1', agent='deep')
        self.run_child('Write the quarterly report summary for finance', 'c2', agent='deep', status='timeout')
        self.assertEqual(self.store.route_stats(), [{'agent': 'deep', 'runs': 2, 'succeeded': 1, 'avg_seconds': 1.2}])
        self.assertNotIn('Write the quarterly report summary for finance', json.dumps(self.outcomes()))

    def test_deleting_the_chat_purges_its_routing_rows(self):
        self.store.grant_local('chat-a'); self.store.grant_local('chat-b')
        self.run_child(GOAL, 'c1', agent='coder', parent='chat-a')
        self.route(GOAL, 'deep', parent='chat-a')  # still queued
        self.run_child('Refactor the billing parser module', 'c2', agent='coder', parent='chat-b')
        self.runtime.session_deleted(session_id='chat-a', reason='delete')
        self.assertEqual(self.store.route_stats()[0]['runs'], 1)
        with self.store.open() as db:
            queued = db.execute('SELECT COUNT(*) FROM stock_route_queue').fetchone()[0]
        db.close()
        self.assertEqual(queued, 0)
        self.runtime.session_deleted(session_id='chat-b', reason='archive')
        self.assertEqual(self.store.health()['routing_outcomes'], 1)

    def test_unknown_children_and_bad_input_are_ignored(self):
        self.stop('never-started')
        self.runtime.subagent_started(parent_session_id='chat-a', child_session_id='', child_goal='x')
        self.runtime.subagent_started(parent_session_id='chat-a', child_session_id='c', child_goal=None)
        self.assertEqual(self.store.route_stats(), [])

    def test_routing_survives_storage_failure(self):
        class Broken:
            def authorized(self, *_a, **_k): raise RuntimeError('db down')
        broken = ElmDelegationProvider(runtime=Broken(), session_id=lambda: 'chat-a')
        self.assertEqual(broken.route_task({'goal': 'x'}, config(default='quick'))['label'], 'ELM: quick (default)')
        self.assertEqual(broken.route_task({'goal': 'x', 'agent': 'deep'}, config())['label'], 'ELM: deep')
        self.assertEqual(ElmDelegationProvider().route_task({'goal': 'x'}, config(default='quick'))['label'], 'ELM: quick (default)')

    def test_score_requires_real_overlap(self):
        history = [('a', ['payment', 'parser'], True), ('b', ['poem'], True), ('x', ['payment', 'parser'], True)]
        self.assertEqual(score_agents(['payment', 'parser', 'tests'], history, {'a', 'b'}), {'a': 2})
        self.assertEqual(score_agents([], history, {'a'}), {})


if __name__ == '__main__':
    unittest.main()
