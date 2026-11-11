"""Real host/store/ELM path. Fictional labels test policy, not AI quality."""
import unittest
import test_workspace_service as fixtures
from elm_plugin.workspace_records import RecordError
from elm_plugin.workspace_index import IndexError as WorkspaceIndexError


class WorkspaceRecallTests(unittest.TestCase):
    setUp = fixtures.WorkspaceServiceTests.setUp
    service = fixtures.WorkspaceServiceTests.service

    def record(self, service, scope, text, **fields):
        return service.create_record(dict(scope_id=scope, title='Amber canary', text=text,
            domain='work', kind='explicit_fact', basis='explicit_statement',
            sources=[{'ref':'fictional:amber-brief'}], state='approved', **fields))

    def test_real_query_and_exact_read_use_host_scope_not_inspector_selection(self):
        s = self.service()
        s.setup(confirm=True)
        a, b = s.capture('chat-a'), s.capture('chat-b')
        workspace = a['context']['workspace_scope_id']
        s.set_privacy(a['scope_id'], False)
        allowed = self.record(s, workspace, 'Amber canary requires a signed rollback.')
        self.record(s, b['scope_id'], 'Amber canary PRIVATE_OTHER_CHAT uses a different gate.')
        self.assertTrue(callable(getattr(s, 'query', None)), 'Scoped service-to-ELM query is missing')
        packet = s.query('chat-a', 'amber canary')
        self.assertEqual(packet['scope_id'], workspace)
        self.assertEqual([r['record_id'] for r in packet['results']], [allowed['id']])
        hit = packet['results'][0]
        self.assertNotIn('PRIVATE_OTHER_CHAT', str(packet))
        self.assertEqual(hit['text'], allowed['text'])
        self.assertEqual(hit['sources'], allowed['sources'])
        self.assertFalse(hit['executable'])
        exact = s.read('chat-a', hit['section'])
        self.assertEqual(exact['record_revision'], allowed['revision'])
        self.assertEqual(exact['text'], allowed['text'])
        self.assertEqual(exact['scope_id'], workspace)
        # Human can inspect a different scope, but model authority is unchanged.
        s.overview('chat-b', workspace)
        with self.assertRaises((RecordError, WorkspaceIndexError)):
            s.read('chat-b', hit['section'])
        private = s.query('chat-b', 'amber canary')
        self.assertEqual(private['scope_id'], b['scope_id'])
        self.assertNotIn('signed rollback', str(private))
    def test_revoke_correction_and_delete_purge_real_content_copies(self):
        s = self.service()
        s.setup(confirm=True)
        scope = s.capture('chat-a')['scope_id']
        card = s.create_record(dict(scope_id='personal', title='Communication', text='Use amber short paragraphs.',
            domain='user', kind='preference', basis='explicit_statement', topic='communication',
            sources=[{'ref':'fictional:card'}], state='approved'))
        s.grant('personal', scope, [card['id']])
        old = s.query('chat-a', 'amber')['results'][0]['section']
        cleanup = s.revoke('personal', scope, [card['id']])['index_cleanup']
        self.assertTrue(cleanup['complete'], cleanup)
        self.assertEqual(cleanup['held'], [])
        self.assertFalse(list(s._index().root.glob('gen_*')))
        with self.assertRaises((RecordError, WorkspaceIndexError)):
            s.read('chat-a', old)
        record = self.record(s, scope, 'Amber canary ORIGINAL_MARKER needs the red gate.')
        first = s.query('chat-a', 'amber canary')['results'][0]['section']
        corrected = s.correct(record['id'], record['revision'], {'text':'Amber canary NEW_MARKER needs the blue gate.'})
        self.assertTrue(corrected['index_cleanup']['complete'])
        self.assertFalse(list(s._index().root.glob('gen_*')))
        with self.assertRaises((RecordError, WorkspaceIndexError)):
            s.read('chat-a', first)
        fresh = s.query('chat-a', 'amber canary')['results'][0]
        self.assertEqual(fresh['text'], corrected['text'])
        preview = s.delete_preview(record['id'])
        erased = s.delete(record['id'], preview['preview_token'])
        self.assertTrue(erased['index_cleanup']['complete'])
        self.assertFalse(list(s._index().root.glob('gen_*')))
        for path in s.cache_root.rglob('*'):
            if path.is_file():
                self.assertNotIn(b'NEW_MARKER', path.read_bytes())
                self.assertNotIn(b'ORIGINAL_MARKER', path.read_bytes())
        with self.assertRaises((RecordError, WorkspaceIndexError)):
            self.service().read('chat-a', fresh['section'])
        self.assertEqual(self.service().query('chat-a', 'amber canary')['results'], [])
    def test_host_workspace_move_during_real_query_withholds_and_purges_stale_projection(self):
        from unittest.mock import patch
        from hermes_cli import projects_db
        s = self.service()
        s.setup(confirm=True)
        initial = s.capture('chat-a')
        s.set_privacy(initial['scope_id'], False)
        self.record(s, initial['context']['workspace_scope_id'], 'Amber OLD_WORKSPACE_EVIDENCE.')
        other = projects_db.create_project(self.projects, name='Other workspace')
        index = s._index()
        real_query = index.query
        def move_after_query(*args, **kwargs):
            value = real_query(*args, **kwargs)
            projects_db.set_session_project(self.projects, 'chat-a', other)
            return value
        with patch.object(s, '_index', return_value=index), patch.object(index, 'query', side_effect=move_after_query):
            with self.assertRaises(RecordError) as refusal:
                s.query('chat-a', 'amber')
        self.assertEqual(refusal.exception.code, 'scope_changed')
        self.assertFalse(list(index.root.glob('gen_*')))
        self.assertEqual(s.query('chat-a', 'amber')['results'], [])

    def test_windows_held_copy_warns_after_commit_and_never_restores_deleted_recall(self):
        import os
        if os.name != 'nt':
            self.skipTest('Real Windows non-delete-sharing handle check')
        import ctypes
        from ctypes import wintypes
        s = self.service()
        s.setup(confirm=True)
        scope = s.capture('chat-a')['scope_id']
        record = self.record(s, scope, 'Amber HELD_DELETION_MARKER.')
        packet = s.query('chat-a', 'amber')
        section = packet['results'][0]['section']
        manifest = s._index().root/packet['generation']/'manifest.json'
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,
                                      wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        handle = kernel.CreateFileW(str(manifest), 0x80000000, 1 | 2, None, 3, 0x80, None)
        self.assertNotEqual(handle, wintypes.HANDLE(-1).value, ctypes.get_last_error())
        try:
            preview = s.delete_preview(record['id'])
            result = s.delete(record['id'], preview['preview_token'])
            self.assertIn(record['id'], result['deleted_ids'])
            self.assertFalse(result['index_cleanup']['complete'])
            self.assertTrue(result['index_cleanup']['held_paths'])
            self.assertIn('committed', result['warning'])
            self.assertTrue(manifest.is_file())
            with self.assertRaises(RecordError):
                s.store.get(record['id'])
            with self.assertRaises((RecordError, WorkspaceIndexError)):
                s.read('chat-a', section)
            self.assertEqual(s.query('chat-a', 'amber')['results'], [])
        finally:
            self.assertTrue(kernel.CloseHandle(handle))
        cleanup = s._cleanup_index()
        self.assertTrue(cleanup['complete'], cleanup)
        self.assertFalse(list(s._index().root.glob('gen_*')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
