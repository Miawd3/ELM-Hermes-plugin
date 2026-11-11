"""Independent synthetic review-bridge attacks, without inherited test methods.

Fixtures deny network through the shared capture audit hook. This suite does not
connect to live profiles, deploy a plugin, or accept canonical memories.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ast
import copy
import hashlib
import json
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import dataclass
from unittest.mock import patch
import test_candidate_inbox as fixtures
from elm_plugin.episode_capture import CaptureRefused
from elm_plugin.candidate_inbox import CandidateInboxControl
from elm_plugin.engine import ElmError

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT.parents[1]

class IndependentReviewBoundary(unittest.TestCase):
    def test_bridge_has_no_acceptance_or_autonomous_entrypoint(self):
        source = (PLUGIN / 'elm_plugin/operator_review.py').read_text()
        tree = ast.parse(source)
        forbidden = {'accept_proposal', 'supersede_claim', 'activate_agent_memory',
                     'remember_submit', 'accept', 'remember-submit', 'proposal-accept'}
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
        for call in calls:
            name = getattr(call.func, 'id', getattr(call.func, 'attr', ''))
            self.assertNotIn(name, forbidden)
            if name == 'run_engine':
                literal_args = {x.value for x in call.args if isinstance(x, ast.Constant) and isinstance(x.value, str)}
                self.assertFalse(literal_args & forbidden)

    def test_bridge_not_registered_as_provider_or_model_tool(self):
        for filename in ('provider.py', 'schemas.py'):
            source = (PLUGIN / 'elm_plugin' / filename).read_text()
            self.assertNotIn('operator_review', source)

from elm_plugin.operator_review import OperatorReviewBridge, ReviewBridgeControl, CONFIG_NAME
from elm_plugin import operator_review_store as store

class IndependentReviewBehavior(unittest.TestCase):
    setUp = fixtures.DurableInbox.setUp
    start_inbox = fixtures.DurableInbox.start
    add_source = fixtures.DurableInbox.add_source
    response = fixtures.DurableInbox.response
    accept_span = fixtures.DurableInbox.accept_span

    def start(self, enabled=True):
        self.binding.mode = 'proposal-only'
        self.binding.path = self.home / 'synthetic-root'
        self.start_inbox()
        if enabled:
            (self.home / CONFIG_NAME).write_text(json.dumps({'format_version': 1, 'enabled': True,
                'root_id': self.binding.root_id, 'project': self.binding.project, 'operator_id': 'reviewer'}))
        self.bridge, reason = OperatorReviewBridge.from_inbox(self.inbox)
        return reason

    def semantics(self, **changes):
        return {'subject': 'speaker:human1', 'predicate': 'preference.color', 'object': 'Avoid red',
            'scope': 'project:orion', 'valid_from': '2026-11-06T12:00:00Z',
            'context': 'The whole sentence negates the extracted substring.',
            'attribution': 'Supplied by human1; identity is not independently authenticated.',
            'uncertainty': 'Single statement; duration unknown.', **changes}

    def source(self):
        request = self.inbox.prepare([self.add_source('I do not prefer red. Someone else said "prefer red".')], request_key='batch')
        response = self.response(request, quote='prefer red', start=9)
        result, _ = self.accept_span(request, response)
        return request['batch_id'], result['candidates'][0]['candidate_id']

    def draft(self):
        return self.bridge.prepare(*self.source(), self.semantics(), request_key='review')

    def rows(self):
        with closing(sqlite3.connect(self.capture.path)) as con:
            con.row_factory = sqlite3.Row
            return store.records(con)

    def submit(self, view):
        return self.bridge.submit(view['review_id'], view['plan_sha256'], confirm=True)

    def test_disabled_bridge_creates_no_review_table(self):
        self.assertEqual(self.start(False), 'disabled')
        self.assertIsNone(self.bridge)
        with closing(sqlite3.connect(self.capture.path)) as con:
            self.assertFalse(store.exists(con))

    def test_read_only_binding_refused(self):
        self.start(); self.binding.mode = 'read-only'
        with self.assertRaises(CaptureRefused): OperatorReviewBridge.from_inbox(self.inbox)

    def test_prepare_requires_complete_operator_semantics_and_scope(self):
        self.start(); batch, candidate = self.source()
        for key in self.semantics():
            value = self.semantics(); del value[key]
            with self.subTest(missing=key), self.assertRaises(CaptureRefused):
                self.bridge.prepare(batch, candidate, value, request_key='bad')
        for value in (self.semantics(scope='project:other'), self.semantics(valid_from='2026-11-06'),
                      self.semantics(object=' '), self.semantics(accepted_memory=True), self.semantics(context='x\n')):
            with self.assertRaises(CaptureRefused):
                self.bridge.prepare(batch, candidate, value, request_key='bad')
        self.assertEqual(self.rows(), [])

    def test_operator_meaning_does_not_inherit_negated_substring(self):
        self.start(); view = self.draft()
        self.assertEqual(view['proposal_payload']['object'], 'Avoid red')
        self.assertIn('I do not prefer red', view['evidence']['sources'][0]['text'])
        self.assertFalse(view['operator_identity_authenticated'])
        self.assertFalse(view['accepted_memory']); self.assertFalse(view['is_authorization'])
        self.assertNotIn('requested_authority', view['proposal_payload'])
        self.assertNotIn('supersedes_claim_id', view['proposal_payload'])
        stored = json.dumps(self.rows())
        self.assertNotIn('Someone else said', stored)
        self.assertIn('Avoid red', stored)

    def test_confirmation_is_exact_bool_and_exact_digest(self):
        self.start(); view = self.draft()
        with patch('elm_plugin.operator_review.run_engine') as run:
            for confirm, digest in ((False,view['plan_sha256']), (1,view['plan_sha256']), ('yes',view['plan_sha256']),
                                    (True,'0'*64), (True,'yes')):
                with self.assertRaises(CaptureRefused): self.bridge.submit(view['review_id'],digest,confirm=confirm)
            run.assert_not_called()
        self.assertEqual(self.rows()[0]['state'], 'prepared')

    def test_changed_meaning_requires_new_digest_and_revokes_old_draft(self):
        self.start(); old = self.draft(); row = self.rows()[0]
        new = self.bridge.prepare(row['batch_id'], row['candidate_id'], self.semantics(object='Avoid blue'),
                                  request_key='correction', replaces_review_id=old['review_id'])
        self.assertNotEqual(old['plan_sha256'], new['plan_sha256'])
        with patch('elm_plugin.operator_review.run_engine') as run:
            with self.assertRaises(CaptureRefused): self.submit(old)
            with self.assertRaises(CaptureRefused):
                self.bridge.submit(new['review_id'],old['plan_sha256'],confirm=True)
            run.assert_not_called()
        self.assertEqual({r['state'] for r in self.rows()}, {'revoked', 'prepared'})

    def test_reused_key_cannot_change_meaning(self):
        self.start(); self.draft(); row=self.rows()[0]
        with self.assertRaisesRegex(CaptureRefused,'key_conflict'):
            self.bridge.prepare(row['batch_id'],row['candidate_id'],self.semantics(object='Prefer red'),request_key='review')
        self.assertEqual(len(self.rows()),1)

    def test_source_mutation_after_preview_prevents_dispatch_forever(self):
        self.start(); view=self.draft()
        with closing(sqlite3.connect(self.capture.path)) as con,con:
            old=con.execute("SELECT text FROM messages WHERE uid='u1'").fetchone()[0]
            con.execute("UPDATE messages SET text='Forged' WHERE uid='u1'")
        with patch('elm_plugin.operator_review.run_engine') as run:
            with self.assertRaises(CaptureRefused): self.submit(view)
            with closing(sqlite3.connect(self.capture.path)) as con,con:
                con.execute("UPDATE messages SET text=? WHERE uid='u1'",(old,))
            self.bridge=OperatorReviewBridge.from_inbox(self.inbox)[0]
            with self.assertRaises(CaptureRefused): self.submit(view)
            run.assert_not_called()
        self.assertTrue(self.rows()[0]['state'].startswith('revoked'))
        self.assertEqual(self.rows()[0]['semantics'],'{}')

    def test_bridge_config_change_and_restore_does_not_revive_draft(self):
        self.start(); view=self.draft(); path=self.home/CONFIG_NAME; original=path.read_text()
        path.write_text(original+' ')
        with self.assertRaises(CaptureRefused): self.bridge.inspect(view['review_id'])
        path.write_text(original); self.bridge=OperatorReviewBridge.from_inbox(self.inbox)[0]
        with self.assertRaises(CaptureRefused): self.submit(view)

    def test_inbox_revocation_immediately_scrubs_interpretation(self):
        self.start(); view=self.draft(); batch=self.rows()[0]['batch_id']
        CandidateInboxControl(self.home,self.binding).revoke(batch)
        self.assertEqual(self.rows()[0]['state'],'revoked')
        self.assertEqual(self.rows()[0]['semantics'],'{}')
        with self.assertRaises(CaptureRefused): self.submit(view)

    def test_concurrent_confirmation_dispatches_at_most_once(self):
        self.start(); view=self.draft()
        def confirm(_):
            bridge=OperatorReviewBridge.from_inbox(self.inbox)[0]
            try: return bridge.submit(view['review_id'],view['plan_sha256'],confirm=True)
            except CaptureRefused: return None
        with patch('elm_plugin.operator_review.run_engine', return_value={'canonical_committed':True,'status':'pending'}) as run:
            with ThreadPoolExecutor(max_workers=8) as pool: results=list(pool.map(confirm,range(16)))
            self.assertEqual(run.call_count,1)
        self.assertEqual(self.rows()[0]['state'],'submitted')
        self.assertTrue(any(r and r['governance_submission_recorded'] for r in results))

    def test_restart_replay_reports_recorded_without_engine_call(self):
        self.start(); view=self.draft()
        with patch('elm_plugin.operator_review.run_engine',return_value={'canonical_committed':True,'status':'pending'}) as run:
            first=self.submit(view)
            self.bridge=OperatorReviewBridge.from_inbox(self.inbox)[0]
            self.assertEqual(first,self.submit(view)); self.assertEqual(run.call_count,1)

    def test_timeout_permanently_blocks_auto_retry_even_after_revoke(self):
        self.start(); view=self.draft()
        with patch('elm_plugin.operator_review.run_engine',side_effect=ElmError('engine_timeout','uncertain')) as run:
            receipt=self.submit(view)
            self.assertTrue(receipt['manual_outcome_review_required'])
            self.assertFalse(receipt['governance_submission_recorded'])
            self.bridge=OperatorReviewBridge.from_inbox(self.inbox)[0]
            with self.assertRaises(CaptureRefused): self.submit(view)
            row=self.rows()[0]; batch,candidate=row['batch_id'],row['candidate_id']
            ReviewBridgeControl(self.home,self.binding).revoke(view['review_id'])
            self.assertEqual(self.rows()[0]['state'],'revoked_unknown')
            with self.assertRaises(CaptureRefused):
                self.bridge.prepare(batch,candidate,self.semantics(),request_key='new')
            self.assertEqual(run.call_count,1)

    def test_malformed_engine_success_is_unknown(self):
        self.start(); view=self.draft()
        with patch('elm_plugin.operator_review.run_engine',return_value={'status':'pending'}):
            receipt=self.submit(view)
        self.assertTrue(receipt['manual_outcome_review_required'])
        self.assertEqual(receipt['state'],'unknown')

    def test_submitted_revocation_warns_canonical_proposal_survives(self):
        self.start(); view=self.draft()
        with patch('elm_plugin.operator_review.run_engine',return_value={'canonical_committed':True,'status':'pending'}):
            self.submit(view)
        result=ReviewBridgeControl(self.home,self.binding).revoke(view['review_id'])
        self.assertTrue(result['external_outcome_review_required'])
        self.assertFalse(result['canonical_proposals_removed']); self.assertFalse(result['accepted_claims_removed'])
        self.assertEqual(self.rows()[0]['state'],'revoked_submitted')
        self.assertEqual(self.rows()[0]['payload'],'{}')

    def test_receipt_does_not_claim_terminal_governance_replay_is_pending(self):
        self.start(); view=self.draft()
        with patch('elm_plugin.operator_review.run_engine',return_value={'canonical_committed':True,'status':'accepted','idempotent_replay':True}):
            receipt=self.submit(view)
        self.assertFalse(receipt['accepted_memory'])
        self.assertNotEqual(receipt.get('status'),'pending')
        self.assertEqual(receipt['current_canonical_status'],'not_inspected')
        self.assertFalse(receipt['acceptance_performed'])

    def test_corrupt_review_table_revocation_quarantines_and_blocks(self):
        self.start(); view=self.draft()
        with closing(sqlite3.connect(self.capture.path)) as con,con:
            con.execute("UPDATE operator_span_reviews SET state='accepted'")
        with self.assertRaises(CaptureRefused): self.bridge.inspect(view['review_id'])
        result=ReviewBridgeControl(self.home,self.binding).revoke()
        self.assertTrue(result['permanently_blocked'])
        self.assertTrue(result['external_outcome_review_required'])
        with self.assertRaises(CaptureRefused): self.bridge.list_reviews()


    def test_forgetting_binds_operator_review_changes_into_confirmation(self):
        from elm_plugin.episode_forgetting import EpisodeForget
        self.start(); batch,candidate=self.source()
        source=self.inbox.review(batch)['sources'][0]['locator']
        forget=EpisodeForget(self.home,self.binding); old=forget.preview(source)
        view=self.bridge.prepare(batch,candidate,self.semantics(),request_key='review')
        with self.assertRaisesRegex(CaptureRefused,'plan_changed'): forget.apply(source,old['plan_sha256'])
        plan=forget.preview(source); self.assertEqual(plan['local_operator_review_copies'],1)
        forget.apply(source,plan['plan_sha256'])
        self.assertEqual(self.rows()[0]['state'],'revoked')
        self.assertEqual(self.rows()[0]['semantics'],'{}')
        with self.assertRaises(CaptureRefused): self.submit(view)

    def test_forgetting_submitted_interpretation_warns_canonical_survives(self):
        from elm_plugin.episode_forgetting import EpisodeForget
        self.start(); view=self.draft(); locator=view['evidence']['sources'][0]['locator']
        with patch('elm_plugin.operator_review.run_engine',return_value={'canonical_committed':True}): self.submit(view)
        forget=EpisodeForget(self.home,self.binding); plan=forget.preview(locator)
        self.assertTrue(plan['external_outcome_review_required'])
        self.assertFalse(plan['canonical_operator_proposals_removed'])
        forget.apply(locator,plan['plan_sha256'])
        self.assertEqual(self.rows()[0]['state'],'revoked_submitted')
        self.assertEqual(self.rows()[0]['payload'],'{}')

    def test_expired_source_scrubs_without_dispatch(self):
        self.start(); view=self.draft(); self.now=self.rows()[0]['expires']+1
        with patch('elm_plugin.operator_review.run_engine') as run:
            with self.assertRaises(CaptureRefused): self.submit(view)
            run.assert_not_called()
        self.assertEqual(self.rows()[0]['state'],'revoked')

    def test_crash_after_engine_commit_retains_uncertain_durable_intent(self):
        self.start(); view=self.draft(); original=store.save
        def die(con,row,**kwargs):
            original(con,row,**kwargs)
            if row['state']=='submitted': raise KeyboardInterrupt('simulated process death')
        with patch('elm_plugin.operator_review.run_engine',return_value={'canonical_committed':True}) as run:
            with patch.object(store,'save',side_effect=die),self.assertRaises(KeyboardInterrupt): self.submit(view)
            self.assertEqual(self.rows()[0]['state'],'submitting')
            self.bridge=OperatorReviewBridge.from_inbox(self.inbox)[0]
            with self.assertRaises(CaptureRefused): self.submit(view)
            self.assertEqual(run.call_count,1)

    def test_authentic_recomputed_storage_digest_does_not_bypass_semantic_plan(self):
        self.start(); view=self.draft(); row=self.rows()[0]
        meaning=json.loads(row['semantics']); meaning['object']='Prefer red'; row['semantics']=json.dumps(meaning)
        with closing(sqlite3.connect(self.capture.path)) as con,con:
            con.execute('UPDATE operator_span_reviews SET semantics=?,record_digest=?',(row['semantics'],store.digest(row)))
        with patch('elm_plugin.operator_review.run_engine') as run:
            with self.assertRaises(CaptureRefused): self.submit(view)
            run.assert_not_called()
        self.assertEqual(self.rows()[0]['state'],'revoked')

    def test_correction_cannot_silently_rewrite_submitted_proposal(self):
        self.start(); view=self.draft(); row=self.rows()[0]
        with patch('elm_plugin.operator_review.run_engine',return_value={'canonical_committed':True}): self.submit(view)
        with self.assertRaises(CaptureRefused):
            self.bridge.prepare(row['batch_id'],row['candidate_id'],self.semantics(object='Avoid blue'),
                                request_key='correction',replaces_review_id=view['review_id'])
        self.assertEqual(self.rows()[0]['state'],'submitted')

    def test_dispatch_is_only_existing_restricted_proposal_submission(self):
        self.start(); view=self.draft()
        with patch('elm_plugin.operator_review.run_engine',return_value={'canonical_committed':True}) as run:
            self.submit(view)
        args=run.call_args.args; payload=run.call_args.kwargs['request']
        self.assertEqual(args[2:],('proposal-submit','--request-stdin','--allow-project','orion'))
        self.assertEqual(args[:2],(self.home,self.binding.path))
        self.assertEqual(set(payload),{'submission_id','project','subject','predicate','object','valid_from',
                                       'sensitivity','rationale','source_refs','evidence'})
        self.assertEqual(payload['sensitivity'],'restricted')
        self.assertEqual(payload,view['proposal_payload'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
