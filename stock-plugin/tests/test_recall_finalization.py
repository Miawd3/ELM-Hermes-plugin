import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from elm_plugin.stock_store import Store, session_key, Denied
from elm_plugin.stock_runtime import Runtime

class RecallFinalizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'memory.db'
        self.store=Store(lambda:sqlite3.connect(self.path))
        self.sid=session_key('chat','cli')
        self.store.settings(self.sid,{'enabled':True})
        self.record=self.store.insert(self.sid,'reference','door red',approved=True)['id']
        self.rt=Runtime(SimpleNamespace(session_surface=lambda:'cli'),self.store)
    def tearDown(self): self.tmp.cleanup()
    def mutate_after_read(self,fn):
        original=self.store.records
        def records(*a,**kw):
            rows=original(*a,**kw); fn(); return rows
        self.store.records=records
    def test_automatic_revocation_after_read_is_empty(self):
        self.mutate_after_read(lambda:self.store.settings(self.sid,{'enabled':False}))
        self.assertIsNone(self.rt.before_turn(session_id='chat',user_message='door'))
    def test_explicit_trash_after_read_rejected(self):
        self.mutate_after_read(lambda:self.store.change(self.sid,self.record,'trash'))
        with self.assertRaises(Denied):self.rt.search(self.sid,'door')
    def test_automatic_edit_after_read_rejected(self):
        self.mutate_after_read(lambda:self.store.change(self.sid,self.record,'edit','door blue'))
        self.assertIsNone(self.rt.before_turn(session_id='chat',user_message='door'))
    def test_content_aba_rejected(self):
        def aba():
            self.store.change(self.sid,self.record,'edit','door blue')
            self.store.change(self.sid,self.record,'edit','door red')
        self.mutate_after_read(aba)
        with self.assertRaisesRegex(Denied,'memory_changed'):self.rt.search(self.sid,'door')
    def test_policy_aba_rejected(self):
        def aba():
            self.store.settings(self.sid,{'enabled':False})
            self.store.settings(self.sid,{'enabled':True})
        self.mutate_after_read(aba)
        with self.assertRaises(Denied):self.rt.search(self.sid,'door')
    def test_physical_delete_triggers_generation(self):
        def delete():
            with sqlite3.connect(self.path) as db:db.execute('DELETE FROM stock_records WHERE id=?',(self.record,))
        self.mutate_after_read(delete)
        with self.assertRaises(Denied):self.rt.search(self.sid,'door')
    def test_profile_switch_rejected_even_same_ids_and_state(self):
        other=Path(self.tmp.name)/'other.db'
        import shutil
        shutil.copyfile(self.path,other)
        with sqlite3.connect(other) as db:db.execute("UPDATE stock_read_epoch SET identity='different-profile'")
        self.mutate_after_read(lambda:setattr(self.store,'connection',lambda:sqlite3.connect(other)))
        with self.assertRaises(Denied):self.rt.search(self.sid,'door')
    def test_forged_candidate_rejected(self):
        original=self.store.records
        def tamper(*a,**kw):
            rows=original(*a,**kw);rows[0]['text']='invented';return rows
        self.store.records=tamper
        with self.assertRaises(Denied):self.rt.search(self.sid,'door')
    def test_clean_explicit_and_automatic_recall(self):
        self.assertEqual(self.rt.search(self.sid,'door')['results'][0]['text'],'door red')
        self.assertIn('door red',self.rt.before_turn(session_id='chat',user_message='door')['context'])
    def test_epoch_persists_reopen_and_updates(self):
        first=self.store.read_stamp(self.sid)
        self.store.change(self.sid,self.record,'edit','door new')
        fresh=Store(lambda:sqlite3.connect(self.path)).read_stamp(self.sid)
        self.assertEqual(first['store_identity'],fresh['store_identity'])
        self.assertGreater(fresh['content_generation'],first['content_generation'])
    def test_expiry_during_materialization_rejected(self):
        self.store.grant_local('chat',hours=1)
        stamp=self.store.read_stamp(self.sid);rows=self.store.records(self.sid,'door')
        def render(rows):
            self.clock.return_value += 7200
            return rows
        import time
        with patch('elm_plugin.stock_store.time.time',return_value=time.time()) as self.clock:
            with self.assertRaises(Denied):self.store.finalize_records(self.sid,stamp,rows,render)
    def test_sqlite_write_lock_held_during_materialization(self):
        stamp=self.store.read_stamp(self.sid);rows=self.store.records(self.sid,'door')
        def render(rows):
            with sqlite3.connect(self.path,timeout=0) as db:
                with self.assertRaises(sqlite3.OperationalError):db.execute("UPDATE stock_records SET status='trash'")
            return rows
        self.assertEqual(self.store.finalize_records(self.sid,stamp,rows,render),rows)

if __name__=='__main__': unittest.main()
