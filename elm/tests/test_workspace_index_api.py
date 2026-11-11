"""Human index rebuild and fresh overview through real HTTP and ELM."""
import json
import unittest
import sys
from unittest.mock import patch
import test_workspace_api as api_fixtures


class WorkspaceIndexApiTests(unittest.TestCase):
    setUp = api_fixtures.WorkspaceApiTests.setUp
    client = api_fixtures.WorkspaceApiTests.client

    def prepared(self):
        client = self.client()
        p = '/api/plugins/elm'
        self.assertEqual(client.post(p+'/setup', json={'confirm':True}).status_code, 200)
        current = client.get(p+'/overview', params={'session_id':'chat-a'}).json()
        scope = current['selected_scope_id']
        made = client.post(p+'/record', json=dict(scope_id=scope, title='Fictional release',
            text='Amber release needs a signed rollback.', domain='work', kind='explicit_fact',
            basis='explicit_statement', sources=[{'ref':'fictional:index-api'}], state='approved'))
        self.assertEqual(made.status_code, 200, made.text)
        service_class = next(r.endpoint.__globals__['WorkspaceService'] for r in client.app.routes
                             if getattr(r,'path',None) == p+'/overview')
        return client, p, scope, made.json()['result'], service_class(self.home)

    def test_confirmed_rebuild_is_read_back_for_the_exact_selected_scope(self):
        client, p, scope, record, service = self.prepared()
        authored = self.home/'elm-workspaces'/'records'
        before = {str(f.relative_to(authored)):f.read_bytes() for f in authored.rglob('*.json')}
        reply = client.post(p+'/index/rebuild', json={'scope_id':scope,'confirm':True})
        self.assertEqual(reply.status_code, 200, reply.text)
        result = reply.json()['result']
        self.assertEqual(result['scope_id'], scope)
        self.assertEqual(result['index_state'], 'ready')
        fresh = client.get(p+'/overview', params={'session_id':'chat-a','scope_id':scope}).json()
        self.assertEqual(fresh['status']['generation'], result['generation'])
        self.assertEqual(fresh['status']['scope_id'], scope)
        self.assertEqual(fresh['status']['index_state'], 'ready')
        self.assertTrue(fresh['status']['snapshot_current'])
        self.assertEqual({str(f.relative_to(authored)):f.read_bytes() for f in authored.rglob('*.json')}, before)
        self.assertEqual(fresh['records'][0]['id'], record['id'])
        self.assertEqual(service.query('chat-a','amber')['generation'], result['generation'])
        for payload in ({'confirm':True}, {'scope_id':scope,'confirm':False},
                        {'scope_id':scope,'confirm':True,'root':'C:/unrelated'}):
            refused = client.post(p+'/index/rebuild', json=payload)
            self.assertEqual(refused.status_code, 400, refused.text)
        self.assertEqual(client.get(p+'/overview', params={'session_id':'chat-a'}).json()['status']['generation'], result['generation'])

    def test_overview_never_builds_or_labels_an_old_snapshot_current(self):
        client, p, scope, record, service = self.prepared()
        self.assertFalse(service.cache_root.exists())
        for _ in range(2):
            fresh = client.get(p+'/overview', params={'session_id':'chat-a'}).json()
            self.assertEqual(fresh['status']['index_state'], 'not_built')
        self.assertFalse(service.cache_root.exists())
        generation = client.post(p+'/index/rebuild', json={'scope_id':scope,'confirm':True}).json()['result']['generation']
        # Another valid repository writer can change authoritative records without
        # calling the service's opportunistic cache purge. Inspection must compare.
        service.store.correct(record['id'], record['revision'], {'text':'Amber now needs two signed rollback reviewers.'})
        before = {str(f.relative_to(service.cache_root)):f.read_bytes()
                  for f in service.cache_root.rglob('*') if f.is_file()}
        fresh = client.get(p+'/overview', params={'session_id':'chat-a'}).json()
        self.assertEqual(fresh['status']['index_state'], 'snapshot_changed')
        self.assertFalse(fresh['status']['snapshot_current'])
        self.assertEqual(fresh['status']['generation'], generation)
        self.assertEqual({str(f.relative_to(service.cache_root)):f.read_bytes()
                          for f in service.cache_root.rglob('*') if f.is_file()}, before)
        rebuilt = client.post(p+'/index/rebuild', json={'scope_id':scope,'confirm':True}).json()['result']
        self.assertNotEqual(rebuilt['generation'], generation)
        self.assertTrue(client.get(p+'/overview', params={'session_id':'chat-a'}).json()['status']['snapshot_current'])

    def test_failed_staging_keeps_previous_generation_and_authored_records(self):
        client, p, scope, record, service = self.prepared()
        original = client.post(p+'/index/rebuild', json={'scope_id':scope,'confirm':True}).json()['result']
        before = service.store.get(record['id'])
        index_module = sys.modules[type(service._index()).__module__]
        with patch.object(index_module, 'run_engine', side_effect=RuntimeError('fictional engine failure')):
            failed = client.post(p+'/index/rebuild', json={'scope_id':scope,'confirm':True})
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(failed.json()['code'], 'index_build_failed')
        self.assertEqual(service.store.get(record['id']), before)
        fresh = client.get(p+'/overview', params={'session_id':'chat-a'}).json()
        self.assertEqual(fresh['status']['generation'], original['generation'])
        self.assertEqual(fresh['status']['index_state'], 'ready')
        self.assertTrue(list(service._index().root.glob('gen_*/failure.json')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
