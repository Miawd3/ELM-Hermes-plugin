import json
from pathlib import Path
import subprocess
import sys
import unittest


class OfflineDemoTests(unittest.TestCase):
    def test_runs_without_hermes(self):
        source = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, "-B", str(source / "demo.py")], text=True,
                                capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value["status"], "PASS")
        self.assertTrue(value["synthetic_only"])
        self.assertFalse(value["ai_answer_generated"])
        self.assertFalse(value["hermes_required"])
        self.assertEqual(value["model_calls"], 0)
        self.assertEqual(value["recall_mode"], "explicit-only")
        self.assertEqual(value["blocked_review"], "operator_review_mode_blocks_submission")


if __name__ == "__main__":
    unittest.main()
