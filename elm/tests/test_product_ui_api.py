"""Real session resolver, ASGI router and isolated product-result storage."""
import importlib
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from hermes_state import SessionDB
from hermes_constants import set_hermes_home_override, reset_hermes_home_override


class ProductResultsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='important-ui-')
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        with closing(SessionDB(self.home/'state.db')) as db:
            for session in ('chat-a', 'chat-b'):
                db.create_session(session, source='desktop')
        self.token = set_hermes_home_override(self.home)
        self.addCleanup(reset_hermes_home_override, self.token)

    def modules(self):
        try:
            return (importlib.import_module('elm_plugin.result_inbox'),
                    importlib.import_module('elm_plugin.product_ui_api'))
        except ModuleNotFoundError as exc:
            if exc.name in ('elm_plugin.result_inbox', 'elm_plugin.product_ui_api'):
                self.fail('Important result publisher and human API are not implemented')
            raise

    def client(self):
        _, api = self.modules()
        app = FastAPI()
        app.include_router(api.router, prefix='/api/plugins/elm/ui')
        client = TestClient(app)
        self.addCleanup(client.close)
        return client

    def test_missing_postcommit_publish_row_is_http_conflict_not_invalid_payload(self):
        from unittest.mock import patch
        inbox,_=self.modules();c=self.client()
        with patch.object(inbox.ResultInbox,'get',return_value={'exists':False,'result':None}):
            response=c.post('/api/plugins/elm/ui/results',json={'session_id':'chat-a','title':'T','body':'B','kind':'partial'})
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(response.json()['code'],'publication_unconfirmed')
        self.assertEqual(len(inbox.ResultInbox(self.home).list('chat-a')['results']),1)

    def test_publish_is_chat_scoped_and_not_a_memory_fact_or_completion(self):
        inbox, _ = self.modules()
        c = self.client()
        baseline = c.get('/api/plugins/elm/ui/results', params={'session_id':'chat-a'})
        self.assertEqual(baseline.status_code, 200)
        self.assertEqual(baseline.json()['results'], [])
        self.assertFalse((self.home/'elm-product-ui').exists(), 'Read must not initialize state')
        receipt = inbox.publish_important_result(current_session_id='chat-a',
            title='Build blocked', body='The signed artifact is still missing.', kind='blocked')
        self.assertTrue(receipt['ok'])
        result = receipt['result']
        self.assertEqual(result['status'], 'unread')
        self.assertEqual(result['kind'], 'blocked')
        a = c.get('/api/plugins/elm/ui/results', params={'session_id':'chat-a'}).json()
        b = c.get('/api/plugins/elm/ui/results', params={'session_id':'chat-b'}).json()
        self.assertEqual(a['results'], [result])
        self.assertEqual(b['results'], [])
        self.assertEqual(c.get('/api/plugins/elm/ui/results/'+result['id'], params={'session_id':'chat-b'}).json()['exists'], False)
        self.assertFalse((self.home/'elm-workspaces').exists())
        self.assertTrue((self.home/'elm-product-ui'/'owner.json').is_file())
        self.assertIn('::elm-result', receipt['directive'])


    def test_view_read_dismiss_delete_require_exact_revision_and_readback(self):
        c = self.client()
        base = '/api/plugins/elm/ui'
        result = c.post(base+'/results', json={'session_id':'chat-a','title':'Partial output',
            'body':'Not a whole-task completion.', 'kind':'partial'}).json()['result']
        ident = result['id']
        def change(action, revision, session='chat-a'):
            return c.post(base+'/results/'+ident+'/'+action, json={'session_id':session,'expected_revision':revision})
        viewed = change('view', 1)
        self.assertEqual(viewed.status_code, 200)
        result = viewed.json()['result']
        self.assertEqual(result['status'], 'viewed')
        self.assertEqual(c.get(base+'/results/'+ident, params={'session_id':'chat-a'}).json()['result'], result)
        self.assertEqual(change('read', 1).status_code, 409)
        self.assertEqual(change('read', 2, 'chat-b').status_code, 404)
        result = change('read', 2).json()['result']
        self.assertEqual(result['status'], 'read')
        result = change('view', result['revision']).json()['result']
        self.assertEqual(result['status'], 'read', 'Visibility cannot downgrade an explicit acknowledgment')
        result = change('dismiss', result['revision']).json()['result']
        self.assertTrue(result['dismissed'])
        self.assertEqual(c.get(base+'/results', params={'session_id':'chat-a'}).json()['results'], [])
        self.assertEqual(len(c.get(base+'/results', params={'session_id':'chat-a','include_dismissed':True}).json()['results']), 1)
        deleted = c.request('DELETE', base+'/results/'+ident,
            json={'session_id':'chat-a','expected_revision':result['revision']})
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()['result']['deleted_id'], ident)
        self.assertFalse(c.get(base+'/results/'+ident, params={'session_id':'chat-a'}).json()['exists'])

    def test_attention_is_chat_scoped_readback_and_rejects_authority_fields(self):
        c = self.client()
        base = '/api/plugins/elm/ui'
        default = c.get(base+'/attention', params={'session_id':'chat-a'})
        self.assertEqual(default.status_code, 200)
        self.assertEqual(default.json()['attention']['mode'], 'quiet')
        self.assertFalse(default.json()['attention']['updates_visible'])
        saved = c.post(base+'/attention', json={'session_id':'chat-a','expected_revision':1,
            'mode':'off','updates_visible':True})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(c.get(base+'/attention', params={'session_id':'chat-a'}).json()['attention'], saved.json()['result'])
        self.assertEqual(c.get(base+'/attention', params={'session_id':'chat-b'}).json()['attention']['mode'], 'quiet')
        self.assertEqual(c.post(base+'/attention', json={'session_id':'chat-a','expected_revision':1,
            'mode':'quiet','updates_visible':False}).status_code, 409)
        self.assertEqual(c.post(base+'/results', json={'session_id':'chat-a','title':'Bad',
            'body':'No roots', 'kind':'final','home':'C:/fictional'}).status_code, 400)
        self.assertEqual(c.get(base+'/results', params={'session_id':'not-owned'}).status_code, 404)
        self.assertEqual(c.get(base+'/results/../x', params={'session_id':'chat-a'}).status_code, 404)
        self.assertEqual(c.get(base+'/results', params={'session_id':'chat-a','limit':101}).status_code, 400)


    def test_database_schema_and_unowned_root_are_not_adopted(self):
        import sqlite3
        inbox,_=self.modules()
        store=inbox.ResultInbox(self.home)
        store.publish('chat-a',title='Old',body='Keep',kind='progress')
        with closing(sqlite3.connect(store.path)) as db:
            db.execute('PRAGMA user_version=2')
        c=self.client();base='/api/plugins/elm/ui'
        self.assertEqual(c.get(base+'/results',params={'session_id':'chat-a'}).status_code,503)
        write=c.post(base+'/results',json={'session_id':'chat-a','title':'New','body':'Refuse','kind':'final'})
        self.assertEqual(write.status_code,503,write.text)
        with closing(sqlite3.connect(store.path)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT count(*) FROM results').fetchone()[0],1)
        (store.root/'owner.json').write_text('{}',encoding='utf-8')
        self.assertEqual(c.get(base+'/results',params={'session_id':'chat-a'}).status_code,409)
        self.assertEqual(c.post(base+'/results',json={'session_id':'chat-a','title':'No adoption','body':'No','kind':'partial'}).status_code,409)

    def test_real_profile_lineage_pagination_and_concurrent_revision_guards(self):
        import concurrent.futures
        import hashlib
        inbox,_=self.modules();store=inbox.ResultInbox(self.home)
        with closing(SessionDB(self.home/'state.db')) as db:
            db.end_session('chat-a','compression')
            db.create_session('continued',source='desktop',parent_session_id='chat-a')
            db.create_session('branch',source='desktop',parent_session_id='chat-a',model_config={'_branched_from':'chat-a'})
        saved=[store.publish('chat-a',title=str(i),body='Synthetic',kind='progress') for i in range(4)]
        first=store.list('continued',limit=2);self.assertEqual(len(first['results']),2)
        second=store.list('continued',limit=2,cursor=first['next_cursor'])
        self.assertEqual({x['id'] for x in first['results']+second['results']},{x['id'] for x in saved})
        self.assertEqual(store.list('branch')['results'],[])
        other=self.home/'synthetic-other';other.mkdir()
        with closing(SessionDB(other/'state.db')) as db:db.create_session('chat-a',source='desktop')
        self.assertEqual(inbox.ResultInbox(other).list('chat-a')['results'],[])
        self.assertFalse((other/'elm-product-ui').exists())
        before=hashlib.sha256((self.home/'state.db').read_bytes()).hexdigest()
        target=saved[0]
        def action():
            try:return store.mutate('chat-a',target['id'],1,'read')['revision']
            except inbox.InboxError as exc:return exc.code
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(lambda _:action(),range(2)))
        self.assertCountEqual(outcomes,[2,'revision_conflict'])
        self.assertEqual(hashlib.sha256((self.home/'state.db').read_bytes()).hexdigest(),before)
        self.assertFalse((self.home/'elm-workspaces').exists())

    def test_bad_ids_boolean_revision_invalid_kind_and_body_limit_fail_closed(self):
        c=self.client();base='/api/plugins/elm/ui'
        for ident in ('A'*32,'x'*33,'x','0'*31):
            self.assertEqual(c.get(base+'/results/'+ident,params={'session_id':'chat-a'}).status_code,400)
        for kind in ('complete','fact',[],False):
            self.assertEqual(c.post(base+'/results',json={'session_id':'chat-a','title':'T','body':'B','kind':kind}).status_code,400)
        self.assertEqual(c.post(base+'/results',content=b'x'*500001).status_code,400)
        self.assertEqual(c.post(base+'/attention',json={'session_id':'chat-a','expected_revision':True,'mode':'quiet','updates_visible':False}).status_code,400)
        self.assertFalse((self.home/'elm-product-ui').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
