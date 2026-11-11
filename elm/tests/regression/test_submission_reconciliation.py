"""Synthetic canonical observations, without a disposable SQLite projection."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch
import test_operator_review as fixtures
from elm_plugin.engine import ElmError
from elm_plugin.episode_capture import CaptureRefused
from elm_plugin.operator_review import ReviewBridgeControl
from elm_plugin import operator_review_store as store

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'engine'))
from elm_memory.governance import submit_proposal_bundle, ProposalLimits, load_governance


class Reconciliation(unittest.TestCase):
    setUp = fixtures.OperatorReview.setUp
    add_source = fixtures.OperatorReview.add_source
    response = fixtures.OperatorReview.response
    accept_span = fixtures.OperatorReview.accept_span
    restart_inbox = fixtures.OperatorReview.restart_inbox
    restart = fixtures.OperatorReview.restart
    prepare = fixtures.OperatorReview.prepare
    rows = fixtures.OperatorReview.rows
    semantics = fixtures.OperatorReview.semantics

    def start(self, **kwargs):
        fixtures.OperatorReview.start(self, **kwargs)
        self.root = self.binding.path
        for path in ('00_registry', '.elm', '20_projects/orion'):
            (self.root / path).mkdir(parents=True, exist_ok=True)
        identity = self.root / '00_registry/ELM_ROOT_ID.json'
        identity.write_text(json.dumps({'format_version': 1, 'record_type': 'root_identity',
            'root_id': self.binding.root_id, 'created_at': '2026-11-06T00:00:00Z', 'creator': 'synthetic-test'}))
        self.binding.identity_sha256 = hashlib.sha256(identity.read_bytes()).hexdigest()

    def digest(self):
        return {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.root.rglob('*') if p.is_file()}

    def submit_canonical(self, payload):
        return submit_proposal_bundle(self.root, request=payload, request_bytes=len(json.dumps(payload).encode()),
            allowed_projects={'orion'}, limits=ProposalLimits(), lock_timeout=1, recover_stale=False)

    def uncertain(self, preview, commit=False):
        def dispatch(*args, request=None):
            if commit: self.submit_canonical(request)
            raise ElmError('synthetic_lost_response', 'unknown')
        with patch('elm_plugin.operator_review.run_engine', side_effect=dispatch) as spy:
            value = self.bridge.submit(preview['review_id'], preview['plan_sha256'], confirm=True)
            self.assertEqual(value['state'], 'unknown'); self.assertEqual(spy.call_count, 1)

    def reconcile(self, preview):
        return self.bridge.reconcile(preview['review_id'], preview['plan_sha256'])

    def test_match_lost_response_restart_and_replay_no_write(self):
        self.start(); preview = self.prepare(); self.uncertain(preview, commit=True); before = self.digest()
        self.restart()
        with patch('elm_plugin.operator_review.run_engine') as spy:
            result = self.reconcile(preview)
            self.assertEqual(result['state'], 'submitted')
            self.assertEqual(result['reconciliation']['classification'], 'matched')
            self.assertEqual(result['reconciliation']['observed_canonical_status'], 'pending')
            self.assertFalse(result['accepted_memory']); self.assertFalse(result['acceptance_performed'])
            self.assertFalse(result['submission_performed']); self.assertFalse(result['retry_permitted'])
            self.restart(); self.reconcile(preview)
            self.bridge.submit(preview['review_id'], preview['plan_sha256'], confirm=True)
            spy.assert_not_called()
        self.assertEqual(self.digest(), before)
        self.assertEqual(len(load_governance(self.root)[0]), 1)
        self.assertNotIn('not red', json.dumps(result))
        self.assertFalse((self.root / '.elm/index.sqlite').exists())

    def test_absent_stays_uncertain_and_blocks_new_intent(self):
        self.start(); preview = self.prepare(); self.uncertain(preview); before = self.digest(); self.restart()
        result = self.reconcile(preview)
        self.assertEqual(result['reconciliation']['classification'], 'absent_uncertain')
        self.assertEqual(result['state'], 'unknown'); self.assertTrue(result['manual_outcome_review_required'])
        self.assertFalse(result['governance_submission_recorded'])
        with patch('elm_plugin.operator_review.run_engine') as spy:
            with self.assertRaises(CaptureRefused): self.bridge.submit(preview['review_id'],preview['plan_sha256'],confirm=True)
            with self.assertRaises(CaptureRefused): self.bridge.prepare(self.batch_id,self.candidate_id,self.semantics(),request_key='other')
            spy.assert_not_called()
        self.assertEqual(self.digest(), before)

    def test_delayed_commit_after_absence_can_later_match(self):
        self.start(); preview = self.prepare(); self.uncertain(preview)
        self.assertEqual(self.reconcile(preview)['reconciliation']['classification'], 'absent_uncertain')
        self.submit_canonical(preview['proposal_payload'])
        self.assertEqual(self.reconcile(preview)['reconciliation']['classification'], 'matched')
        self.assertEqual(len(load_governance(self.root)[0]), 1)

    def test_same_id_different_payload_conflict_never_unblocks(self):
        self.start(); preview = self.prepare(); self.uncertain(preview)
        changed = copy.deepcopy(preview['proposal_payload']); changed['object'] = 'synthetic other meaning'
        self.submit_canonical(changed); before = self.digest()
        result = self.reconcile(preview)
        self.assertEqual(result['reconciliation']['classification'], 'conflict')
        self.assertEqual(result['reconciliation']['reason'], 'payload_digest_mismatch')
        self.assertEqual(result['state'], 'unknown'); self.assertFalse(result['acceptance_observed_in_governance'])
        self.assertEqual(self.digest(), before)

    def test_prepared_or_wrong_plan_cannot_be_promoted(self):
        self.start(); preview = self.prepare(); self.submit_canonical(preview['proposal_payload'])
        with self.assertRaisesRegex(CaptureRefused, 'intent_unavailable'): self.reconcile(preview)
        self.uncertain(preview)
        with self.assertRaisesRegex(CaptureRefused, 'plan_changed'): self.bridge.reconcile(preview['review_id'],'0'*64)
        self.assertEqual(self.rows()[0]['state'],'unknown')

    def test_scrubbed_review_not_matched_by_id_alone(self):
        self.start(); preview = self.prepare(); self.uncertain(preview, commit=True)
        ReviewBridgeControl(self.home,self.binding).revoke(preview['review_id'])
        with patch('elm_plugin.operator_review.observe_submission') as spy:
            with self.assertRaisesRegex(CaptureRefused, 'unavailable'): self.reconcile(preview)
            spy.assert_not_called()
        self.assertEqual(self.rows()[0]['state'],'revoked_unknown')

    def test_expiry_and_source_mutation_stay_revoked_unknown(self):
        for changed in (False, True):
            with self.subTest(source_mutated=changed):
                # Independent complete fixtures for each mutation.
                case=Reconciliation(); case.setUp()
                try:
                    case.start(); preview=case.prepare(); case.uncertain(preview,commit=True)
                    if changed:
                        with closing(sqlite3.connect(case.capture.path)) as con,con:
                            con.execute("UPDATE messages SET text='changed' WHERE uid='u1'")
                    else: case.now += 86401
                    with self.assertRaises(CaptureRefused): case.reconcile(preview)
                    self.assertEqual(case.rows()[0]['state'],'revoked_unknown')
                finally: case.doCleanups()

    def test_canonical_corruption_is_unavailable_not_match(self):
        self.start(); preview=self.prepare(); self.uncertain(preview,commit=True)
        p=next((self.root/'01_inbox/elm_proposals').rglob('proposal_*.json')); p.write_text('{}')
        result=self.reconcile(preview)
        self.assertEqual(result['reconciliation']['classification'],'unavailable')
        self.assertEqual(result['state'],'unknown')

    def test_identity_changed_inside_reader_blocks(self):
        self.start(); preview=self.prepare(); self.uncertain(preview,commit=True)
        p=self.root/'00_registry/ELM_ROOT_ID.json';p.write_text(p.read_text()+' ')
        # Unit fixture intentionally has a no-op Binding guard. The canonical
        # helper's own locked identity hash comparison still refuses the root.
        result=self.reconcile(preview)
        self.assertEqual(result['reconciliation']['reason'],'root_identity_mismatch')
        self.assertEqual(result['state'],'unknown')

    def test_malformed_helper_response_never_changes_local_state(self):
        self.start(); preview=self.prepare();self.uncertain(preview)
        with patch('elm_plugin.submission_reconciliation.subprocess.run',return_value=subprocess.CompletedProcess([],0,'{"classification":"matched"}','')):
            with self.assertRaises(ElmError):self.reconcile(preview)
        self.assertEqual(self.rows()[0]['state'],'unknown')

    def test_concurrent_reconciliation_serializes_without_duplicate(self):
        self.start(); preview=self.prepare();self.uncertain(preview,commit=True);before=self.digest()
        with ThreadPoolExecutor(max_workers=4) as pool:
            values=list(pool.map(lambda _:self.reconcile(preview),range(8)))
        self.assertTrue(all(v['state']=='submitted' and v['reconciliation']['classification']=='matched' for v in values))
        self.assertEqual(self.digest(),before);self.assertEqual(len(load_governance(self.root)[0]),1)


if __name__ == '__main__': unittest.main(verbosity=2)
