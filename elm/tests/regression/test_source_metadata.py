"""Optional source metadata, separate provenance/authority, and native host transport."""
from contextlib import closing
import hashlib
import json
import sqlite3
import unittest

from test_episode_capture import CaptureCore, RealProviderHooks, pair, config
from elm_plugin.episode_capture import EpisodeCapture, CaptureRefused


def observed(number=1, stamp="2026-10-20T11:00:00+01:00"):
    rows = pair(number, user="Remember: equipment = brass compass")
    for row, speaker in zip(rows, ("human1", "assistant1")):
        row.update(speaker_id=speaker, timestamp=stamp)
    return rows


def read(capture, table="messages"):
    with closing(sqlite3.connect(capture.path)) as con:
        con.row_factory = sqlite3.Row
        return [dict(row) for row in con.execute("SELECT * FROM " + table + " ORDER BY rowid")]


class MetadataCore(CaptureCore):
    def test_missing_metadata_stays_unknown(self):
        capture = self.start()
        self.append(capture, turn_author={"id": "human1", "is_bot": False})
        rows = read(capture)
        self.assertTrue(all(r["source_timestamp"] is None and r["source_speaker_id"] is None for r in rows))
        self.assertEqual([r["author_id"] for r in rows], ["human1", None])

    def test_exact_source_time_and_speaker_survive_restart(self):
        capture = self.start()
        rows = observed()
        self.append(capture, rows, turn_author={"id": "human1", "is_bot": False})
        restarted, _ = EpisodeCapture.from_profile(self.home, self.binding, "primary", clock=lambda: self.now)
        actual = read(restarted)
        self.assertEqual([r["source_speaker_id"] for r in actual], ["human1", "assistant1"])
        self.assertEqual([r["source_timestamp"] for r in actual], [rows[0]["timestamp"]] * 2)
        self.assertTrue(all(r["captured"] == self.now for r in actual))
        self.assertEqual(self.append(restarted, rows)["status"], "duplicate")

    def test_numeric_host_times_preserve_number_and_unit(self):
        capture = self.start()
        for number, stamp in enumerate((1792490400, 1792490400.125, 0, -1.5), 1):
            self.append(capture, observed(number, stamp))
        actual = read(capture)
        for index, stamp in enumerate((1792490400, 1792490400.125, 0, -1.5)):
            self.assertEqual(actual[index * 2]["source_timestamp"], stamp)
            self.assertIs(type(actual[index * 2]["source_timestamp"]), type(stamp))

    def test_invalid_metadata_rejects_pair_atomically(self):
        capture = self.start()
        for stamp in (True, float("nan"), float("inf"), 10**1000, "2026-10-20T10:00:00", "2026-02-30T00:00:00Z", "yesterday", {}, "2026-10-20T10:00:00+25:00"):
            with self.subTest(stamp=str(stamp)[:40]):
                with self.assertRaisesRegex(CaptureRefused, "invalid_source_timestamp"):
                    self.append(capture, observed(stamp=stamp))
        for speaker in (False, "", "bad identity", {"id": "assistant1"}, "x" * 129):
            rows = observed(); rows[1]["speaker_id"] = speaker
            with self.assertRaisesRegex(CaptureRefused, "invalid_source_speaker_id"):
                self.append(capture, rows)
        self.assertEqual(read(capture), [])

    def test_metadata_speaker_never_confers_proposal_authority(self):
        capture = self.start(explicit_proposals=True, proposal_author_id="human1")
        self.append(capture, observed())
        capture.seal("s1", "session_end"); capture.prepare_batches()
        self.assertEqual(capture.proposal_snapshot()["records"], [])
        self.assertTrue(all(r["author_id"] is None for r in read(capture)))

    def test_user_observation_cannot_disagree_with_caller(self):
        capture = self.start()
        with self.assertRaisesRegex(CaptureRefused, "source_speaker_author_mismatch"):
            self.append(capture, observed(), turn_author={"id": "human2", "is_bot": False})
        self.assertEqual(read(capture), [])

    def test_uid_metadata_changes_refused_before_and_after_expiry(self):
        capture = self.start(retention_seconds=60)
        self.append(capture, observed())
        for expiry in (False, True):
            if expiry:
                self.now += 61; capture.seal("s1", "session_end")
            for field, value in (("speaker_id", "assistant2"), ("timestamp", "2026-10-20T10:00:00Z"), ("timestamp", None)):
                rows = observed(); rows[1][field] = value
                with self.assertRaisesRegex(CaptureRefused, "message_identity_conflict"):
                    self.append(capture, rows)
        self.assertEqual(len(read(capture, "seen")), 2)
        self.assertEqual(read(capture), [])

    def test_unknown_metadata_cannot_be_silently_enriched_on_replay(self):
        capture = self.start()
        rows = observed(); unknown = [dict(r) for r in rows]
        for row in unknown:
            row.pop("timestamp"); row.pop("speaker_id")
        self.append(capture, unknown)
        with self.assertRaisesRegex(CaptureRefused, "message_identity_conflict"):
            self.append(capture, rows)
        self.assertTrue(all(r["source_timestamp"] is None for r in read(capture)))

    def test_proposal_provenance_preserves_time_without_semantic_resolution(self):
        capture = self.start(explicit_proposals=True, proposal_author_id="human1")
        self.append(capture, observed(), turn_author={"id": "human1", "is_bot": False})
        capture.seal("s1", "session_end"); capture.prepare_batches()
        record = capture.proposal_snapshot()["records"][0]
        evidence = record["evidence"]
        self.assertEqual(evidence["source_timestamp"], observed()[0]["timestamp"])
        self.assertEqual(evidence["source_speaker_id"], "human1")
        self.assertEqual(evidence["captured_at"], self.now)
        self.assertFalse(evidence["is_authorization"])
        self.assertEqual(evidence["valid_from_basis"], "capture_time_placeholder_not_fact_validity")
        self.assertEqual(record["status"], "queued")

    def test_legacy_schema_refusal_does_not_modify_database(self):
        capture = self.start()
        self.append(capture)
        with closing(sqlite3.connect(capture.path)) as con, con:
            con.execute("UPDATE meta SET value='1' WHERE key='schema_version'")
        before = hashlib.sha256(capture.path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(CaptureRefused, "stored_scope_or_schema_mismatch"):
            EpisodeCapture.from_profile(self.home, self.binding, "primary", clock=lambda: self.now)
        self.assertEqual(before, hashlib.sha256(capture.path.read_bytes()).hexdigest())


class MetadataNative(RealProviderHooks):
    def test_real_manager_preserves_optional_metadata_without_granting_authority(self):
        provider, manager = self.provider()
        rows = observed(stamp=1792490400.125)
        manager.sync_all(rows[0]["content"], rows[1]["content"], session_id="session1", messages=rows)
        self.assertTrue(manager.flush_pending(timeout=10))
        actual = read(provider._episode_capture)
        self.assertEqual([r["source_speaker_id"] for r in actual], ["human1", "assistant1"])
        self.assertEqual([r["source_timestamp"] for r in actual], [1792490400.125] * 2)
        self.assertEqual([r["author_id"] for r in actual], [None, None])


if __name__ == "__main__":
    suite = unittest.TestSuite()
    for cls in (MetadataCore, MetadataNative):
        for name in cls.__dict__:
            if name.startswith("test_"): suite.addTest(cls(name))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
