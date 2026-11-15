"""Memory-aware routing (delegation.backend: elm): routes, learning, privacy and purge."""
import gc
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from elm_plugin.routing import ElmDelegationProvider, configured_agents, score_agents
from elm_plugin.stock_runtime import Runtime
from elm_plugin.stock_store import Store

AGENTS = {
    'quick': {'description': 'Small, fast tasks', 'model': 'flash', 'provider': 'deepseek'},
    'deep': {'description': 'Hard reasoning', 'model': 'pro', 'provider': 'deepseek', 'reasoning_effort': 'high'},
    'coder': {'description': 'Code changes', 'profile': 'coder'},
}


def config(agents=AGENTS, **settings):
    return {'backend': 'elm', 'model': 'parent-model', 'service_tier': 'fast',
            'backends': {'elm': dict(settings, agents=agents)}}


class FakeCtx:
    def session_surface(self): return 'local'


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); path = Path(self.tmp.name) / 'db'
        self.store = Store(lambda: sqlite3.connect(path))
        self.provider = ElmDelegationProvider(store_factory=lambda: self.store)
        self.runtime = Runtime(FakeCtx(), self.store, provider_selected=lambda: False)

    def tearDown(self):
        gc.collect(); self.tmp.cleanup()

    def run_child(self, goal, child, status='completed', parent='chat-a', agent=None, cfg=None):
        task = {'goal': goal, 'context': '', 'index': 0}
        if agent:
            task['agent'] = agent
        route = self.provider.route_task(task, cfg or config())
        self.runtime.subagent_started(parent_session_id=parent, child_session_id=child, child_goal=goal)
        self.runtime.subagent_stopped(child_session_id=child, child_status=status, duration_ms=1200)
        return route

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
        parent = self.provider.route_task({'goal': 'x'}, config())
        self.assertEqual(parent, {'model': 'parent-model', 'label': 'ELM: parent model'})
        self.assertEqual(self.provider.route_task({'goal': 'x'}, config(agents={})), {'model': 'parent-model'})

    def test_learns_from_results_in_granted_chats(self):
        self.store.grant_local('chat-a')
        goal = 'Refactor the payment parser module and add unit tests'
        self.run_child(goal, 'c1', agent='coder')
        self.run_child(goal, 'c2', agent='coder')
        similar = 'Add unit tests for the payment parser'
        route = self.provider.route_task({'goal': similar}, config(default='quick'))
        self.assertEqual(route['label'], 'ELM: coder (past results)')
        self.assertEqual(route['profile'], 'coder')
        unrelated = self.provider.route_task({'goal': 'Summarize this poem about autumn'}, config(default='quick'))
        self.assertEqual(unrelated['label'], 'ELM: quick (default)')

    def test_failures_count_against_an_agent(self):
        self.store.grant_local('chat-a')
        goal = 'Translate the onboarding guide into Spanish'
        self.run_child(goal, 'c1', agent='quick', status='failed')
        self.run_child(goal, 'c2', agent='deep')
        route = self.provider.route_task({'goal': goal}, config(default='quick'))
        self.assertEqual(route['label'], 'ELM: deep (past results)')

    def test_nothing_is_remembered_for_chats_without_elm(self):
        self.run_child('Refactor the payment parser module', 'c1', agent='coder', parent='not-granted')
        self.assertEqual(self.store.route_stats(), [])
        self.assertEqual(self.store.route_history(), [])

    def test_learn_false_records_nothing(self):
        self.store.grant_local('chat-a')
        cfg = config(learn=False, default='quick')
        self.run_child('Refactor the payment parser module', 'c1', agent='coder', cfg=cfg)
        self.assertEqual(self.store.route_stats(), [])
        self.assertEqual(self.provider.route_task({'goal': 'Refactor the payment parser'}, cfg)['label'], 'ELM: quick (default)')

    def test_stats_have_counts_only_and_history_has_keywords_only(self):
        self.store.grant_local('chat-a')
        self.run_child('Write the quarterly report summary for finance', 'c1', agent='deep')
        self.run_child('Write the quarterly report summary for finance', 'c2', agent='deep', status='timeout')
        self.assertEqual(self.store.route_stats(), [{'agent': 'deep', 'runs': 2, 'succeeded': 1, 'avg_seconds': 1.2}])
        for _agent, terms, _ok in self.store.route_history():
            self.assertNotIn('the', terms)
            self.assertLessEqual(len(terms), 12)
        with self.store.open() as db:
            text = json.dumps(db.execute('SELECT * FROM stock_route_outcomes').fetchall())
        db.close()
        self.assertNotIn('Write the quarterly report summary for finance', text)

    def test_deleting_the_chat_purges_its_routing_history(self):
        self.store.grant_local('chat-a'); self.store.grant_local('chat-b')
        self.run_child('Refactor the payment parser module', 'c1', agent='coder', parent='chat-a')
        self.run_child('Refactor the billing parser module', 'c2', agent='coder', parent='chat-b')
        self.runtime.session_deleted(session_id='chat-a', reason='delete')
        self.assertEqual(self.store.route_stats()[0]['runs'], 1)
        self.runtime.session_deleted(session_id='chat-b', reason='archive')
        self.assertEqual(self.store.route_stats()[0]['runs'], 1)
        self.assertEqual(self.store.health()['routing_outcomes'], 1)

    def test_unknown_children_and_bad_input_are_ignored(self):
        self.runtime.subagent_stopped(child_session_id='never-started', child_status='completed')
        self.runtime.subagent_started(parent_session_id='chat-a', child_session_id='', child_goal='x')
        self.runtime.subagent_started(parent_session_id='chat-a', child_session_id='c', child_goal=None)
        self.assertEqual(self.store.route_stats(), [])

    def test_routing_survives_storage_failure(self):
        broken = ElmDelegationProvider(store_factory=lambda: (_ for _ in ()).throw(RuntimeError('db down')))
        self.assertEqual(broken.route_task({'goal': 'x'}, config(default='quick'))['label'], 'ELM: quick (default)')
        self.assertEqual(broken.route_task({'goal': 'x', 'agent': 'deep'}, config())['label'], 'ELM: deep')

    def test_score_requires_real_overlap(self):
        history = [('a', ['payment', 'parser'], True), ('b', ['poem'], True), ('x', ['payment', 'parser'], True)]
        self.assertEqual(score_agents(['payment', 'parser', 'tests'], history, {'a', 'b'}), {'a': 2})
        self.assertEqual(score_agents([], history, {'a'}), {})


if __name__ == '__main__':
    unittest.main()
