"""Operator forget behavior in disposable stores through real Hermes hooks."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch

from test_episode_capture import RealProviderHooks, pair, config, PLUGIN
from test_episode_recall import RecallBehavior, hashes
from elm_plugin.provider import ElmMemoryProvider
from elm_plugin.storage import load_binding
from elm_plugin.episode_capture import CaptureRefused
from elm_plugin.episode_recall import CONFIG_NAME
from elm_plugin.episode_forgetting import EpisodeForget
from agent.memory_manager import MemoryManager


class ForgetBehavior(unittest.TestCase):
    setUp = RealProviderHooks.setUp
    call = RecallBehavior.call

    def start(self, mode='read-only', context='primary'):
        p = ElmMemoryProvider()
        p.save_config({"budget_mode": "legacy-estimate", 'root': str(self.root), 'project':'orion', 'mode':mode, 'budget':700}, str(self.home))
        binding = load_binding(self.home)
        config(self.home, binding, explicit_proposals=True, proposal_author_id='human1', retention_seconds=60)
        (self.home / CONFIG_NAME).write_text(json.dumps({'format_version':1, 'enabled':True,
            'root_id':binding.root_id, 'project':'orion', 'budget':1200}))
        m = MemoryManager(); m.add_provider(p)
        m.initialize_all('session1', hermes_home=str(self.home), platform='cli', agent_context=context)
        self.addCleanup(m.shutdown_all)
        if p._episode_capture: p._episode_capture.clock=lambda:1000.
        return p,m

    def ingest(self,p,m,number=1,text='Remember: color = unique_emerald',stage=True):
        rows=pair(number,user=text,assistant='Acknowledged '+str(number))
        m.sync_all(rows[0]['content'],rows[1]['content'], session_id='session1', messages=rows,
                   turn_author={'id':'human1','is_bot':False})
        self.assertTrue(m.flush_pending(timeout=10))
        if stage:
            p._episode_capture.seal('session1','session_end'); p._episode_capture.prepare_batches()
        locator = self.call(m,query=text)['results'][0]['locator']
        return rows,locator

    def test_preview_read_only_and_exact_confirm_required(self):
        p,m=self.start(); _,locator=self.ingest(p,m)
        before=hashes(self.base)
        preview=p.episode_forget_preview(locator)
        self.assertEqual(preview['status'],'preview_only')
        self.assertEqual(preview['source_messages_to_remove'],2)
        self.assertEqual(before,hashes(self.base))
        for value in (None, True, '', 'f'*64):
            with self.assertRaises(CaptureRefused): p.episode_forget(locator,value)
        self.assertEqual(before,hashes(self.base))

    def test_pair_removed_queue_scrubbed_and_canonical_unchanged(self):
        p,m=self.start(); _,locator=self.ingest(p,m)
        before=hashes(self.root)
        result=p.episode_forget(locator,p.episode_forget_preview(locator)['plan_sha256'])
        self.assertEqual(result['replay_ids_retained'],2)
        self.assertFalse(result['limits']['secure_erasure'])
        self.assertFalse(result['external_outcome_review_required'])
        self.assertEqual(self.call(m,query='unique_emerald')['results'],[])
        self.assertIn('error',self.call(m,'elm_episode_read',locator=locator))
        row=p.episode_proposal_snapshot()['records'][0]
        self.assertEqual(row['status'],'revoked')
        self.assertEqual(row['payload'],{}); self.assertEqual(row['evidence'],{})
        self.assertIsNone(row['result']); self.assertEqual(row['object_hash'],'')
        self.assertEqual(before,hashes(self.root))
        self.assertIsNone(p._episode_capture.next_proposal())

    def test_replay_and_new_counterpart_after_restart_do_not_resurrect(self):
        p,m=self.start(); rows,locator=self.ingest(p,m)
        p.episode_forget(locator,p.episode_forget_preview(locator)['plan_sha256'])
        m.shutdown_all(); p,m=self.start()
        for sample in (rows,[rows[0],pair(9)[1]]):
            m.sync_all(sample[0]['content'],sample[1]['content'],session_id='session1',messages=sample,
                       turn_author={'id':'human1','is_bot':False})
            self.assertTrue(m.flush_pending(timeout=10))
        self.assertEqual(self.call(m,query='unique_emerald')['results'],[])
        self.assertEqual(p._episode_capture.status()['active_messages'],0)
        self.assertEqual(len(p.episode_proposal_snapshot()['records']),1)

    def test_unrelated_source_and_queued_proposal_survive(self):
        p,m=self.start(); _,locator=self.ingest(p,m)
        self.ingest(p,m,2,'Remember: launch = unique_amber')
        p.episode_forget(locator,p.episode_forget_preview(locator)['plan_sha256'])
        self.assertEqual(self.call(m,query='unique_amber')['matched_messages'],1)
        self.assertEqual([r['status'] for r in p.episode_proposal_snapshot()['records']],['revoked','queued'])

    def test_stale_plan_rejected_without_partial_removal(self):
        p,m=self.start(); _,locator=self.ingest(p,m)
        preview=p.episode_forget_preview(locator)
        item=p._episode_capture.next_proposal()
        before=hashes(self.base)
        with self.assertRaisesRegex(CaptureRefused,'forget_plan_changed'):
            p.episode_forget(locator,preview['plan_sha256'])
        self.assertEqual(before,hashes(self.base))
        self.assertIsNotNone(item)

    def test_forget_after_optout_does_not_reenable_capture(self):
        p,m=self.start(); _,locator=self.ingest(p,m)
        for filename in ('elm_episode_capture.json',CONFIG_NAME):
            (self.home/filename).unlink()
        control=EpisodeForget(self.home)
        result=control.apply(locator,control.preview(locator)['plan_sha256'])
        self.assertEqual(result['status'],'source_evidence_forgotten_locally')
        self.assertFalse((self.home/'elm_episode_capture.json').exists())
        self.assertIn('error',self.call(m,query='unique_emerald'))

    def test_submitted_copy_reported_not_canonical_removed(self):
        p,m=self.start(mode='proposal-only'); _,locator=self.ingest(p,m)
        self.assertEqual(p.flush_episode_proposals()['submitted'],1)
        before=hashes(self.root)
        result=p.episode_forget(locator,p.episode_forget_preview(locator)['plan_sha256'])
        self.assertTrue(result['external_outcome_review_required'])
        self.assertEqual(p.episode_proposal_snapshot()['records'][0]['status'],'revoked_submitted')
        self.assertEqual(before,hashes(self.root))
        self.assertEqual(p.flush_episode_proposals()['submitted'],0)

    def test_unknown_remains_dispatch_blocker_and_late_result_stays_scrubbed(self):
        p,m=self.start(); _,locator=self.ingest(p,m)
        cap=p._episode_capture; item=cap.next_proposal()
        cap.finish_proposal(item['submission_id'],error_code='engine_timeout')
        p.episode_forget(locator,p.episode_forget_preview(locator)['plan_sha256'])
        self.assertEqual(cap.next_proposal()['error_code'],'unresolved_previous_submission')
        cap.finish_proposal(item['submission_id'],result={'canonical_committed':True,'source_text':'must_not_persist'})
        record=p.episode_proposal_snapshot()['records'][0]
        self.assertEqual(record['status'],'revoked_submitted'); self.assertIsNone(record['result'])
        self.assertNotIn('must_not_persist',json.dumps(record))

    def test_claim_before_forget_never_dispatches(self):
        p,m=self.start(mode='proposal-only'); _,locator=self.ingest(p,m)
        cap=p._episode_capture; original=cap.next_proposal
        def revoke_after_claim():
            item=original()
            if item and not item.get('blocked'):
                control=EpisodeForget(self.home)
                control.apply(locator,control.preview(locator)['plan_sha256'])
            return item
        from elm_plugin import provider as module
        run=module.run_engine; dispatched=[]
        def spy(*args,**kwargs):
            if 'proposal-submit' in args: dispatched.append(args)
            return run(*args,**kwargs)
        with patch.object(cap,'next_proposal',revoke_after_claim),patch.object(module,'run_engine',spy):
            p.flush_episode_proposals()
        self.assertEqual(dispatched,[])
        self.assertEqual(p.episode_proposal_snapshot()['records'][0]['status'],'revoked')

    def test_not_a_model_tool_and_non_primary_is_blocked(self):
        p,m=self.start()
        self.assertFalse(m.has_tool('elm_episode_forget'))
        self.assertEqual(json.loads(p.handle_tool_call('elm_episode_forget',{}))['error'],'unknown_tool')
        p,m=self.start(context='subagent')
        with self.assertRaisesRegex(CaptureRefused,'unavailable'): p.episode_forget_preview('anything')

    def test_exact_scope_and_wrong_episode_rejected(self):
        p,m=self.start(); _,locator=self.ingest(p,m)
        before=hashes(self.base)
        for value in (locator.replace(p._episode_capture.scope,'f'*64),locator+'/extra',
                      locator.replace(locator.split('/')[-2],'episode_00000000-0000-0000-0000-000000000000')):
            with self.assertRaises(CaptureRefused): p.episode_forget_preview(value)
        self.assertEqual(before,hashes(self.base))

    def test_retained_links_do_not_stage_orphaned_live_user(self):
        p,m=self.start(); cap=p._episode_capture
        first=pair(1,user='Earlier ordinary source.',assistant='Shared assistant')
        cap.append_turn('session1',first[0]['content'],first[1]['content'],messages=first,
                        turn_author={'id':'human1','is_bot':False})
        cap.clock=lambda:1030.
        second=[pair(2,user='Remember: orphan = must_not_stage')[0],first[1]]
        cap.append_turn('session1',second[0]['content'],second[1]['content'],messages=second,
                        turn_author={'id':'human1','is_bot':False})
        cap.clock=lambda:1061.
        cap.seal('session1','session_end')
        self.assertEqual(cap.prepare_batches()['staged'],0)
        self.assertEqual(cap.proposal_snapshot()['records'],[])
        with closing(sqlite3.connect(cap.path)) as con:
            self.assertEqual(con.execute('SELECT count(*) FROM turns').fetchone()[0],2)
            self.assertEqual(con.execute('SELECT uid FROM messages').fetchall(),[('u2',)])

    def test_cli_preview_and_apply_uses_exact_profile(self):
        p,m=self.start(); _,locator=self.ingest(p,m)
        base=[sys.executable,'-B',str(PLUGIN/'manage.py')]
        args=['--hermes-home',str(self.home),'--locator',locator]
        preview=subprocess.run(base+['episode-forget-preview']+args,capture_output=True,text=True,check=True)
        plan=json.loads(preview.stdout)
        applied=subprocess.run(base+['episode-forget']+args+['--confirm-plan',plan['plan_sha256']],
                               capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(applied.stdout)['status'],'source_evidence_forgotten_locally')
        self.assertEqual(self.call(m,query='unique_emerald')['results'],[])


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ForgetBehavior))
    raise SystemExit(not result.wasSuccessful())
