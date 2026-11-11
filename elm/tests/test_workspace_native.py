"""Actual host loader + MemoryManager dispatch; no live installation/activation.

Only provider directory discovery is redirected to this candidate source. The
real loader/registration/manager, host databases, store and ELM all execute.
"""
import inspect
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_workspace_service as fixtures
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from agent.memory_manager import MemoryManager
from plugins import memory

CANDIDATE = Path(__file__).resolve().parents[1]


class WorkspaceNativeTests(unittest.TestCase):
    setUp = fixtures.WorkspaceServiceTests.setUp
    service = fixtures.WorkspaceServiceTests.service

    def manager(self, session_id='chat-a'):
        token = set_hermes_home_override(self.home)
        self.addCleanup(reset_hermes_home_override, token)
        with patch.object(memory, 'find_provider_dir', return_value=CANDIDATE):
            provider = memory.load_memory_provider('elm')
        self.assertIsNotNone(provider)
        self.assertTrue(Path(inspect.getfile(type(provider))).resolve().is_relative_to(CANDIDATE))
        self.assertTrue(provider.is_available(), 'Explicit workspace setup must not require legacy elm.json')
        manager = MemoryManager()
        manager.add_provider(provider)
        manager.initialize_all(session_id=session_id, hermes_home=str(self.home), platform='desktop')
        self.addCleanup(manager.shutdown_all)
        return manager, provider

    def test_real_native_context_read_and_pending_proposal(self):
        service = self.service()
        service.setup(confirm=True)
        scope = service.capture('chat-a')['scope_id']
        record = service.create_record(dict(scope_id=scope, title='Canary',
            text='Amber canary requires signed rollback.', domain='work', kind='explicit_fact',
            basis='explicit_statement', sources=[{'ref':'fictional:brief'}], state='approved'))
        manager, provider = self.manager()
        self.assertTrue(manager.has_tool('elm_context'))
        self.assertTrue(manager.has_tool('elm_read'))
        self.assertTrue(manager.has_tool('elm_propose'))
        self.assertFalse(manager.has_tool('elm_note'))
        value = json.loads(manager.handle_tool_call('elm_context', {'query':'amber canary'}))
        self.assertNotIn('error', value, value)
        self.assertNotIn('_publication', value)
        hit = value['results'][0]
        self.assertEqual(hit['record_id'], record['id'])
        self.assertEqual(hit['text'], record['text'])
        self.assertFalse(hit['executable'])
        read = json.loads(manager.handle_tool_call('elm_read', {'section':hit['section']}))
        self.assertEqual(read['text'], record['text'])
        proposal = json.loads(manager.handle_tool_call('elm_propose', dict(title='Draft', text='New amber note.',
            domain='work', kind='observation', basis='direct_observation', sources=[{'ref':'fictional:turn'}])))
        self.assertEqual(proposal['state'], 'pending', proposal)
        self.assertEqual(proposal['scope_id'], scope)
        self.assertEqual(service.store.get(proposal['id'])['state'], 'pending')
        self.assertEqual([r['id'] for r in service.capture('chat-a')['records']], [record['id']])
        for injected in ({'session_id':'chat-b'}, {'scope_id':'personal'}, {'root':'C:/unrelated'}, {'state':'approved'}):
            refused = json.loads(manager.handle_tool_call('elm_context', {'query':'amber', **injected}))
            self.assertEqual(refused['error'], 'invalid_arguments')
        status = json.loads(manager.handle_tool_call('elm_status', {}))
        self.assertEqual(status['mode'], 'workspace')
        self.assertFalse(status['automatic_learning'])
        self.assertFalse(status['automatic_recall'])
        self.assertEqual(manager.prefetch_all('amber canary', session_id='chat-a'), '')
        self.assertFalse((self.home/'elm.json').exists())
    def test_legacy_surface_stays_available_until_explicit_workspace_setup(self):
        from elm_plugin.engine import run_engine
        token = set_hermes_home_override(self.home)
        self.addCleanup(reset_hermes_home_override, token)
        with patch.object(memory, 'find_provider_dir', return_value=CANDIDATE):
            provider = memory.load_memory_provider('elm')
        self.assertEqual(type(provider).__name__, 'ElmMemoryProvider')
        names = {t['name'] for t in provider.get_tool_schemas()}
        self.assertIn('elm_note', names)
        self.assertNotIn('elm_propose', names)
        legacy = self.home/'fictional-legacy'
        run_engine(self.home, legacy, 'init', '--project', 'lantern')
        provider.save_config(dict(root=str(legacy), project='lantern', mode='read-only',
            budget=700, budget_mode='legacy-estimate', recall_mode='explicit-only'), str(self.home))
        manager = MemoryManager()
        manager.add_provider(provider)
        manager.initialize_all(session_id='chat-a', hermes_home=str(self.home), platform='desktop')
        self.addCleanup(manager.shutdown_all)
        initial = json.loads(manager.handle_tool_call('elm_status', {}))
        self.assertTrue(initial['healthy'], initial)
        binding_bytes = (self.home/'elm.json').read_bytes()
        self.service().setup(confirm=True)
        blocked = json.loads(manager.handle_tool_call('elm_status', {}))
        self.assertEqual(blocked.get('error'), 'workspace_restart_required', blocked)
        self.assertEqual((self.home/'elm.json').read_bytes(), binding_bytes)
        with patch.object(memory, 'find_provider_dir', return_value=CANDIDATE):
            replacement = memory.load_memory_provider('elm')
        self.assertEqual(type(replacement).__name__, 'WorkspaceMemoryProvider')
    def test_large_provenance_is_bounded_without_losing_type_or_exact_text(self):
        service = self.service()
        service.setup(confirm=True)
        scope = service.capture('chat-a')['scope_id']
        sources = [{'ref':f'fictional:long-source-{i}', 'quote':'Q' * 16384} for i in range(3)]
        record = service.create_record(dict(scope_id=scope, title='Large reference',
            text='Amber canary detailed source. ' * 300, domain='reference', kind='summary',
            basis='inference', sources=sources, state='approved'))
        manager, provider = self.manager()
        wire = manager.handle_tool_call('elm_context', {'query':'amber canary'})
        self.assertLessEqual(len(wire), 12000, 'Native memory output has no bounded delivery contract')
        result = json.loads(wire)
        self.assertNotIn('error', result, result)
        hit = result['results'][0]
        self.assertEqual(hit['kind'], 'summary')
        self.assertEqual(hit['basis'], 'inference')
        self.assertEqual(hit['text'], record['text'][hit['start']:hit['end']])
        self.assertTrue(hit['source_quotes_omitted'])
        self.assertEqual(hit['source_count'], len(sources))
        self.assertEqual(hit['next_source_offset'], 2)
        self.assertTrue(all('quote' not in source for source in hit['sources']))
        self.assertEqual(hit['section_navigation']['first']['part'], 1)
        self.assertEqual(hit['section_navigation']['last']['part'], hit['record_section_count'])
        if hit['part'] < hit['record_section_count']:
            self.assertEqual(hit['section_navigation']['next']['part'], hit['part']+1)
        else:
            self.assertIsNone(hit['section_navigation']['next'])
        exact_wire = manager.handle_tool_call('elm_read', {'section':hit['section'], 'source_offset':2})
        self.assertLessEqual(len(exact_wire), 12000)
        exact = json.loads(exact_wire)
        self.assertEqual(exact['text'], hit['text'])
        self.assertEqual(exact['basis'], 'inference')
        self.assertEqual(exact['sources'], [{'ref':sources[2]['ref']}])
        self.assertIsNone(exact['next_source_offset'])
        pending_text = 'Fictional proposed material. ' * 2000
        receipt_wire = manager.handle_tool_call('elm_propose', dict(title='Large pending note', text=pending_text,
            domain='reference', kind='summary', basis='inference', sources=[{'ref':'fictional:proposal'}]))
        self.assertLessEqual(len(receipt_wire), 12000)
        receipt = json.loads(receipt_wire)
        self.assertEqual(receipt['state'], 'pending')
        self.assertNotIn('text', receipt)
        self.assertEqual(service.store.get(receipt['id'])['text'], pending_text)
    def test_revocation_during_native_serialization_withholds_late_context_and_read(self):
        import sys
        service = self.service()
        service.setup(confirm=True)
        scope = service.capture('chat-a')['scope_id']
        card = service.create_record(dict(scope_id='personal', title='Communication',
            text='Use amber concise paragraphs.', domain='user', kind='preference', topic='communication',
            basis='explicit_statement', sources=[{'ref':'fictional:private-card'}], state='approved'))
        manager, provider = self.manager()
        module = sys.modules[type(provider).__module__]
        real_encode = module._bounded_result
        for tool in ('elm_context', 'elm_read'):
            with self.subTest(tool=tool):
                service.grant('personal', scope, [card['id']])
                located = json.loads(manager.handle_tool_call('elm_context', {'query':'amber concise'}))['results'][0]
                args = {'query':'amber concise'} if tool == 'elm_context' else {'section':located['section']}
                def revoke_during_serialization(result, name, source_offset=0):
                    service.revoke('personal', scope, [card['id']])
                    return real_encode(result, name, source_offset)
                with patch.object(module, '_bounded_result', side_effect=revoke_during_serialization):
                    result = json.loads(manager.handle_tool_call(tool, args))
                self.assertEqual(result.get('error'), 'scope_changed', result)
                self.assertNotIn(card['text'], str(result))
                self.assertEqual(service.capture('chat-a')['records'], [])
    def test_session_switch_and_wrong_profile_never_emit_the_prior_chat(self):
        import sys
        service = self.service()
        service.setup(confirm=True)
        scope = service.capture('chat-a')['scope_id']
        record = service.create_record(dict(scope_id=scope, title='Private canary',
            text='Amber ORIGINAL_PRIVATE_CONTEXT.', domain='work', kind='explicit_fact',
            basis='explicit_statement', sources=[{'ref':'fictional:private'}], state='approved'))
        manager, provider = self.manager()
        initial = json.loads(manager.handle_tool_call('elm_context', {'query':'amber'}))
        old = initial['results'][0]['section']
        module = sys.modules[type(provider).__module__]
        real_encode = module._bounded_result
        def switch_during_serialization(result, name, offset=0):
            manager.on_session_switch('chat-b', reset=True)
            return real_encode(result, name, offset)
        with patch.object(module, '_bounded_result', side_effect=switch_during_serialization):
            late = json.loads(manager.handle_tool_call('elm_context', {'query':'amber'}))
        self.assertEqual(late.get('error'), 'session_changed', late)
        self.assertNotIn(record['text'], str(late))
        self.assertEqual(json.loads(manager.handle_tool_call('elm_context', {'query':'amber'}))['results'], [])
        refused = json.loads(manager.handle_tool_call('elm_read', {'section':old}))
        self.assertEqual(refused.get('error'), 'section_not_visible', refused)
        other = self.home/'other-profile'
        other.mkdir()
        token = set_hermes_home_override(other)
        try:
            foreign = json.loads(manager.handle_tool_call('elm_context', {'query':'amber'}))
            self.assertIn('error', foreign)
            self.assertNotIn('ORIGINAL_PRIVATE_CONTEXT', str(foreign))
        finally:
            reset_hermes_home_override(token)
        manager.on_session_switch('missing-session', reset=True)
        missing = json.loads(manager.handle_tool_call('elm_context', {'query':'amber'}))
        self.assertEqual(missing.get('error'), 'session_unavailable', missing)
        self.assertNotIn('ORIGINAL_PRIVATE_CONTEXT', str(missing))
    def test_workspace_setup_during_legacy_read_withholds_the_late_legacy_result(self):
        import sys
        from elm_plugin.engine import run_engine
        token = set_hermes_home_override(self.home)
        self.addCleanup(reset_hermes_home_override, token)
        with patch.object(memory, 'find_provider_dir', return_value=CANDIDATE):
            provider = memory.load_memory_provider('elm')
        root = self.home/'late-legacy'
        run_engine(self.home, root, 'init', '--project', 'lantern')
        provider.save_config(dict(root=str(root), project='lantern', mode='read-only', budget=700,
            budget_mode='legacy-estimate', recall_mode='explicit-only'), str(self.home))
        manager = MemoryManager()
        manager.add_provider(provider)
        manager.initialize_all(session_id='chat-a', hermes_home=str(self.home))
        self.addCleanup(manager.shutdown_all)
        module = sys.modules[type(provider).__module__]
        real_engine = module.run_engine
        def setup_after_engine_read(*args, **kwargs):
            result = real_engine(*args, **kwargs)
            self.service().setup(confirm=True)
            return result
        with patch.object(module, 'run_engine', side_effect=setup_after_engine_read):
            result = json.loads(manager.handle_tool_call('elm_status', {}))
        self.assertEqual(result.get('error'), 'workspace_restart_required', result)
        self.assertNotIn('root_id', result)
    def test_workspace_setup_before_legacy_dispatch_does_not_write_the_old_store(self):
        import sys
        from elm_plugin.engine import run_engine
        token = set_hermes_home_override(self.home)
        self.addCleanup(reset_hermes_home_override, token)
        with patch.object(memory, 'find_provider_dir', return_value=CANDIDATE):
            provider = memory.load_memory_provider('elm')
        root = self.home/'legacy-dispatch'
        run_engine(self.home, root, 'init', '--project', 'lantern')
        provider.save_config(dict(root=str(root), project='lantern', mode='proposal-only', budget=700,
            budget_mode='legacy-estimate', recall_mode='explicit-only'), str(self.home))
        manager = MemoryManager()
        manager.add_provider(provider)
        manager.initialize_all(session_id='chat-a', hermes_home=str(self.home))
        self.addCleanup(manager.shutdown_all)
        module = sys.modules[type(provider).__module__]
        real_engine = module.run_engine
        def setup_after_readiness(*args, **kwargs):
            result = real_engine(*args, **kwargs)
            if args[2] == 'status' and not self.service().mode_present(self.home):
                self.service().setup(confirm=True)
            return result
        note = dict(operation='propose', submission_id='submission_11111111-1111-4111-8111-111111111111',
            subject='Lantern', predicate='requires', object='signed rollback', valid_from='2026-11-10T00:00:00+00:00',
            rationale='Fictional transition regression.', source_refs=[])
        with patch.object(module, 'run_engine', side_effect=setup_after_readiness):
            result = json.loads(manager.handle_tool_call('elm_note', note))
        self.assertEqual(result.get('error'), 'workspace_restart_required', result)
        history = run_engine(self.home, root, 'history', '--project', 'lantern', '--no-sync')
        self.assertEqual(history['proposals'], [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
