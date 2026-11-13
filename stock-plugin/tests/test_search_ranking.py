"""Targeted regression tests, not a general retrieval benchmark."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from elm_plugin.stock_store import Store, Denied, session_key

class SearchRankingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(lambda:sqlite3.connect(Path(self.tmp.name)/'test.db'))
        self.a=session_key('a','cli');self.b=session_key('b','cli')
        for sid in (self.a,self.b):self.store.settings(sid,{'enabled':True})
    def tearDown(self):self.tmp.cleanup()
    def add(self,content,sid=None,approved=True,tags=()):
        return self.store.insert(sid or self.a,'reference',content,tags=tags,approved=approved)['id']
    def test_old_complete_match_survives_twelve_recent_partial_matches(self):
        target=self.add('Door unlock code is violet.')
        for i in range(20):self.add(f'Door decoration {i}')
        self.assertEqual(self.store.records(self.a,'door unlock code')[0]['id'],target)
    def test_newer_equal_coverage_wins_tie(self):
        self.add('Door unlock code is old.');new=self.add('Door unlock code is new.')
        self.assertEqual(self.store.records(self.a,'door unlock code')[0]['id'],new)
    def test_duplicate_query_terms_do_not_change_order(self):
        self.add('door');self.add('unlock code')
        one=self.store.records(self.a,'door unlock code')
        repeat=self.store.records(self.a,'door door door unlock code')
        self.assertEqual(one,repeat)
    def test_literals_and_unicode_substrings_preserved(self):
        target=self.add('ДВЕРЬ foo_bar unlock')
        self.add('fooXbar unlock')
        self.assertEqual(self.store.records(self.a,'двер foo_bar')[0]['id'],target)
        self.assertEqual(len(self.store.records(self.a,'foo_bar')),1)
    def test_scopes_and_status_filter_before_rank_and_limit(self):
        self.add('door unlock code',self.b)
        self.add('door unlock code',approved=False)
        trashed=self.add('door unlock code');self.store.change(self.a,trashed,'trash')
        mine=self.add('door')
        self.assertEqual([r['id'] for r in self.store.records(self.a,'door unlock code',limit=1)],[mine])
    def test_unqueried_lists_stay_recent_and_pages_do_not_overlap(self):
        ids=[self.add('door unlock code' if i%2 else 'door') for i in range(9)]
        self.assertEqual(self.store.records(self.a)[0]['id'],ids[-1])
        ranked=self.store.records(self.a,'door unlock code',limit=9)
        first=self.store.records(self.a,'door unlock code',limit=4)
        second=self.store.records(self.a,'door unlock code',limit=5,offset=4)
        self.assertEqual(first+second,ranked)
    def test_edited_content_changes_rank_immediately(self):
        target=self.add('door unlock code');other=self.add('door unlock')
        self.store.change(self.a,target,'edit','unrelated')
        self.assertEqual(self.store.records(self.a,'door unlock code')[0]['id'],other)
    def test_tags_and_revocation(self):
        target=self.add('door',tags=['unlock','code'])
        self.add('door')
        self.assertEqual(self.store.records(self.a,'door unlock code')[0]['id'],target)
        self.store.settings(self.a,{'enabled':False})
        with self.assertRaises(Denied):self.store.records(self.a,'door unlock code')
    def test_punctuation_only_and_injection_are_data(self):
        self.add('harmless')
        self.assertEqual(self.store.records(self.a,"%';--"),[])
        self.store.records(self.a,"' OR 1=1 --")
        self.assertEqual(len(self.store.records(self.a)),1)

if __name__=='__main__':unittest.main()
