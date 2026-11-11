"""Owner integration: real host identity + durable record repository."""
import importlib
import tempfile
import unittest
from pathlib import Path

from hermes_state import SessionDB
from hermes_cli import projects_db
from elm_plugin.workspace_records import RecordError


class WorkspaceServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='workspace-service-')
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.db = SessionDB(self.home/'state.db')
        self.addCleanup(self.db.close)
        self.projects = projects_db.connect(self.home/'projects.db')
        self.addCleanup(self.projects.close)
        self.project_id = projects_db.create_project(self.projects, name='Lantern')
        self.db.create_session('chat-a', source='desktop')
        self.db.create_session('chat-b', source='desktop')
        projects_db.set_session_project(self.projects, 'chat-a', self.project_id)
        projects_db.set_session_project(self.projects, 'chat-b', self.project_id)

    def service(self):
        try:
            module = importlib.import_module('elm_plugin.workspace_service')
        except ModuleNotFoundError as exc:
            if exc.name == 'elm_plugin.workspace_service':
                self.fail('The host-to-record service is not implemented')
            raise
        return module.WorkspaceService(self.home)

    def test_explicit_setup_and_human_inspection_do_not_grant_model_recall(self):
        s = self.service()
        root = self.home/'elm-workspaces'
        before = s.overview('chat-a')
        self.assertFalse(before['setup'])
        self.assertFalse(root.exists())
        self.assertFalse(before['status']['learning_enabled'])
        self.assertEqual(before['records'], [])
        self.assertTrue(s.setup(confirm=True)['initialized'])
        overview = s.overview('chat-a')
        private = overview['context']['chat_scope_id']
        workspace = overview['context']['workspace_scope_id']
        self.assertNotEqual(private, workspace)
        self.assertTrue(overview['context']['private'])
        record = s.create_record(dict(scope_id=workspace, title='Banner', text='Use indigo banners.',
            domain='work', kind='explicit_fact', basis='explicit_statement', topic='facts',
            sources=[{'ref':'fictional:brief-1','quote':'Use indigo banners.'}], state='approved'))
        inspection = s.overview('chat-a', scope_id=workspace)
        self.assertEqual([r['id'] for r in inspection['records']], [record['id']])
        self.assertEqual(s.capture('chat-a')['scope_id'], private)
        self.assertEqual(s.capture('chat-a')['records'], [])
        self.assertEqual(s.capture('chat-b')['records'], [])
        self.assertEqual(s.overview('chat-a')['context'], inspection['context'])
        # One persisted store, not a fresh hand-written response after reopening.
        self.assertEqual(self.service().overview('chat-a', workspace)['records'], inspection['records'])


    def test_model_proposal_is_forced_pending_and_cannot_select_scope_or_approval(self):
        s = self.service()
        s.setup(confirm=True)
        binding = s.capture('chat-a')
        payload = dict(title='Banner', text='Use indigo banners.', domain='work', kind='explicit_fact',
                       basis='explicit_statement', sources=[{'ref':'fictional:brief-1'}])
        self.assertTrue(callable(getattr(s, 'propose', None)), 'Model proposal boundary is missing')
        for injected in ({'state':'approved'}, {'scope_id':binding['context']['workspace_scope_id']},
                         {'root':'C:/unrelated'}, {'operation':'approve'}):
            with self.subTest(injected=injected), self.assertRaises(RecordError):
                s.propose('chat-a', {**payload, **injected})
        result = s.propose('chat-a', payload)
        self.assertEqual(result['state'], 'pending')
        self.assertEqual(result['scope_id'], binding['scope_id'])
        self.assertEqual(s.capture('chat-a')['records'], [])
        self.assertEqual(s.capture('chat-b')['records'], [])
        self.assertEqual(s.overview('chat-a')['records'][0]['id'], result['id'])


    def test_privacy_tightening_between_policy_and_snapshot_withholds_stale_scope(self):
        from unittest.mock import patch
        s = self.service()
        s.setup(confirm=True)
        initial = s.capture('chat-a')
        chat = s.store.get_scope(initial['scope_id'])
        s.store.put_scope(chat['id'], chat['kind'], chat['label'], private=False)
        real_snapshot = s.store.snapshot
        def tighten_before_snapshot(scope_id):
            s.store.put_scope(chat['id'], chat['kind'], chat['label'], private=True)
            return real_snapshot(scope_id)
        with patch.object(s.store, 'snapshot', side_effect=tighten_before_snapshot):
            with self.assertRaises(RecordError) as refused:
                s.capture('chat-a')
        self.assertEqual(refused.exception.code, 'scope_changed')
        self.assertTrue(s.store.get_scope(chat['id'])['private'])


    def test_human_privacy_approval_card_sharing_correction_and_delete_are_reopened(self):
        s = self.service()
        s.setup(confirm=True)
        a = s.capture('chat-a')
        b = s.capture('chat-b')
        workspace = a['context']['workspace_scope_id']
        self.assertTrue(callable(getattr(s, 'set_privacy', None)), 'Human scope lifecycle is missing')
        s.set_privacy(a['scope_id'], False)
        pending = s.create_record(dict(scope_id=workspace, title='Banner', text='Use indigo banners.',
            domain='work', kind='explicit_fact', basis='explicit_statement',
            sources=[{'ref':'fictional:brief-1'}]))
        self.assertEqual(s.capture('chat-a')['records'], [])
        approved = s.approve(pending['id'], pending['revision'])
        self.assertEqual([r['id'] for r in s.capture('chat-a')['records']], [approved['id']])
        self.assertEqual(s.capture('chat-b')['records'], [])
        before = s.capture('chat-a')
        corrected = s.correct(approved['id'], approved['revision'], {'text':'Use copper banners.'})
        with self.assertRaises(RecordError):
            s.assert_current(before)
        self.assertEqual(s.capture('chat-a')['records'][0]['text'], 'Use copper banners.')
        card = s.create_record(dict(scope_id='personal', title='Communication', text='Use short paragraphs.',
            domain='user', kind='preference', basis='explicit_statement', topic='communication',
            sources=[{'ref':'fictional:preference-1'}], state='approved'))
        s.grant('personal', b['scope_id'], [card['id']])
        self.assertEqual([r['id'] for r in self.service().capture('chat-b')['records']], [card['id']])
        grants = s.overview('chat-b')['grants']
        self.assertEqual(grants, [dict(source_scope='personal', target_scope=b['scope_id'],
                                      record_id=card['id'], record_revision=card['revision'])])
        s.revoke('personal', b['scope_id'], [card['id']])
        self.assertEqual(self.service().capture('chat-b')['records'], [])
        self.assertEqual(s.overview('chat-b')['grants'], [])
        preview = s.delete_preview(corrected['id'])
        receipt = s.delete(corrected['id'], preview['preview_token'])
        self.assertIn(corrected['id'], receipt['deleted_ids'])
        self.assertTrue(receipt['index_cleanup']['complete'])
        self.assertEqual(self.service().capture('chat-a')['records'], [])
        self.assertEqual(self.service().overview('chat-a', workspace)['records'], [])


    def test_busy_operation_refuses_mutation_without_partial_commit(self):
        s = self.service()
        s.setup(confirm=True)
        captured = s.capture('chat-a')
        self.assertTrue(callable(getattr(s, 'operation', None)), 'Cross-component operation lock is missing')
        payload = dict(scope_id=captured['scope_id'], title='Banner', text='Indigo.', domain='work',
                       kind='explicit_fact', basis='explicit_statement', sources=[{'ref':'fictional:brief'}])
        with s.operation():
            with self.assertRaises(RecordError) as busy:
                self.service().create_record(payload)
            self.assertEqual(busy.exception.code, 'operation_busy')
            self.assertEqual(s.store.list_records(captured['scope_id']), [])
        self.assertEqual(self.service().create_record(payload)['state'], 'pending')


    def test_learning_consent_is_explicit_boolean_and_persists_independently(self):
        s = self.service()
        s.setup(confirm=True)
        self.assertFalse(s.overview('chat-a')['status']['learning_enabled'])
        self.assertTrue(callable(getattr(s, 'set_learning', None)), 'Learning consent is not implemented')
        for value in (1, 'true', None):
            with self.assertRaises(RecordError):
                s.set_learning(value)
        enabled = s.set_learning(True)
        self.assertTrue(enabled['learning_enabled'])
        self.assertTrue(self.service().overview('chat-a')['status']['learning_enabled'])
        disabled = s.set_learning(False)
        self.assertNotEqual(enabled['revision'], disabled['revision'])
        self.assertFalse(self.service().overview('chat-a')['status']['learning_enabled'])
        self.assertEqual(s.capture('chat-a')['records'], [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
