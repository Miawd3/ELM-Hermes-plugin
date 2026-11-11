"""Independent offline regressions for native authority/publication boundaries.

Use run_product_tests.py; no live profile, model, network, or host edits.
Assertions express the contract and intentionally remain RED for review defects.
"""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import test_workspace_service as fixtures
import test_workspace_native as native
from agent.memory_manager import MemoryManager
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from plugins import memory

CANDIDATE = Path(__file__).resolve().parents[1]


class WorkspaceNativeReviewTests(unittest.TestCase):
    setUp = fixtures.WorkspaceServiceTests.setUp
    service = fixtures.WorkspaceServiceTests.service
    manager = native.WorkspaceNativeTests.manager

    def test_fresh_host_chat_can_recover_after_lazy_row_creation(self):
        service = self.service()
        service.setup(confirm=True)
        # Stock local Desktop/TUI eagerly builds an empty draft's agent before
        # prompt.submit persists its session row. Do not invent that row early.
        self.assertIsNone(self.db.get_session('fresh-draft'))
        manager, provider = self.manager('fresh-draft')
        # The host later persists the actual durable identity on first submit.
        self.db.create_session('fresh-draft', source='desktop')
        scope = service.capture('fresh-draft')['scope_id']
        record = service.create_record(dict(scope_id=scope, title='Fresh chat',
            text='Amber FRESH_CHAT_EVIDENCE.', domain='work', kind='explicit_fact',
            basis='explicit_statement', sources=[{'ref':'fictional:fresh-brief'}], state='approved'))
        result = json.loads(manager.handle_tool_call('elm_context', {'query':'amber'}))
        print('FRESH_CHAT_RESULT', json.dumps(result, sort_keys=True))
        self.assertNotIn('error', result,
            'An initialize-time absent host row permanently strands the native provider after the row exists')
        self.assertEqual(result['results'][0]['record_id'], record['id'])

    def test_native_publication_rechecks_host_move_after_serialization(self):
        from hermes_cli import projects_db
        service = self.service()
        service.setup(confirm=True)
        initial = service.capture('chat-a')
        service.set_privacy(initial['scope_id'], False)
        record = service.create_record(dict(scope_id=initial['context']['workspace_scope_id'],
            title='Work canary', text='Amber PRIOR_WORKSPACE_REVIEW_MARKER.', domain='work',
            kind='explicit_fact', basis='explicit_statement', sources=[{'ref':'fictional:work'}], state='approved'))
        other = projects_db.create_project(self.projects, name='Other review workspace')
        manager, provider = self.manager()
        positive = json.loads(manager.handle_tool_call('elm_context', {'query':'amber'}))
        self.assertEqual(positive['results'][0]['record_id'], record['id'])
        module = sys.modules[type(provider).__module__]
        encode = module._bounded_result
        def move_during_serialization(*args, **kwargs):
            projects_db.set_session_project(self.projects, 'chat-a', other)
            return encode(*args, **kwargs)
        with patch.object(module, '_bounded_result', side_effect=move_during_serialization):
            result = json.loads(manager.handle_tool_call('elm_context', {'query':'amber'}))
        self.assertEqual(result.get('error'), 'scope_changed', result)
        self.assertNotIn(record['text'], str(result))
        self.assertEqual(json.loads(manager.handle_tool_call('elm_context', {'query':'amber'}))['results'], [])

    def test_native_publication_rechecks_correction_and_deletion(self):
        service = self.service()
        service.setup(confirm=True)
        scope = service.capture('chat-a')['scope_id']
        record = service.create_record(dict(scope_id=scope, title='Inference canary',
            text='Amber OLD_REVIEW_INFERENCE.', domain='work', kind='interpretation',
            basis='inference', sources=[{'ref':'fictional:source'}], state='approved'))
        manager, provider = self.manager()
        initial = json.loads(manager.handle_tool_call('elm_context', {'query':'amber'}))['results'][0]
        self.assertEqual((initial['kind'], initial['basis']), ('interpretation', 'inference'))
        self.assertFalse(initial['executable'])
        module = sys.modules[type(provider).__module__]
        encode = module._bounded_result
        def correct_during_serialization(*args, **kwargs):
            service.correct(record['id'], record['revision'], {'text':'Amber NEW_REVIEW_INFERENCE.'})
            return encode(*args, **kwargs)
        with patch.object(module, '_bounded_result', side_effect=correct_during_serialization):
            stale = json.loads(manager.handle_tool_call('elm_read', {'section':initial['section']}))
        self.assertEqual(stale.get('error'), 'scope_changed', stale)
        self.assertNotIn('OLD_REVIEW_INFERENCE', str(stale))
        current = json.loads(manager.handle_tool_call('elm_context', {'query':'amber'}))['results'][0]
        self.assertIn('NEW_REVIEW_INFERENCE', current['text'])
        self.assertEqual((current['kind'], current['basis']), ('interpretation', 'inference'))
        def delete_during_serialization(*args, **kwargs):
            preview = service.delete_preview(record['id'])
            service.delete(record['id'], preview['preview_token'])
            return encode(*args, **kwargs)
        with patch.object(module, '_bounded_result', side_effect=delete_during_serialization):
            erased = json.loads(manager.handle_tool_call('elm_read', {'section':current['section']}))
        self.assertEqual(erased.get('error'), 'scope_changed', erased)
        self.assertNotIn('NEW_REVIEW_INFERENCE', str(erased))
        self.assertEqual(service.capture('chat-a')['records'], [])

    def test_delegated_native_provider_cannot_create_a_pending_proposal(self):
        service = self.service()
        service.setup(confirm=True)
        token = set_hermes_home_override(self.home)
        self.addCleanup(reset_hermes_home_override, token)
        with patch.object(memory, 'find_provider_dir', return_value=CANDIDATE):
            provider = memory.load_memory_provider('elm')
        manager = MemoryManager()
        manager.add_provider(provider)
        manager.initialize_all(session_id='chat-a', hermes_home=str(self.home), agent_context='subagent')
        self.addCleanup(manager.shutdown_all)
        result = json.loads(manager.handle_tool_call('elm_propose', dict(title='Blocked proposal',
            text='Amber delegate proposal.', domain='work', kind='explicit_fact', basis='explicit_statement',
            sources=[{'ref':'fictional:delegate'}])))
        self.assertEqual(result.get('error'), 'write_blocked', result)
        scope = service.capture('chat-a')['scope_id']
        self.assertEqual(service.store.list_records(scope), [])

    def test_workspace_setup_during_warm_legacy_delivery_withholds_packet(self):
        from elm_plugin.engine import run_engine
        token = set_hermes_home_override(self.home)
        self.addCleanup(reset_hermes_home_override, token)
        with patch.object(memory, 'find_provider_dir', return_value=CANDIDATE):
            provider = memory.load_memory_provider('elm')
        self.assertEqual(type(provider).__name__, 'ElmMemoryProvider')
        root = self.home/'legacy-review-source'
        run_engine(self.home, root, 'init', '--project', 'lantern')
        (root/'20_projects/lantern/DECISIONS.md').write_text(
            'Title: Lantern release decisions\nScope: lantern only\nTags: lantern, deployment\n'
            'Status: active\nSummary: Lantern rollout.\n\n# Lantern release decisions\n\n'
            '## Deployment\n\nAmber canary requires LEGACY_ONLY_REVIEW_MARKER rollback.\n', encoding='utf-8')
        run_engine(self.home, root, 'sync')
        provider.save_config(dict(root=str(root), project='lantern', mode='read-only', budget=700,
            budget_mode='legacy-estimate', recall_mode='legacy-background'), str(self.home))
        manager = MemoryManager(external_prefetch_timeout=10)
        manager.add_provider(provider)
        manager.initialize_all(session_id='chat-a', hermes_home=str(self.home), platform='desktop')
        self.addCleanup(manager.shutdown_all)
        query = 'amber canary rollback'
        provider.queue_prefetch(query, session_id='chat-a')
        self.assertIsNotNone(provider._worker)
        provider._worker.join(30)
        self.assertFalse(provider._worker.is_alive(), 'Owned background work must finish')
        control = manager.prefetch_all(query, session_id='chat-a')
        self.assertIn('LEGACY_ONLY_REVIEW_MARKER', control, 'Positive control must use real cached ELM evidence')
        module = sys.modules[type(provider).__module__]
        original = module.prepare_recall
        def setup_during_delivery(*args, **kwargs):
            self.service().setup(confirm=True)
            return original(*args, **kwargs)
        with patch.object(module, 'prepare_recall', side_effect=setup_during_delivery):
            late = manager.prefetch_all(query, session_id='chat-a')
        self.assertTrue(self.service().mode_present(self.home))
        print('LATE_LEGACY_PACKET', repr(late))
        self.assertEqual(late, '', 'Legacy background evidence escaped after explicit workspace setup')


if __name__ == '__main__':
    unittest.main(verbosity=2)
