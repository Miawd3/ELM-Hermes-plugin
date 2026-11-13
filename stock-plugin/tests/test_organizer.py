import json
from types import SimpleNamespace
import unittest
import test_stock
from elm_plugin.stock_organizer import validate

class OrganizerTests(unittest.TestCase):
    setUp=test_stock.StockTests.setUp
    tearDown=test_stock.StockTests.tearDown
    cmd=test_stock.StockTests.cmd
    tool=test_stock.StockTests.tool
    enable=test_stock.StockTests.enable
    def prepare(self):
        self.enable();self.cmd('capture on');self.cmd('organizer on')
        return self.store.capture_turn(self.a,'I like blue doors.','The project has a red door.')
    def answer(self,records,callback=None):
        def complete(**kwargs):
            self.ctx.calls.append(kwargs)
            if callback:callback()
            return SimpleNamespace(text=json.dumps({'records':records}))
        self.ctx.llm.complete=complete
    def test_organizer_needs_explicit_permission(self):
        self.enable();self.cmd('capture on');source=self.store.capture_turn(self.a,'x','y')
        self.assertIn('enable_elm_and_organizer_first',self.cmd('organize '+source))
        self.assertEqual(self.ctx.calls,[])
    def test_exact_excerpt_pending_and_role_model_slot(self):
        source=self.prepare();self.answer([{'kind':'user','text':'I like blue doors.','tags':['color']}])
        result=json.loads(self.cmd('organize '+source))
        self.assertEqual(result['drafts'][0]['status'],'pending')
        self.assertEqual(self.store.records(self.a,'blue'),[])
        self.assertEqual(self.ctx.calls[0]['task'],'elm_organizer')
        self.assertEqual(len(self.store.records(self.a,'blue',status='pending')),1)
    def test_duplicate_organize_deduplicates(self):
        source=self.prepare();self.answer([{'kind':'user','text':'I like blue doors.','tags':[]}])
        self.cmd('organize '+source);self.cmd('organize '+source)
        self.assertEqual(len(self.store.records(self.a,'blue',status='pending')),1)
    def test_invalid_partial_batch_writes_nothing(self):
        source=self.prepare();self.answer([{'kind':'user','text':'I like blue doors.','tags':[]},
                                          {'kind':'user','text':'hallucinated fact','tags':[]}])
        self.assertIn('organizer_failed_no_drafts_saved',self.cmd('organize '+source))
        self.assertEqual(self.store.records(self.a,status='pending'),[])
    def test_assistant_user_assertion_not_accepted(self):
        with self.assertRaises(ValueError):validate('{"records":[{"kind":"user","text":"You like red","tags":[]}]}',{'user':'Hi','assistant':'You like red'})
    def test_organizer_scope_change_aborts(self):
        source=self.prepare();self.answer([{'kind':'project','text':'I like blue doors.','tags':[]}],lambda:self.cmd('project other'))
        self.assertIn('scope_changed_retry',self.cmd('organize '+source))
        self.assertEqual(self.store.records(self.a,status='pending'),[])
    def test_organizer_aba_change_aborts(self):
        source=self.prepare()
        def change():self.cmd('project temporary');self.cmd('project off')
        self.answer([{'kind':'project','text':'I like blue doors.','tags':[]}],change)
        self.assertIn('scope_changed_retry',self.cmd('organize '+source))
    def test_search_scope_change_aborts(self):
        self.enable();self.cmd('agent on');self.cmd('save reference door')
        def complete(**kwargs):
            self.cmd('project other')
            return SimpleNamespace(text='{"queries":[]}')
        self.ctx.llm.complete=complete
        result=self.tool({'action':'search','query':'door','use_agent':True})
        self.assertIn('scope_changed_retry',result['error'])
    def test_search_revoke_aborts(self):
        self.enable();self.cmd('agent on')
        def complete(**kwargs):
            self.cmd('off')
            return SimpleNamespace(text='{"queries":[]}')
        self.ctx.llm.complete=complete
        self.assertIn('error',self.tool({'action':'search','query':'door','use_agent':True}))
    def test_records_paginate(self):
        self.enable()
        for i in range(15):self.cmd('save reference record '+str(i))
        first=json.loads(self.cmd('list'));second=json.loads(self.cmd('list 12'))
        self.assertEqual(len(first['records']),12);self.assertEqual(len(second['records']),3)
        self.assertFalse({r['id'] for r in first['records']} & {r['id'] for r in second['records']})
    def test_sources_paginate(self):
        self.enable();self.cmd('capture on')
        for i in range(22):self.store.capture_turn(self.a,str(i),'x')
        self.assertEqual(len(json.loads(self.cmd('sources'))['sources']),20)
        self.assertEqual(len(json.loads(self.cmd('sources 20'))['sources']),2)
    def test_source_text_pagination(self):
        self.enable();self.cmd('capture on')
        source=self.store.capture_turn(self.a,'x'*5000,'y')
        self.assertEqual(len(self.store.source(self.a,source)['user']),4000)
        self.assertEqual(len(self.store.source(self.a,source,4000)['user']),1000)
    def test_punctuation_query_not_global_dump(self):
        self.enable();self.cmd('save reference secret')
        self.assertEqual(self.store.records(self.a,'%%%'),[])

    def test_unicode_casefold_search(self):
        self.enable();self.cmd('save reference Русский Текст Straße')
        self.assertEqual(len(self.store.records(self.a,'русский')),1)
        self.assertEqual(len(self.store.records(self.a,'STRASSE')),1)
