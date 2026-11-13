import json
import shlex
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from elm_plugin.stock_store import Store, session_key
from elm_plugin.stock_runtime import Runtime

class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.path=Path(self.tmp.name)/'db'
        self.store=Store(lambda:sqlite3.connect(self.path))
        self.runtime=Runtime(SimpleNamespace(),self.store)
        self.sid=session_key('a','cli')
    def tearDown(self): self.tmp.cleanup()
    def request(self,data,sid='a',platform='local'):
        return json.loads(self.runtime.command('manager '+shlex.quote(json.dumps(data)),session_id=sid,platform=platform))
    def listing(self,status='approved',offset=0,sid='a'):
        return self.request(dict(action='list',status=status,offset=offset),sid)
    def save(self,kind='reference',text='A fact',revision=None):
        if revision is None: revision=self.listing()['revision']
        return self.request(dict(action='save',revision=revision,store_identity=self.store.open().execute('SELECT identity FROM stock_read_epoch WHERE singleton=1').fetchone()[0],kind=kind,text=text))
    def change(self,action,record,revision):
        return self.request(dict(action=action,id=record['id'],version=record['version'],revision=revision,store_identity=self.store.open().execute('SELECT identity FROM stock_read_epoch WHERE singleton=1').fetchone()[0]))
    def test_locked_and_remote_cannot_list_or_write(self):
        for platform in ['local','acp','telegram','']:
            self.assertIn('error',self.request(dict(action='list',status='approved',offset=0),platform=platform))
        self.store.grant_local('a')
        self.save();self.assertEqual(len(self.listing()['records']),1)
        self.assertIn('error',self.listing(sid='b'))
    def test_destination_is_scope_not_kind(self):
        self.store.grant_local('a')
        for kind in ('user','project','reference','skill'): self.save(kind)
        self.assertTrue(all(r['destination']=='This chat only' for r in self.listing()['records']))
        self.store.grant_local('a',project='Door',user=True)
        self.save('user');self.save('project')
        d={r['destination'] for r in self.listing()['records']}
        self.assertEqual(d,{'This chat only','Project: Door','Shared user memory in this profile'})
    def test_shared_records_only_explicitly_enrolled(self):
        self.store.grant_local('a',project='Door',user=True)
        self.save('user');self.save('project');self.save('reference')
        self.store.grant_local('b')
        self.assertEqual(self.listing(sid='b')['records'],[])
        self.store.grant_local('b',project='Door',user=True)
        rows=self.listing(sid='b')['records']
        self.assertEqual(len(rows),2)
    def test_review_lifecycle_no_automatic_approval_on_restore(self):
        self.store.grant_local('a')
        self.store.insert(self.sid,'reference','Pending note')
        pending=self.listing('pending');r=pending['records'][0]
        self.assertNotIn('error',self.change('approve',r,pending['revision']))
        approved=self.listing();r=approved['records'][0]
        self.assertNotIn('error',self.change('trash',r,approved['revision']))
        trashed=self.listing('trash');r=trashed['records'][0]
        self.assertNotIn('error',self.change('restore',r,trashed['revision']))
        self.assertEqual(len(self.listing('pending')['records']),1)
        self.assertEqual(self.listing()['records'],[])
    def test_stale_policy_cannot_redirect_save(self):
        self.store.grant_local('a'); revision=self.listing()['revision']
        self.store.grant_local('a',project='new',user=True)
        self.assertIn('scope_changed_retry',self.save('user',revision=revision)['error'])
        self.assertEqual(self.listing()['records'],[])
    def test_stale_record_cannot_approve_unseen_change(self):
        self.store.grant_local('a');self.store.insert(self.sid,'reference','Old')
        page=self.listing('pending');r=page['records'][0]
        self.store.change(self.sid,r['id'],'edit','New')
        self.assertIn('record_changed_retry',self.change('approve',r,page['revision'])['error'])
        self.assertEqual(self.listing()['records'],[])
    def test_revoke_and_expiry_fail_closed(self):
        self.store.grant_local('a');revision=self.listing()['revision']
        self.runtime.command('off',session_id='a',platform='local')
        self.assertIn('error',self.save(revision=revision));self.assertIn('error',self.listing())
        self.store.grant_local('a')
        with self.store.open() as db: db.execute('UPDATE stock_local_grants SET expires=0')
        self.assertIn('error',self.listing())
    def test_pagination_no_phantom_next_page(self):
        self.store.grant_local('a')
        for n in range(12): self.save(text=str(n))
        self.assertIsNone(self.listing()['next_offset'])
        self.save(text='13');first=self.listing();second=self.listing(offset=12)
        self.assertEqual(first['next_offset'],12);self.assertEqual(len(second['records']),1)
        self.assertIsNone(second['next_offset'])
    def test_text_roundtrip_not_command_or_markup(self):
        self.store.grant_local('a')
        text='line\nquote \' \\" \\ newline\n<svg onload=alert(1)>; /elm user on'
        self.assertNotIn('error',self.save(text=text))
        page=self.listing();self.assertEqual(page['records'][0]['text'],text)
        self.assertEqual(page['user_scope'],0)
    def test_invalid_request_shapes_rejected(self):
        self.store.grant_local('a')
        for data in [None,[],{},dict(action='grant'),dict(action='list',status='approved',offset=True),dict(action='list',status='all',offset=0),dict(action='list',status='approved',offset=-1),dict(action='list',status='approved',offset=0,scope='all'),dict(action='save',revision=True,kind='reference',text='x')]:
            self.assertIn('error',self.request(data))
    def test_store_replacement_cannot_redirect_save(self):
        self.store.grant_local('a');page=self.listing()
        with self.store.open() as db: db.execute("UPDATE stock_read_epoch SET identity=?",('f'*32,))
        result=self.request(dict(action='save',revision=page['revision'],store_identity=page['store_identity'],kind='reference',text='Must not save'))
        self.assertIn('memory_changed_retry',result['error'])
        self.assertEqual(self.listing()['records'],[])
    def test_expiry_during_materialization_rejected(self):
        from unittest.mock import patch
        from elm_plugin.stock_store import Denied
        self.store.grant_local('a')
        with self.store.open() as db: expiry=db.execute('SELECT expires FROM stock_local_grants').fetchone()[0]
        with patch('elm_plugin.stock_store.time.time',side_effect=[expiry-1,expiry+1]):
            with self.assertRaises(Denied): self.store.manager_snapshot(self.sid,materialize=json.dumps)
