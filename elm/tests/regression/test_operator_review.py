"""Synthetic explicit review bridge tests. Existing fixture denies network."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import copy
import json
import sqlite3
import unittest
from unittest.mock import patch
from test_candidate_inbox import DurableInbox
from elm_plugin.operator_review import OperatorReviewBridge, ReviewBridgeControl, CONFIG_NAME
from elm_plugin import operator_review_store as store
from elm_plugin.episode_capture import CaptureRefused
from elm_plugin.episode_forgetting import EpisodeForget
from elm_plugin.engine import ElmError


class OperatorReview(unittest.TestCase):
    setUp = DurableInbox.setUp
    add_source = DurableInbox.add_source
    response = DurableInbox.response
    accept_span = DurableInbox.accept_span
    restart_inbox = DurableInbox.restart

    def start(self, enabled=True, **kwargs):
        DurableInbox.start(self, **kwargs)
        self.binding.mode = 'proposal-only'
        self.binding.path = self.home / 'synthetic-root'
        if enabled:
            (self.home / CONFIG_NAME).write_text(json.dumps({'format_version': 1, 'enabled': True,
                'root_id': self.binding.root_id, 'project': self.binding.project, 'operator_id': 'operator1'}))
        self.bridge, reason = OperatorReviewBridge.from_inbox(self.inbox)
        return reason

    def semantics(self, **updates):
        return {'subject': 'speaker:human1', 'predicate': 'preference.color', 'object': 'not red',
                'scope': 'project:orion', 'valid_from': '2026-11-06T00:00:00Z',
                'context': 'The full message negates the selected words; quoted speech is another person.',
                'attribution': 'Caller identifies the source sender; identity is unverified.',
                'uncertainty': 'Operator interpretation; not established as enduring fact.', **updates}

    def prepare(self, text='I do not prefer red. Someone else said prefer red.', key='one', **kwargs):
        request = self.inbox.prepare([self.add_source(text)], request_key='source')
        result, _ = self.accept_span(request, self.response(request, quote='prefer red', start=text.index('prefer red')))
        self.batch_id, self.candidate_id, self.locator = request['batch_id'], result['candidates'][0]['candidate_id'], request['sources'][0]['locator']
        return self.bridge.prepare(self.batch_id, self.candidate_id, self.semantics(), request_key=key, **kwargs)

    def restart(self):
        self.restart_inbox()
        self.bridge, reason = OperatorReviewBridge.from_inbox(self.inbox)
        self.assertEqual(reason, 'ready')

    def rows(self):
        with closing(sqlite3.connect(self.capture.path)) as con:
            con.row_factory = sqlite3.Row
            return store.records(con)

    def test_disabled_default_noninitializing(self):
        self.assertEqual(self.start(enabled=False), 'disabled')
        self.assertIsNone(self.bridge)
        with closing(sqlite3.connect(self.capture.path)) as con:
            self.assertFalse(store.exists(con))

    def test_prepare_needs_meaning_scope_context_not_extractor_labels(self):
        self.start(); preview = self.prepare()
        self.assertEqual(preview['operator_semantics']['object'], 'not red')
        candidate = preview['evidence']['candidates'][0]
        self.assertEqual(candidate['selection']['quote'], 'prefer red')
        self.assertEqual(candidate['truth'], 'not_evaluated')
        self.assertEqual(candidate['entailment'], 'not_evaluated')
        self.assertFalse(preview['accepted_memory']); self.assertFalse(preview['is_authorization'])
        self.assertIn('do not prefer red', preview['evidence']['sources'][0]['text'])
        for value in ({}, {'object': 'red'}, self.semantics(scope='project:other'), self.semantics(context=''),
                      self.semantics(accepted_memory=True), self.semantics(valid_from='2026-11-06')):
            with self.assertRaises(CaptureRefused):
                self.bridge.prepare(self.batch_id, self.candidate_id, value, request_key='bad')
        self.assertEqual(len(self.rows()), 1)

    def test_durable_review_replay_and_key_conflict(self):
        self.start(); before = self.prepare(); self.inbox.close(); self.restart()
        self.assertEqual(self.bridge.inspect(before['review_id']), before)
        self.assertEqual(self.bridge.prepare(self.batch_id, self.candidate_id, self.semantics(), request_key='one'), before)
        with self.assertRaisesRegex(CaptureRefused, 'key_conflict'):
            self.bridge.prepare(self.batch_id, self.candidate_id, self.semantics(object='blue'), request_key='one')

    def test_confirmation_exact_plan_and_boolean(self):
        self.start(); preview = self.prepare()
        with patch('elm_plugin.operator_review.run_engine') as engine:
            for plan, confirm in [(preview['plan_sha256'], False), (preview['plan_sha256'], 1), ('0'*64, True)]:
                with self.assertRaises(CaptureRefused): self.bridge.submit(preview['review_id'], plan, confirm=confirm)
            engine.assert_not_called()
        self.assertEqual(self.rows()[0]['state'], 'prepared')

    def test_submit_existing_closed_governance_pending_only_once(self):
        self.start(); preview = self.prepare()
        with patch('elm_plugin.operator_review.run_engine', return_value={'canonical_committed': True}) as engine:
            first = self.bridge.submit(preview['review_id'], preview['plan_sha256'], confirm=True)
            self.restart()
            self.assertEqual(self.bridge.submit(preview['review_id'], preview['plan_sha256'], confirm=True), first)
            self.assertEqual(engine.call_count, 1)
            args, kwargs = engine.call_args
            self.assertEqual(args[2], 'proposal-submit')
            payload = kwargs['request']
            self.assertFalse(any(k in payload for k in ('authority', 'accepted', 'supersedes_claim_id')))
            self.assertEqual(payload['object'], 'not red')
            self.assertEqual(payload['sensitivity'], 'restricted')
        self.assertEqual(first['state'], 'submitted'); self.assertFalse(first['accepted_memory'])

    def test_unknown_timeout_refusal_and_malformed_outcome_never_resend(self):
        self.start(); preview = self.prepare()
        with patch('elm_plugin.operator_review.run_engine', side_effect=ElmError('engine_timeout','synthetic')) as engine:
            result = self.bridge.submit(preview['review_id'], preview['plan_sha256'], confirm=True)
            self.assertEqual(result['state'], 'unknown')
            self.restart()
            with self.assertRaisesRegex(CaptureRefused, 'unresolved'): self.bridge.submit(preview['review_id'], preview['plan_sha256'], confirm=True)
            self.assertEqual(engine.call_count, 1)
            ReviewBridgeControl(self.home,self.binding).revoke(preview['review_id'])
            self.assertEqual(self.rows()[0]['state'], 'revoked_unknown')
            with self.assertRaisesRegex(CaptureRefused, 'unresolved'):
                self.bridge.prepare(self.batch_id,self.candidate_id,self.semantics(object='blue'),request_key='new')

    def test_source_change_before_confirm_scrubs_review_and_no_submission(self):
        self.start(); preview = self.prepare()
        with closing(sqlite3.connect(self.capture.path)) as con, con:
            con.execute("UPDATE messages SET text='different' WHERE uid='u1'")
        with patch('elm_plugin.operator_review.run_engine') as engine:
            with self.assertRaisesRegex(CaptureRefused, 'revoked'):
                self.bridge.submit(preview['review_id'],preview['plan_sha256'],confirm=True)
            engine.assert_not_called()
        self.assertEqual(self.rows()[0]['semantics'], '{}')

    def test_inbox_revocation_scrubs_operator_derivative(self):
        self.start(); preview = self.prepare(); self.inbox.revoke(self.batch_id)
        self.assertEqual(self.rows()[0]['state'], 'revoked')
        self.assertEqual(self.rows()[0]['payload'], '{}')
        self.restart()
        with self.assertRaisesRegex(CaptureRefused, 'revoked'): self.bridge.inspect(preview['review_id'])

    def test_bridge_optout_revokes_without_revival(self):
        self.start(); preview = self.prepare()
        path = self.home / CONFIG_NAME; previous = path.read_bytes(); path.unlink()
        self.assertEqual(OperatorReviewBridge.from_inbox(self.inbox), (None,'disabled'))
        path.write_bytes(previous); self.restart()
        with self.assertRaisesRegex(CaptureRefused, 'revoked'): self.bridge.inspect(preview['review_id'])

    def test_config_pin_change_after_restart_revokes(self):
        self.start(); preview = self.prepare()
        path=self.home / CONFIG_NAME; path.write_text(path.read_text()+' ')
        self.restart()
        with self.assertRaisesRegex(CaptureRefused, 'revoked'): self.bridge.inspect(preview['review_id'])

    def test_correction_revokes_unsubmitted_old_plan_atomically(self):
        self.start(); old=self.prepare()
        new=self.bridge.prepare(self.batch_id,self.candidate_id,self.semantics(object='unclear'),request_key='corrected',replaces_review_id=old['review_id'])
        self.restart()
        with self.assertRaisesRegex(CaptureRefused,'revoked'): self.bridge.submit(old['review_id'],old['plan_sha256'],confirm=True)
        with self.assertRaisesRegex(CaptureRefused,'plan_changed'): self.bridge.submit(new['review_id'],old['plan_sha256'],confirm=True)
        self.assertEqual(self.bridge.inspect(new['review_id'])['operator_semantics']['object'],'unclear')
        self.assertEqual(new['replaces_review_id'],old['review_id'])

    def test_forget_plan_binds_new_review_and_scrubs_pair_closure(self):
        self.start(); preview=self.prepare()
        forget=EpisodeForget(self.home,self.binding); plan=forget.preview(self.locator)
        self.bridge.prepare(self.batch_id,self.candidate_id,self.semantics(object='unclear'),request_key='second')
        with self.assertRaisesRegex(CaptureRefused,'plan_changed'):forget.apply(self.locator,plan['plan_sha256'])
        plan=forget.preview(self.locator)
        self.assertEqual(plan['local_operator_review_copies'],2)
        self.assertFalse(plan['canonical_operator_proposals_removed'])
        forget.apply(self.locator,plan['plan_sha256']); self.restart()
        self.assertTrue(all(r['state']=='revoked' and r['semantics']=='{}' for r in self.rows()))

    def test_forget_submitted_retains_outcome_metadata_not_payload(self):
        self.start(); preview=self.prepare()
        with patch('elm_plugin.operator_review.run_engine',return_value={'canonical_committed':True}):
            self.bridge.submit(preview['review_id'],preview['plan_sha256'],confirm=True)
        forget=EpisodeForget(self.home,self.binding); plan=forget.preview(self.locator)
        self.assertTrue(plan['external_outcome_review_required'])
        forget.apply(self.locator,plan['plan_sha256'])
        row=self.rows()[0]
        self.assertEqual(row['state'],'revoked_submitted'); self.assertEqual(row['payload'],'{}')
        self.assertEqual(row['submission_id'],preview['submission_id'])

    def test_source_expiry_scrubs_review_on_capture_sweep(self):
        self.start(retention_seconds=60); self.prepare(); self.now+=61
        self.capture.seal('s1','session_end')
        self.assertEqual(self.rows()[0]['state'],'revoked'); self.assertEqual(self.rows()[0]['semantics'],'{}')

    def test_corrupt_review_does_not_block_source_forgetting(self):
        self.start(); self.prepare()
        with closing(sqlite3.connect(self.capture.path)) as con,con:
            con.execute("UPDATE operator_span_reviews SET semantics='corrupt'")
        forget=EpisodeForget(self.home,self.binding); plan=forget.preview(self.locator)
        self.assertTrue(plan['operator_review_corruption_will_block'])
        forget.apply(self.locator,plan['plan_sha256'])
        self.assertEqual(len(self.recall._rows()),0)
        with self.assertRaisesRegex(CaptureRefused,'permanently_blocked'):self.rows()

    def test_concurrent_prepare_same_key_one_review(self):
        self.start(); preview=self.prepare()
        def prep(_):return self.bridge.prepare(self.batch_id,self.candidate_id,self.semantics(),request_key='one')
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(prep,range(8)))
        self.assertTrue(all(r==preview for r in results));self.assertEqual(len(self.rows()),1)

    def test_closed_handle_does_not_revoke_durable_review(self):
        self.start(); preview=self.prepare(); self.inbox.close()
        with self.assertRaisesRegex(CaptureRefused,'closed'):self.bridge.inspect(preview['review_id'])
        self.restart()
        self.assertEqual(self.bridge.inspect(preview['review_id']),preview)

    def test_readonly_mode_refuses(self):
        self.start(); self.binding.mode='read-only'
        with self.assertRaisesRegex(CaptureRefused,'mode_blocks'):OperatorReviewBridge.from_inbox(self.inbox)


if __name__=='__main__':unittest.main(defaultTest='OperatorReview',verbosity=2)
