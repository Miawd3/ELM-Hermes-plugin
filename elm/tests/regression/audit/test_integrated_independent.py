"""Independent synthetic lifecycle boundary tests; no network or host mutation."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import unittest

AREA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AREA))
from test_episode_inspect import InspectContract, fingerprint
from elm_plugin.episode_capture import EpisodeCapture, CaptureRefused
from elm_plugin.episode_forgetting import EpisodeForget

class IntegratedIndependent(unittest.TestCase):
    setUp = InspectContract.setUp
    write_config = InspectContract.write_config
    inspect = InspectContract.inspect
    populate = InspectContract.populate

    def submit(self, result_status='pending'):
        row = self.capture.next_proposal()
        self.assertNotIn('blocked', row)
        self.capture.finish_proposal(row['submission_id'], result={
            'canonical_committed': True, 'status': result_status,
            'untrusted_result': 'sensitive_unique_marker'})
        return row['submission_id']

    def test_submitted_pending_and_accepted_are_visible_but_unchecked(self):
        for outcome in ('pending', 'accepted'):
            with self.subTest(outcome=outcome):
                # Fresh independent disposable profile per outcome.
                if hasattr(self, 'capture'):
                    self.tmp.cleanup(); self.setUp()
                self.populate(); sid = self.submit(outcome)
                before = fingerprint(self.base)
                result = self.inspect().candidates()
                self.assertEqual([r['candidate_id'] for r in result['records']], [sid])
                row = result['records'][0]
                self.assertFalse(row['accepted_memory'])
                self.assertEqual(row['governance_outcome'], 'not_checked')
                self.assertNotIn('sensitive_unique_marker', json.dumps(result))
                counts = self.inspect().status()['counts']
                self.assertEqual(counts['pending_local_candidates'], 0)
                self.assertEqual(counts['reviewable_local_candidates'], 1)
                self.assertEqual(counts['submitted_governance_outcome_unchecked'], 1)
                self.assertEqual(before, fingerprint(self.base))

    def test_restart_preserves_submitted_and_does_not_retry(self):
        self.populate(); sid = self.submit()
        restarted, _ = EpisodeCapture.from_profile(self.home, self.binding, 'primary', clock=lambda:self.now)
        self.assertIsNone(restarted.next_proposal())
        self.assertEqual(self.inspect().candidates()['records'][0]['candidate_id'], sid)

    def test_expired_submitted_stays_visible_without_payload_fallback(self):
        self.populate(); self.submit(); self.now += 61
        before = fingerprint(self.base)
        record = self.inspect().candidates()['records'][0]
        self.assertEqual(record['citation_status'], 'unavailable_expired_missing_or_unlinked')
        with self.assertRaisesRegex(CaptureRefused, 'source_unavailable'):
            self.inspect().evidence(self.locator, include_source_text=True)
        self.assertEqual(before, fingerprint(self.base))

    def test_submitted_forgetting_is_hidden_by_default_and_tombstoned(self):
        self.populate(); self.submit()
        forget = EpisodeForget(self.home, self.binding)
        preview = forget.preview(self.locator)
        self.assertTrue(preview['external_outcome_review_required'])
        forget.apply(self.locator, preview['plan_sha256'])
        self.assertEqual(self.inspect().candidates()['records'], [])
        row = self.inspect().candidates(include_resolved=True)['records'][0]
        self.assertEqual(row['local_queue_state'], 'revoked_submitted')
        self.assertEqual(row['citation_status'], 'revoked_local_evidence')
        raw = self.capture.proposal_snapshot()['records'][0]
        self.assertEqual(raw['payload'], {}); self.assertEqual(raw['evidence'], {})
        self.assertIsNone(raw['result'])

    def test_unknown_forgetting_remains_reviewable_and_blocks_redispatch(self):
        self.populate(count=2)
        row = self.capture.next_proposal()
        self.capture.finish_proposal(row['submission_id'], error_code='uncertain_outcome')
        forget = EpisodeForget(self.home, self.binding)
        plan = forget.preview(self.locator)
        forget.apply(self.locator, plan['plan_sha256'])
        records = self.inspect().candidates()['records']
        self.assertEqual(len(records), 2)
        revoked = next(r for r in records if r['candidate_id'] == row['submission_id'])
        self.assertEqual(revoked['local_queue_state'], 'revoked_unknown')
        self.assertEqual(revoked['citation_status'], 'revoked_local_evidence')
        self.assertEqual(self.capture.next_proposal()['error_code'], 'unresolved_previous_submission')

    def test_late_success_after_forget_does_not_restore_copies(self):
        self.populate(); row = self.capture.next_proposal()
        forget = EpisodeForget(self.home, self.binding)
        forget.apply(self.locator, forget.preview(self.locator)['plan_sha256'])
        status = self.capture.finish_proposal(row['submission_id'], result={
            'canonical_committed': True, 'status':'pending', 'body':'sensitive_unique_marker'})
        self.assertEqual(status, 'revoked_submitted')
        self.assertEqual(self.inspect().candidates()['records'], [])
        raw = self.capture.proposal_snapshot()['records'][0]
        self.assertEqual(raw['payload'], {}); self.assertEqual(raw['evidence'], {})
        self.assertIsNone(raw['result'])

    def test_stale_preview_after_submission_refuses_without_changes(self):
        self.populate(); forget = EpisodeForget(self.home, self.binding)
        plan = forget.preview(self.locator); self.submit()
        before = fingerprint(self.base)
        with self.assertRaisesRegex(CaptureRefused, 'forget_plan_changed'):
            forget.apply(self.locator, plan['plan_sha256'])
        self.assertEqual(before, fingerprint(self.base))

if __name__ == '__main__':
    unittest.main(defaultTest='IntegratedIndependent', verbosity=2)
