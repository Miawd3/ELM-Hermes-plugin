from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_episode_capture import CaptureCore, pair
from test_source_metadata import read
from elm_plugin.episode_capture import CaptureRefused

class IndependentBoundary(CaptureCore):
    def test_invalid_offset_minutes(self):
        cap=self.start()
        for i,suffix in enumerate(('+00:60','-00:99','+12:75'),1):
            with self.subTest(suffix=suffix):
                rows=pair(i); rows[0]['timestamp']='2026-01-01T12:00:00'+suffix
                with self.assertRaisesRegex(CaptureRefused,'invalid_source_timestamp'):
                    self.append(cap,rows)
    def test_numeric_type_change_conflicts(self):
        cap=self.start(); rows=pair(); rows[0]['timestamp']=1
        self.append(cap,rows); rows[0]['timestamp']=1.0
        with self.assertRaisesRegex(CaptureRefused,'message_identity_conflict'):
            self.append(cap,rows)
    def test_exact_offset_and_fraction_text(self):
        cap=self.start(); rows=pair()
        rows[0]['timestamp']='2026-01-01T12:00:00.120000+05:45'
        rows[1]['timestamp']='2026-01-01T12:00:00-00:00'
        self.append(cap,rows)
        self.assertEqual([r['source_timestamp'] for r in read(cap)],[r['timestamp'] for r in rows])
    def test_assistant_speaker_does_not_authorize(self):
        cap=self.start(explicit_proposals=True,proposal_author_id='human1')
        rows=pair(user='Remember: equipment = compass'); rows[1]['speaker_id']='human1'
        self.append(cap,rows); cap.seal('s1','session_end'); cap.prepare_batches()
        self.assertEqual(cap.proposal_snapshot()['records'],[])
        self.assertTrue(all(r['author_id'] is None for r in read(cap)))
    def test_bad_second_row_atomic(self):
        cap=self.start(); rows=pair(); rows[1]['timestamp']=False
        with self.assertRaises(CaptureRefused): self.append(cap,rows)
        self.assertEqual(read(cap),[]); self.assertEqual(read(cap,'seen'),[])

if __name__=='__main__':
    suite=unittest.TestSuite(IndependentBoundary(n) for n in IndependentBoundary.__dict__ if n.startswith('test_'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
