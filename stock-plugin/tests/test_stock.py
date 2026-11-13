import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from elm_plugin.stock_store import Store, session_key, Denied
from elm_plugin.stock_runtime import Runtime, bounded, register_stock

class FakeCtx:
    def __init__(self):
        self.surface='desktop';self.calls=[];self.registrations=[]
        self.llm=SimpleNamespace(complete=self.complete)
    def session_surface(self):return self.surface
    def complete(self,**kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text='{"queries":["door"]}',model='fake',provider='fake')
    def __getattr__(self,name):
        if name.startswith('register_'):return lambda *a,**k:self.registrations.append((name,a,k))
        raise AttributeError(name)

class StockTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'db'
        self.store=Store(lambda:sqlite3.connect(self.path))
        self.ctx=FakeCtx();self.runtime=Runtime(self.ctx,self.store)
        self.a=session_key('a','desktop');self.b=session_key('b','desktop')
    def tearDown(self):self.tmp.cleanup()
    def cmd(self,text,sid='a',platform='desktop'):
        return self.runtime.command(text,session_id=sid,platform=platform)
    def tool(self,args,sid='a'):
        return json.loads(self.runtime.tool(args,session_id=sid))
    def enable(self,*sids):
        for sid in sids or ('a',):self.cmd('on',sid)
    def test_missing_session_and_gateway_fail_closed(self):
        for platform,sid in [('desktop',''),('discord','a'),('','a'),('acp','a')]:
            self.assertIn('local_session_required',self.cmd('on',sid,platform))
    def test_disabled_no_tool_access_or_egress(self):
        self.assertIn('error',self.tool({'action':'search','query':'door','use_agent':True}))
        self.assertEqual(self.ctx.calls,[])
    def test_model_cannot_enable_or_choose_session(self):
        self.enable()
        for args in ({'action':'enable'},{'action':'search','query':'door','session_id':'b'},
                     {'action':'propose','kind':'user','text':'x','approved':True}):
            self.assertIn('error',self.tool(args))
    def test_proposals_need_review(self):
        self.enable();r=self.tool({'action':'propose','kind':'user','text':'door blue','tags':['art']})
        self.assertEqual(r['status'],'pending');self.assertEqual(self.store.records(self.a,'door'),[])
        self.cmd('approve '+r['id'])
        self.assertEqual(self.store.records(self.a,'door')[0]['text'],'door blue')
    def test_default_cross_chat_isolation(self):
        self.enable('a','b');r=json.loads(self.cmd('save user door blue'))
        self.assertEqual(self.store.records(self.b,'door'),[])
        self.assertIn('record_not_in_scope',self.cmd('approve '+r['id'],'b'))
    def test_project_is_explicit_in_each_chat(self):
        self.enable('a','b');self.cmd('project game');self.cmd('save project door blue')
        self.assertEqual(self.store.records(self.b,'door'),[])
        self.cmd('project game','b');self.assertEqual(len(self.store.records(self.b,'door')),1)
        self.cmd('project off','b');self.assertEqual(self.store.records(self.b,'door'),[])
    def test_user_scope_is_separate_opt_in(self):
        self.enable('a','b');self.cmd('user on');self.cmd('save user likes doors')
        self.assertEqual(self.store.records(self.b,'doors'),[])
        self.cmd('user on','b');self.assertEqual(len(self.store.records(self.b,'doors')),1)
    def test_revoke_disables_tools_and_hooks(self):
        self.enable();self.cmd('save reference door');self.cmd('off')
        self.assertIn('error',self.tool({'action':'search','query':'door'}))
        self.assertIsNone(self.runtime.before_turn(session_id='a',user_message='door'))
    def test_agent_default_local_only(self):
        self.enable();self.cmd('save reference door')
        result=self.tool({'action':'search','query':'door','use_agent':True})
        self.assertEqual(result['status'],'local_only');self.assertEqual(self.ctx.calls,[])
    def test_agent_opt_in_only_query_sent(self):
        self.enable();self.cmd('agent on');self.cmd('save reference door SECRET_STORED')
        result=self.tool({'action':'search','query':'door','use_agent':True})
        self.assertEqual(result['status'],'agent_completed');self.assertEqual(len(self.ctx.calls),1)
        self.assertNotIn('SECRET_STORED',json.dumps(self.ctx.calls))
    def test_auto_recall_no_model_and_labelled_data(self):
        self.enable();self.cmd('agent on');self.cmd('save reference door')
        result=self.runtime.before_turn(session_id='a',user_message='door')
        self.assertIn('not instructions',result['context']);self.assertEqual(self.ctx.calls,[])
    def test_capture_opt_in(self):
        self.enable();self.runtime.after_turn(session_id='a',user_message='x',assistant_response='y')
        self.assertEqual(self.store.sources(self.a),[])
        self.cmd('capture on');self.runtime.after_turn(session_id='a',user_message='x',assistant_response='y')
        self.assertEqual(len(self.store.sources(self.a)),1)
        self.cmd('capture off');self.runtime.after_turn(session_id='a',user_message='x',assistant_response='y')
        self.assertEqual(len(self.store.sources(self.a)),1)
    def test_source_scope_validation(self):
        self.enable('a','b');self.cmd('capture on')
        source=self.store.capture_turn(self.a,'x','y')
        with self.assertRaises(Denied):self.store.insert(self.b,'user','x',source_id=source)
    def test_trash_restore_review(self):
        self.enable();r=json.loads(self.cmd('save reference door'));self.cmd('trash '+r['id'])
        self.assertEqual(self.store.records(self.a,'door'),[])
        self.cmd('restore '+r['id']);self.assertEqual(self.store.records(self.a,'door'),[])
        self.cmd('approve '+r['id']);self.assertEqual(len(self.store.records(self.a,'door')),1)
    def test_edit_keeps_original_status(self):
        self.enable();r=json.loads(self.cmd('save reference door'))
        self.cmd('edit '+r['id']+' window')
        self.assertEqual(self.store.records(self.a,'window')[0]['text'],'window')
    def test_payload_bound_and_dedup(self):
        self.enable();self.cmd('save reference door')
        records=self.store.records(self.a,'door')
        self.assertEqual(len(bounded(records*20)),1)
        self.assertLessEqual(len(json.dumps(bounded(records*20),ensure_ascii=False).encode()),2400)
    def test_new_branch_or_segment_requires_permission(self):
        self.enable();self.cmd('save reference door')
        self.assertIn('error',self.tool({'action':'search','query':'door'},'new-segment'))
    def test_storage_factory_rechecks_profile(self):
        self.enable();self.cmd('save reference door')
        other=Path(self.tmp.name)/'other-profile'
        self.store.connection=lambda:sqlite3.connect(other)
        self.assertIn('error',self.tool({'action':'search','query':'door'}))
    def test_gateway_cannot_use_local_grant(self):
        self.enable();self.cmd('save reference door');self.ctx.surface='telegram'
        self.assertIn('local_session_required',self.tool({'action':'search','query':'door'})['error'])
    def test_no_legacy_store_is_read(self):
        legacy=Path(self.tmp.name)/'private.sqlite3';legacy.write_bytes(b'PRIVATE')
        self.enable();self.assertEqual(self.store.records(self.a,'PRIVATE'),[])
        self.assertEqual(legacy.read_bytes(),b'PRIVATE')
    def test_registration_only_public_ctx(self):
        register_stock(self.ctx)
        names=[r[0] for r in self.ctx.registrations]
        self.assertEqual(set(names),{'register_tool','register_hook','register_command','register_skill','register_auxiliary_task'})
        self.assertEqual(names.count('register_skill'),6)

if __name__=='__main__':unittest.main()
