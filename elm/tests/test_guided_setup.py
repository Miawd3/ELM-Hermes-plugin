"""Safe guided setup contract; all test paths are disposable synthetic fixtures."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import setup_profile as guided
from elm_plugin.engine import ElmError
from elm_plugin.storage import load_binding
from elm_plugin.episode_capture import EpisodeCapture
from elm_plugin.episode_recall import EpisodeRecall
from elm_plugin.candidate_inbox import DurableCandidateInbox
from elm_plugin.operator_review import OperatorReviewBridge


class GuidedSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home, self.root = self.base / "profile", self.base / "store"

    def args(self, *extra, operation="new", home=None):
        return guided.parser().parse_args([operation, "--budget-mode", "legacy-estimate", "--hermes-home", str(home or self.home),
                                          "--root", str(self.root), "--project", "orion", *extra])

    def test_safe_defaults_and_repeat_no_overwrite(self):
        result = guided.setup(self.args())
        self.assertEqual(result["binding"]["mode"], "read-only")
        self.assertEqual(result["binding"]["recall_mode"], "explicit-only")
        self.assertEqual(result["created_configs"], ["elm.json"])
        before = (self.home / "elm.json").read_bytes()
        with self.assertRaisesRegex(ElmError, "never overwritten"):
            guided.setup(self.args())
        self.assertEqual(before, (self.home / "elm.json").read_bytes())
        self.assertFalse((self.home / "config.yaml").exists())

    def test_adopt_distinct_no_store_modification(self):
        guided.setup(self.args())
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        fresh = self.base / "second-profile"
        guided.setup(self.args(operation="adopt", home=fresh))
        after = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(load_binding(fresh), load_binding(self.home))

    def test_invalid_opt_ins_do_not_create_targets(self):
        cases = [("--episode-recall",), ("--marker-proposals",), ("--batch-extraction",),
                 ("--inbox",), ("--review-bridge",), ("--budget", "199"),
                 ("--capture", "--episode-recall", "--budget", "200"),
                 ("--author-id", "unused"), ("--operator-id", "unused"),
                 ("--capture", "--marker-proposals", "--author-id", "author"),
                 ("--capture", "--marker-proposals", "--mode", "proposal-only", "--author-id", "bad/id")]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ElmError):
                guided.setup(self.args(*case))
            self.assertFalse(self.home.exists())
            self.assertFalse(self.root.exists())

    def test_new_rejects_even_empty_existing_root(self):
        self.root.mkdir()
        with self.assertRaises(ElmError):
            guided.setup(self.args())
        self.assertFalse(self.home.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_adopt_requires_existing_store(self):
        with self.assertRaises(ElmError):
            guided.setup(self.args(operation="adopt"))
        self.assertFalse(self.home.exists())

    def test_optional_existing_config_refused(self):
        self.home.mkdir()
        file = self.home / "elm_episode_capture.json"
        file.write_text('{"enabled": false}')
        with self.assertRaises(ElmError):
            guided.setup(self.args())
        self.assertEqual(file.read_text(), '{"enabled": false}')
        self.assertFalse(self.root.exists())

    def test_relative_overlap_and_symlink_refused(self):
        args = self.args()
        args.hermes_home = "relative"
        with self.assertRaises(ElmError):
            guided.setup(args)
        args = self.args()
        args.root = str(self.home / "nested")
        with self.assertRaises(ElmError):
            guided.setup(args)
        self.home.symlink_to(self.base / "absent", target_is_directory=True)
        with self.assertRaises(ElmError):
            guided.setup(self.args())
        self.assertFalse(self.root.exists())

    def test_all_opt_ins_are_loadable(self):
        guided.setup(self.args("--mode", "proposal-only", "--capture", "--episode-recall",
                              "--marker-proposals", "--batch-extraction", "--inbox", "--review-bridge",
                              "--author-id", "synthetic_author", "--operator-id", "synthetic_operator"))
        binding = load_binding(self.home)
        capture, state = EpisodeCapture.from_profile(self.home, binding, "primary")
        self.assertEqual(state, "ready")
        recall, state = EpisodeRecall.from_capture(capture)
        self.assertEqual(state, "ready")
        inbox, state = DurableCandidateInbox.from_recall(recall)
        self.assertEqual(state, "ready")
        bridge, state = OperatorReviewBridge.from_inbox(inbox)
        self.assertEqual(state, "ready")
        self.assertIsNotNone(bridge)

    def test_failure_preserves_store_for_inspection(self):
        original = guided.run_engine
        def fail_after_init(home, root, command, *args):
            if command == "status":
                raise ElmError("injected_failure", "synthetic failure")
            return original(home, root, command, *args)
        with patch.object(guided, "run_engine", side_effect=fail_after_init), self.assertRaises(ElmError):
            guided.setup(self.args())
        self.assertTrue(self.root.is_dir())
        self.assertFalse((self.home / "elm.json").exists())
        self.assertFalse((self.home / ".elm-setup.lock").exists())


if __name__ == "__main__":
    unittest.main()
