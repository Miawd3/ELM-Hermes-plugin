"""Offline capture URI and persistent gap regressions. No host/model required."""
from dataclasses import dataclass
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from elm_plugin.episode_capture import EpisodeCapture, CaptureRefused, _safe_text, _GAP_LIMIT

@dataclass
class Binding:
    root_id: str = 'root_12345678-1234-4234-8234-123456789012'
    project: str = 'orion'
    def check_identity(self):
        pass

class CaptureURIRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='elm-uri-regression-')
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.binding = Binding()
        self.config = self.home / 'elm_episode_capture.json'
        self.config.write_text(json.dumps(dict(format_version=1, enabled=True,
                                              root_id=self.binding.root_id, project='orion')))
        self.capture = self.restart()

    def restart(self):
        capture, ready = EpisodeCapture.from_profile(self.home, self.binding, 'primary', clock=lambda: 1000.)
        self.assertEqual(ready, 'ready')
        return capture

    def append(self, number=1, user='Plain user text.', assistant='Plain assistant text.', history=None):
        pair = [dict(message_uid=f'u{number}', role='user', content=user),
                dict(message_uid=f'a{number}', role='assistant', content=assistant)]
        return self.capture.append_turn('session', user, assistant,
                                        messages=(history or []) + pair, turn_author=None)

    def test_ordinary_labels_preserved_for_both_speakers(self):
        labels = ['Metadata: project Juniper.', 'Here is the data: target 42.',
                  'Database metadata: migration 3.', 'DATA: version, 3.',
                  'const data: number = 42;', 'The data: field is optional.',
                  'metadata:image/png;base64, is a field label.']
        number = 0
        for label in labels:
            for side in ('user', 'assistant'):
                number += 1
                with self.subTest(label=label, side=side):
                    self.assertEqual(self.append(number, **{side: label})['captured_messages'], 2)
        with closing(sqlite3.connect(self.capture.path)) as con, con:
            texts = {r[0] for r in con.execute('SELECT text FROM messages')}
        self.assertTrue(set(labels).issubset(texts))
        self.assertEqual(self.capture.status()['capture_gaps']['known_refused_attempts'], 0)

    def test_real_data_uris_refused_for_both_speakers(self):
        uris = ['data:image/png;base64,U1lOVEhFVElD', 'DATA:IMAGE/PNG;BASE64,U1lOVEhFVElD',
                'data:,plain', 'data:;base64,U1lOVEhFVElD',
                'Look: (data:text/plain;charset=utf-8,hello)',
                '<img src="data:image/png;base64,U1lOVEhFVElD">',
                'url(data:image/svg+xml,%3Csvg%3E)',
                "data:text/plain;name=O'Reilly,SYNTHETIC",
                "data:application/x-foo'bar,SYNTHETIC",
                'data:text/plain;name=foo`bar,SYNTHETIC']
        for uri in uris:
            for side in ('user', 'assistant'):
                with self.subTest(uri=uri, side=side), self.assertRaisesRegex(CaptureRefused, 'inline_media_refused'):
                    self.append(**{side: uri})
        self.assertEqual(self.capture.status()['active_messages'], 0)
        self.assertEqual(self.capture.status()['capture_gaps']['known_refused_attempts'], 20)

    def test_gap_survives_success_seal_and_restart_without_source_text(self):
        secret = 'SYNTHETIC_REJECTED_PAYLOAD_928374'
        with self.assertRaises(CaptureRefused):
            self.append(user='data:text/plain,' + secret)
        self.append(2)
        self.capture.seal('session', 'session_end')
        self.capture = self.restart()
        gaps = self.capture.status()['capture_gaps']
        self.assertEqual(gaps['known_refused_attempts'], 1)
        self.assertEqual(gaps['last_reason'], 'inline_media_refused')
        self.assertFalse(gaps['complete_capture_certified'])
        self.assertNotIn(secret.encode(), self.capture.path.read_bytes())
        with closing(sqlite3.connect(self.capture.path)) as con, con:
            self.assertEqual(con.execute('SELECT count(*) FROM capture_gap_events').fetchone()[0], 1)

    def test_repeated_rejection_counts_attempts_not_unique_turns(self):
        for _ in range(2):
            with self.assertRaises(CaptureRefused): self.append(user='data:,synthetic')
        self.assertEqual(self.capture.status()['capture_gaps']['known_refused_attempts'], 2)

    def test_counter_saturates_and_does_not_grow_rows(self):
        with closing(sqlite3.connect(self.capture.path)) as con, con:
            con.execute('UPDATE capture_gap_events SET refused_attempts=?', (_GAP_LIMIT,))
        with self.assertRaises(CaptureRefused): self.append(user='data:,synthetic')
        gaps = self.capture.status()['capture_gaps']
        self.assertEqual(gaps['known_refused_attempts'], _GAP_LIMIT)
        self.assertTrue(gaps['counter_saturated'])

    def test_withdrawal_does_not_write_gap_state(self):
        before = self.capture.path.read_bytes()
        self.config.write_text(json.dumps({'enabled': False}))
        with self.assertRaises(CaptureRefused): self.append(user='data:,synthetic')
        self.assertEqual(before, self.capture.path.read_bytes())

    def test_new_table_adoption_never_claims_historical_completeness(self):
        self.append()
        with closing(sqlite3.connect(self.capture.path)) as con, con:
            con.execute('DROP TABLE capture_gap_events')
        self.capture = self.restart()
        self.assertEqual(self.capture.status()['active_messages'], 2)
        self.assertFalse(self.capture.status()['capture_gaps']['complete_capture_certified'])

    def test_missing_existing_gap_row_is_not_reset_on_restart(self):
        with closing(sqlite3.connect(self.capture.path)) as con, con:
            con.execute('DELETE FROM capture_gap_events')
        with self.assertRaises(CaptureRefused): self.append(user='data:,synthetic')
        self.assertTrue(self.capture._gap_recording_failed)
        with self.assertRaisesRegex(CaptureRefused, 'capture_gap_state_invalid'):
            self.restart()
        with closing(sqlite3.connect(self.capture.path)) as con, con:
            self.assertEqual(con.execute('SELECT count(*) FROM capture_gap_events').fetchone()[0], 0)

    def test_large_repeated_non_uris_are_bounded(self):
        text = 'data:' * 100000
        started = time.monotonic()
        self.assertEqual(_safe_text(text, 1048576), text)
        self.assertLess(time.monotonic() - started, 2)

    def test_failed_connection_setup_closes_real_database_handle(self):
        self.capture.path.write_bytes(b'not a SQLite database')
        real_connect = sqlite3.connect
        opened = []

        class ObservedConnection(sqlite3.Connection):
            explicitly_closed = False
            def close(self):
                self.explicitly_closed = True
                return super().close()

        def connect(*args, **kwargs):
            con = real_connect(*args, factory=ObservedConnection, **kwargs)
            opened.append(con)
            self.addCleanup(con.close)
            return con

        with patch('elm_plugin.episode_capture.sqlite3.connect', side_effect=connect):
            with self.assertRaises(sqlite3.DatabaseError):
                self.capture._connect()
        self.assertEqual(len(opened), 1)
        self.assertTrue(opened[0].explicitly_closed,
                        'SQLite connection escaped after PRAGMA setup failure')

    def test_existing_hidden_and_structured_content_still_refused(self):
        with self.assertRaisesRegex(CaptureRefused, 'non_plain_or_empty_text'):
            self.append(user=[{'type': 'text', 'text': 'Metadata: visible'}])
        rows = [dict(message_uid='u1', role='user', content='Metadata: visible', data_use='restricted'),
                dict(message_uid='a1', role='assistant', content='Plain')]
        with self.assertRaises(CaptureRefused):
            self.capture.append_turn('session', rows[0]['content'], rows[1]['content'], messages=rows)

if __name__ == '__main__': unittest.main()
