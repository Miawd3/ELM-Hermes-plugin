"""Independent adversarial checks. Every data store is disposable synthetic data."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_episode_capture import RealProviderHooks, config, pair
from elm_plugin.provider import ElmMemoryProvider
from elm_plugin.storage import load_binding
from elm_plugin.episode_capture import EpisodeCapture, CaptureRefused
from elm_plugin.episode_recall import EpisodeRecall, CONFIG_NAME
from elm_plugin.episode_forgetting import EpisodeForget

class Independent(unittest.TestCase):
    setUp=RealProviderHooks.setUp
    def start(self):
        p=ElmMemoryProvider()
        p.save_config({"budget_mode": "legacy-estimate", 'root':str(self.root),'project':'orion','mode':'read-only','budget':700},str(self.home))
        self.binding=load_binding(self.home)
        config(self.home,self.binding,explicit_proposals=True,proposal_author_id='human1',retention_seconds=60)
        self.now=1000
        self.c,_=EpisodeCapture.from_profile(self.home,self.binding,'primary',clock=lambda:self.now)
        (self.home/CONFIG_NAME).write_text(json.dumps({'format_version':1,'enabled':True,'root_id':self.binding.root_id,'project':'orion','budget':1200}))
        self.r,_=EpisodeRecall.from_capture(self.c)
        self.f=EpisodeForget(self.home)
    def add(self,n=1,rows=None,session='s1'):
        rows=rows or pair(n,user='Remember: color = emerald')
        self.c.append_turn(session,rows[0]['content'],rows[1]['content'],messages=rows,turn_author={'id':'human1','is_bot':False})
        return rows
    def locator(self,uid='u1'):
        with closing(sqlite3.connect(self.c.path)) as con:
            ep=con.execute('SELECT episode_id FROM turns WHERE user_uid=? OR assistant_uid=?',(uid,uid)).fetchone()[0]
        return f'elm-episode://{self.c.scope}/{ep}/{uid}'
    def forget(self,loc):
        return self.f.apply(loc,self.f.preview(loc)['plan_sha256'])
    def stage(self):
        self.c.seal('s1','session_end'); self.c.prepare_batches()
    def rows(self,table):
        with closing(sqlite3.connect(self.c.path)) as con:
            con.row_factory=sqlite3.Row
            return [dict(x) for x in con.execute('SELECT * FROM '+table)]
    def test_preview_readonly_and_body_free(self):
        self.start(); self.add(); self.stage(); before=self.c.path.read_bytes()
        out=self.f.preview(self.locator())
        self.assertNotIn('emerald',json.dumps(out)); self.assertEqual(before,self.c.path.read_bytes())
    def test_shared_uid_chain_and_unrelated_survive(self):
        self.start(); a=self.add(); b=pair(2,user=a[0]['content']); b[0]=a[0]; self.add(rows=b,session='s2')
        d=pair(3); d[1]=b[1]; self.add(rows=d,session='s3'); self.add(4,session='s4')
        result=self.forget(self.locator('a1'))
        self.assertEqual(result['linked_pair_messages'],4)
        self.assertEqual({x['uid'] for x in self.rows('messages')},{'u4','a4'})
    def test_stale_preview_after_staging_is_atomic(self):
        self.start(); self.add(); loc=self.locator(); plan=self.f.preview(loc)
        self.stage(); before=self.c.path.read_bytes()
        with self.assertRaisesRegex(CaptureRefused,'forget_plan_changed'): self.f.apply(loc,plan['plan_sha256'])
        self.assertEqual(before,self.c.path.read_bytes())
    def test_expired_queued_payload_still_scrubbed(self):
        self.start(); self.add(); loc=self.locator(); self.stage(); self.now=1061; self.add(2)
        self.assertNotIn('u1',{x['uid'] for x in self.rows('messages')})
        self.forget(loc); p=self.rows('episode_proposals')[0]
        self.assertEqual(p['status'],'revoked'); self.assertEqual(p['payload'],'{}'); self.assertEqual(p['evidence'],'{}')
    def test_optout_no_reenable_needed(self):
        self.start(); self.add(); loc=self.locator()
        (self.home/'elm_episode_capture.json').write_text('{"enabled":false}')
        (self.home/CONFIG_NAME).unlink()
        self.forget(loc); self.assertEqual(self.rows('messages'),[])
    def test_restart_same_uid_and_mixed_replay(self):
        self.start(); original=self.add(); self.forget(self.locator())
        self.c,_=EpisodeCapture.from_profile(self.home,self.binding,'primary',clock=lambda:self.now)
        self.add(rows=original); self.assertEqual(self.rows('messages'),[])
        changed=pair(2); changed[0]=original[0]
        with self.assertRaises(CaptureRefused): self.add(rows=changed)
        self.assertEqual(self.rows('messages'),[])
    def test_recall_loaded_then_forget_read_and_search(self):
        for method in ['read','search']:
            with self.subTest(method=method):
                self.start(); self.add(); loc=self.locator(); original=self.r._rows; triggered=False
                def wrapped(*args,**kwargs):
                    nonlocal triggered
                    rows=original(*args,**kwargs)
                    if not triggered: triggered=True; self.forget(loc)
                    return rows
                with patch.object(self.r,'_rows',side_effect=wrapped):
                    with self.assertRaisesRegex(CaptureRefused,'episode_source_unavailable'):
                        getattr(self.r,method)(loc if method=='read' else 'emerald')
                # New capture UIDs required after revocation; reset fixture per subtest.
                if method=='read':
                    self.c.path.unlink()
    def test_claim_forget_prevents_dispatch_late_result_scrubbed(self):
        self.start(); self.add(); loc=self.locator(); self.stage(); item=self.c.next_proposal(); self.forget(loc)
        with self.assertRaisesRegex(CaptureRefused,'proposal_revoked_before_dispatch'):
            with self.c.dispatch_guard(item['submission_id']): self.fail('dispatch permitted')
        self.c.finish_proposal(item['submission_id'],result={'canonical_committed':True,'body':'emerald'})
        p=self.rows('episode_proposals')[0]
        self.assertEqual(p['status'],'revoked_submitted'); self.assertIsNone(p['result']); self.assertEqual(p['payload'],'{}')
    def test_bad_scope_and_missing_ledger_refuse_without_mutation(self):
        self.start(); self.add(); loc=self.locator(); before=self.c.path.read_bytes()
        with self.assertRaises(CaptureRefused): self.f.preview(loc.replace(self.c.scope,'f'*64))
        self.assertEqual(before,self.c.path.read_bytes())
        with closing(sqlite3.connect(self.c.path)) as con,con: con.execute("DELETE FROM seen WHERE uid='a1'")
        before=self.c.path.read_bytes()
        with self.assertRaisesRegex(CaptureRefused,'forget_replay_ledger_missing'): self.f.preview(loc)
        self.assertEqual(before,self.c.path.read_bytes())
    def test_expired_shared_pair_proposal_graph(self):
        self.start(); first=self.add(); second=pair(2,user='Remember: shade = emerald'); second[1]=first[1]
        self.add(rows=second); loc=self.locator(); self.stage()
        self.now=1061; self.add(3)
        self.forget(loc)
        self.assertTrue(all(p['status']=='revoked' for p in self.rows('episode_proposals')))
    def test_historical_missing_links_explicit_disclosure(self):
        self.start(); self.add(); loc=self.locator(); self.stage()
        # Simulate legacy v2 expiry, which removed both text and linkage.
        with closing(sqlite3.connect(self.c.path)) as con,con:
            con.execute('DELETE FROM messages'); con.execute('DELETE FROM turns'); con.execute('DELETE FROM episodes')
        plan=self.f.preview(loc)
        self.assertTrue(plan['historical_pair_links_unavailable'])
        self.assertEqual(plan['retained_pair_links'],0)
        self.assertIn('historical_missing_links_not_reconstructed',plan['limits']['pair_linkage_scope'])
        self.f.apply(loc,plan['plan_sha256'])
        self.assertEqual(self.rows('episode_proposals')[0]['payload'],'{}')
    def test_expiry_links_capacity_and_session_boundaries(self):
        self.start()
        config(self.home,self.binding,explicit_proposals=True,proposal_author_id='human1',retention_seconds=60,
               max_messages=4,max_seen_ids=4)
        self.c,_=EpisodeCapture.from_profile(self.home,self.binding,'primary',clock=lambda:self.now)
        self.add(); first_loc=self.locator(); first_episode=self.rows('episodes')[0]['id']
        self.now=1061; self.add(2)
        self.assertEqual(len(self.rows('turns')),2)
        self.assertEqual(len(self.rows('episodes')),2)
        old=next(e for e in self.rows('episodes') if e['id']==first_episode)
        self.assertEqual(old['reason'],'source_expired'); self.assertIsNotNone(old['sealed'])
        self.assertEqual({r['uid'] for r in self.rows('messages')},{'u2','a2'})
        def capture_content():
            # Refusal updates only the existing bounded, text-free gap row.
            # Preserve every schema statement and every other table's data.
            with closing(sqlite3.connect(self.c.path)) as con:
                return tuple(statement for statement in con.iterdump()
                             if not statement.startswith('INSERT INTO "capture_gap_events" '))
        self.assertEqual(self.rows('capture_gap_events'),
                         [{'singleton':1,'refused_attempts':0,'last_reason':'none'}])
        before=capture_content()
        with self.assertRaisesRegex(CaptureRefused,'capture_capacity_reached'): self.add(3)
        self.assertEqual(before,capture_content())
        self.assertEqual(self.rows('capture_gap_events'),
                         [{'singleton':1,'refused_attempts':1,'last_reason':'capture_capacity_reached'}])
        self.forget(first_loc)
        self.assertEqual(len(self.rows('seen')),4)
        self.assertEqual(len(self.rows('turns')),1)
        before=capture_content()
        with self.assertRaisesRegex(CaptureRefused,'capture_capacity_reached'): self.add(3)
        self.assertEqual(before,capture_content())
        self.assertEqual(self.rows('capture_gap_events'),
                         [{'singleton':1,'refused_attempts':2,'last_reason':'capture_capacity_reached'}])
    def test_dispatch_lock_prevents_concurrent_apply(self):
        self.start(); self.add(); loc=self.locator(); self.stage(); item=self.c.next_proposal()
        plan=self.f.preview(loc)['plan_sha256']
        with self.c.dispatch_guard(item['submission_id']):
            with self.assertRaises(sqlite3.OperationalError): self.f.apply(loc,plan)
            self.assertEqual(len(self.rows('messages')),2)
        self.f.apply(loc,plan)
        self.assertEqual(self.rows('messages'),[])
    def test_real_submitted_governance_untouched(self):
        from test_explicit_proposals import RealGovernanceBatches
        p,m=RealGovernanceBatches.enabled_provider(self)
        rows=RealGovernanceBatches.send(self,m,text='Remember: audit_marker = emerald')
        m.on_session_end(rows)
        self.c=p._episode_capture
        record=p.episode_proposal_snapshot()['records'][0]
        self.assertEqual(record['status'],'submitted')
        def root_hashes():
            return {str(x.relative_to(self.root)):hashlib.sha256(x.read_bytes()).hexdigest()
                    for x in self.root.rglob('*') if x.is_file() and not x.name.endswith(('-wal','-shm'))}
        before=root_hashes(); loc=self.locator()
        plan=p.episode_forget_preview(loc)
        self.assertTrue(plan['external_outcome_review_required'])
        p.episode_forget(loc,plan['plan_sha256'])
        self.assertEqual(before,root_hashes())
        record=p.episode_proposal_snapshot()['records'][0]
        self.assertEqual(record['status'],'revoked_submitted'); self.assertEqual(record['payload'],{})
        self.assertEqual(RealGovernanceBatches.governance_counts(self),(0,1))
    def test_model_surface_no_forgetting(self):
        self.start()
        from agent.memory_manager import MemoryManager
        p=ElmMemoryProvider(); m=MemoryManager(); m.add_provider(p)
        m.initialize_all('session1',hermes_home=str(self.home),platform='cli',agent_context='primary')
        self.addCleanup(m.shutdown_all)
        self.assertTrue(m.has_tool('elm_episode_search'))
        for name in ['elm_episode_forget','episode_forget','elm_episode_forget_preview']:
            self.assertFalse(m.has_tool(name))
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Independent))
    raise SystemExit(not result.wasSuccessful())
