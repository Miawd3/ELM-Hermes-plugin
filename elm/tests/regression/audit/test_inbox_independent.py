"""Independent synthetic attacks. Reuse setup helpers, never inherited tests."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
import sqlite3
import unittest
from contextlib import closing, redirect_stdout
from io import StringIO
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from test_candidate_inbox import DurableInbox
import review_candidates as cli
from elm_plugin.candidate_inbox import DurableCandidateInbox, CandidateInboxControl
from elm_plugin.episode_capture import CaptureRefused, EpisodeCapture
from elm_plugin.episode_forgetting import EpisodeForget
from elm_plugin import candidate_inbox_store as store

class IndependentInbox(unittest.TestCase):
    setUp = DurableInbox.setUp
    start = DurableInbox.start
    add_source = DurableInbox.add_source
    response = DurableInbox.response
    prepare = DurableInbox.prepare
    accept_span = DurableInbox.accept_span
    restart = DurableInbox.restart
    rows = DurableInbox.rows

    def mutate(self, sql, args=()):
        with closing(sqlite3.connect(self.capture.path)) as con, con:
            con.execute(sql, args)

    def test_parallel_bad_responses_cannot_overrun_or_reset_budget(self):
        self.start(); r = self.prepare()
        def attack(_):
            try: DurableCandidateInbox.from_recall(self.recall)[0].validate(r['batch_id'], '{')
            except CaptureRefused: return True
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertTrue(all(pool.map(attack, range(24))))
        self.restart()
        self.assertEqual((self.rows()[0]['state'], self.rows()[0]['attempts']), ('failed', 3))
        with self.assertRaises(CaptureRefused): self.accept_span(r)

    def test_cross_response_batch_replay_consumes_only_target_budget(self):
        self.start(); r = self.prepare(); s = self.inbox.prepare([r['sources'][0]['locator']], request_key='other')
        _, raw = self.accept_span(r)
        with self.assertRaises(CaptureRefused): self.inbox.validate(s['batch_id'], raw)
        by_id = {row['batch_id']: row for row in self.rows()}
        self.assertEqual(by_id[r['batch_id']]['state'], 'validated')
        self.assertEqual(by_id[s['batch_id']]['state'], 'pending')
        self.assertEqual(by_id[s['batch_id']]['attempts'], 1)

    def test_unicode_and_deep_json_bad_attempts_survive_restart(self):
        self.start(); r = self.prepare()
        for raw in ('\ud800', '['*9 + '0' + ']'*9, '{"x":1,"x":2}'):
            with self.assertRaises(CaptureRefused): self.inbox.validate(r['batch_id'], raw)
            self.restart()
        self.assertEqual(self.rows()[0]['attempts'], 3)

    def test_authenticated_storage_shape_attack_still_no_upgrade(self):
        self.start(); r = self.prepare(); self.accept_span(r)
        row = self.rows()[0]; values = json.loads(row['selections']); values[0]['accepted_memory'] = True
        row['selections'] = json.dumps(values)
        self.mutate('UPDATE span_candidate_inbox SET selections=?,record_digest=?', (row['selections'], store.digest(row)))
        with self.assertRaises(CaptureRefused): self.inbox.review(r['batch_id'])
        self.assertEqual(self.rows()[0]['state'], 'revoked')

    def test_digest_recomputed_negative_offsets_still_rejected(self):
        self.start(); r = self.prepare(); self.accept_span(r)
        row = self.rows()[0]; values = json.loads(row['selections']); values[0]['start'] = -2
        row['selections'] = json.dumps(values)
        self.mutate('UPDATE span_candidate_inbox SET selections=?,record_digest=?', (row['selections'], store.digest(row)))
        with self.assertRaises(CaptureRefused): self.inbox.review(r['batch_id'])
        self.assertEqual(self.rows()[0]['state'], 'revoked')

    def test_all_layer_optouts_durable_when_seen_by_handle(self):
        for name in ('elm_episode_capture.json', 'elm_episode_recall.json', 'elm_batch_extraction.json', 'elm_candidate_inbox.json'):
            with self.subTest(name=name):
                self.start(); r = self.prepare(key=name)
                file = self.home/name; old = file.read_bytes(); file.write_text('{"enabled":false}')
                with self.assertRaises(CaptureRefused): self.inbox.list_batches()
                file.write_bytes(old); self.restart()
                self.assertEqual(self.rows()[-1]['state'], 'revoked')

    def test_expired_review_does_not_wait_for_capture_sweep(self):
        self.start(retention_seconds=60); r = self.prepare(); self.accept_span(r)
        self.now += 60
        with self.assertRaises(CaptureRefused): self.inbox.review(r['batch_id'])
        self.assertEqual(self.rows()[0]['state'], 'revoked')
        self.now -= 60; self.restart()
        with self.assertRaises(CaptureRefused): self.inbox.prepare([r['sources'][0]['locator']], request_key='fixture')

    def test_backwards_clock_tombstones_instead_of_extending_life(self):
        self.start(); r = self.prepare(); self.now -= 1
        with self.assertRaises(CaptureRefused): self.inbox.validate(r['batch_id'], json.dumps(self.response(r)))
        self.assertEqual(self.rows()[0]['state'], 'revoked')

    def test_source_change_during_result_boundary_scrubs(self):
        self.start(); r = self.prepare(); self.accept_span(r)
        original = self.inbox.extractor._sources
        calls = [0]
        def changed(locators):
            result = original(locators); calls[0] += 1
            if calls[0] > 1: raise CaptureRefused('simulated_source_change')
            return result
        with patch.object(self.inbox.extractor, '_sources', changed):
            with self.assertRaises(CaptureRefused): self.inbox.review(r['batch_id'])
        self.assertEqual(self.rows()[0]['state'], 'revoked')

    def test_binding_change_at_commit_rolls_back_admission(self):
        self.start(); loc = self.add_source()
        with patch.object(self.inbox.control.owner, '_guard', side_effect=[None, CaptureRefused('binding_changed'), CaptureRefused('binding_changed')]):
            with self.assertRaises(CaptureRefused): self.inbox.prepare([loc], request_key='binding')
        self.assertEqual(self.rows(), [])

    def test_transient_binding_failure_must_not_commit_admission(self):
        self.start(); loc = self.add_source()
        with patch.object(self.inbox.control.owner, '_guard', side_effect=[None, CaptureRefused('binding_changed'), None]):
            with self.assertRaises(CaptureRefused): self.inbox.prepare([loc], request_key='transient-binding')
        self.assertEqual(self.rows(), [], 'Admission committed despite rejected commit-boundary guard')

    def test_cli_missing_profile_never_initializes(self):
        missing = self.home/'does-not-exist'
        with redirect_stdout(StringIO()) as output:
            code = cli.main(['--hermes-home', str(missing), '--root-id', self.binding.root_id,
                             '--project', self.binding.project, 'list'])
        self.assertEqual(code, 2); self.assertFalse(missing.exists())
        self.assertFalse(json.loads(output.getvalue())['contents_included'])

    def test_cli_optout_observation_revokes_existing_rows(self):
        for name in ('elm_batch_extraction.json', 'elm_candidate_inbox.json'):
            with self.subTest(name=name):
                self.start(); r = self.prepare(key='cli-'+name)
                path = self.home/name; old = path.read_bytes(); path.unlink()
                inspector = SimpleNamespace(home=self.home, binding=self.binding, capture_state='enabled',
                                            recall_state='enabled', batch_state='disabled' if name.startswith('elm_batch') else 'enabled')
                with patch.object(cli, 'EpisodeInspection', return_value=inspector), \
                     patch.object(cli, '_ExistingCapture', return_value=self.capture), redirect_stdout(StringIO()) as output:
                    code = cli.main(['--hermes-home', str(self.home), '--root-id', self.binding.root_id,
                                     '--project', self.binding.project, 'list'])
                self.assertEqual(code, 2)
                path.write_bytes(old); self.restart()
                row = next(row for row in self.rows() if row['batch_id'] == r['batch_id'])
                self.assertEqual(row['state'], 'revoked')

    def assert_permanent_block(self, locator):
        self.restart()
        for key in ('fixture', 'new-key-after-corruption'):
            with self.assertRaisesRegex(CaptureRefused, 'permanently_blocked'):
                self.inbox.prepare([locator], request_key=key)
        with closing(sqlite3.connect(self.capture.path)) as con:
            self.assertEqual(con.execute('SELECT count(*) FROM span_candidate_inbox').fetchone()[0], 0)
            self.assertTrue(con.execute("SELECT 1 FROM sqlite_master WHERE name='span_candidate_inbox_blocked'").fetchone())

    def test_corrupt_inbox_cannot_block_expiry_and_permanently_blocks_replay(self):
        self.start(retention_seconds=60); r = self.prepare(); self.accept_span(r)
        self.mutate("UPDATE span_candidate_inbox SET selections='corrupt'")
        self.now += 61
        with closing(sqlite3.connect(self.capture.path)) as con, con:
            EpisodeCapture._expire(con, self.now)
            self.assertEqual(con.execute('SELECT count(*) FROM messages').fetchone()[0], 0)
        self.assert_permanent_block(r['sources'][0]['locator'])

    def test_corrupt_forget_preview_readonly_stale_plan_refused_then_cleanup(self):
        self.start(); r = self.prepare(); self.accept_span(r)
        self.mutate("UPDATE span_candidate_inbox SET selections='corrupt'")
        forget = EpisodeForget(self.home, self.binding); loc = r['sources'][0]['locator']
        before = self.capture.path.read_bytes(); plan = forget.preview(loc)
        self.assertEqual(self.capture.path.read_bytes(), before)
        self.assertTrue(plan['corrupt_span_inbox_will_be_scrubbed_and_blocked'])
        self.mutate("UPDATE span_candidate_inbox SET selections='different-corruption'")
        with self.assertRaisesRegex(CaptureRefused, 'plan_changed'): forget.apply(loc, plan['plan_sha256'])
        self.assertEqual(len(self.recall._rows()), 2)
        current = forget.preview(loc); result = forget.apply(loc, current['plan_sha256'])
        self.assertEqual(result['local_span_inbox_batches_scrubbed'], 'all')
        self.assertEqual(len(self.recall._rows()), 0)
        self.assert_permanent_block(loc)

    def test_revoke_all_scrubs_corrupt_inbox_without_other_optins(self):
        self.start(); r = self.prepare(); self.accept_span(r)
        self.mutate("UPDATE span_candidate_inbox SET selections='corrupt'")
        config = self.home/'elm_candidate_inbox.json'; old = config.read_bytes(); config.unlink()
        result = CandidateInboxControl(self.home, self.binding).revoke()
        self.assertTrue(result['inbox_permanently_blocked'])
        config.write_bytes(old)
        self.assert_permanent_block(r['sources'][0]['locator'])
        self.assertEqual(len(self.recall._rows()), 2)

if __name__ == '__main__': unittest.main(defaultTest='IndependentInbox', verbosity=2)
