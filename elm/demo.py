"""Offline synthetic evidence demo. No model, network service or Hermes required.

All profile and store writes use an automatically removed temporary directory.
Queries are scripted. Output is retrieved evidence, NOT generated AI answers.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from elm_plugin.storage import load_binding, atomic_json
from elm_plugin.episode_capture import EpisodeCapture, CaptureRefused
from elm_plugin.episode_recall import EpisodeRecall
from elm_plugin.candidate_inbox import DurableCandidateInbox
from elm_plugin.operator_review import OperatorReviewBridge


def document(project, text):
    return (f"Title: {project} release decisions\nScope: {project} only\nTags: deployment, {project}\n"
            f"Status: active\nSummary: Synthetic release choices for {project}.\n\n"
            f"# {project} release decisions\n\n## Deployment\n\n{text}\n")


def run_demo():
    source = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="elm-offline-synthetic-") as temp:
        home, root = Path(temp) / "profile", Path(temp) / "store"
        def command(script, *args):
            env = {k: v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR"}}
            env.update(PYTHONDONTWRITEBYTECODE="1", HOME=temp, USERPROFILE=temp)
            result = subprocess.run([sys.executable, "-B", str(source / script), *args,
                                     "--hermes-home", str(home)], text=True, capture_output=True,
                                    timeout=60, env=env)
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
            return json.loads(result.stdout)
        setup = command("setup_profile.py", "new", "--budget-mode", "legacy-estimate", "--root", str(root), "--project", "orion",
                        "--capture", "--episode-recall", "--batch-extraction", "--inbox", "--author-id", "synthetic_author")
        (root / "20_projects/orion/DECISIONS.md").write_text(document("orion", "SYNTHETIC: Orion uses amber canaries and requires a signed rollback."), encoding="utf-8")
        foreign = root / "20_projects/lighthouse"
        foreign.mkdir()
        (foreign / "DECISIONS.md").write_text(document("lighthouse", "FOREIGN_PROJECT_SENTINEL: Lighthouse uses amber canaries without rollback."), encoding="utf-8")
        command("manage.py", "sync")
        before = command("manage.py", "context", "amber canaries signed rollback")
        # Each CLI call launches a fresh process and reloads the pinned binding.
        recalled = command("manage.py", "context", "amber canaries signed rollback")
        assert recalled == before, "Fresh-process retrieval changed"
        assert "signed rollback" in recalled["packet"] and "FOREIGN_PROJECT_SENTINEL" not in recalled["packet"]
        marker = "\n\nELM-DICT/1\n"
        if marker in recalled["packet"]:
            packet = json.loads(recalled["packet"].split(marker, 1)[1])
            locators = [packet["prefixes"].get("source", "") + row["source"] for row in packet["sources"]]
        else:
            locators = re.findall(r"(?m)^source: (elm://section/section_[0-9a-f-]+)$", recalled["packet"])
        assert locators, "No exact locators returned"
        expanded = [command("manage.py", "read", locator) for locator in locators]
        matching = [row for row in expanded if "signed rollback" in row.get("text", "")]
        assert matching and all("FOREIGN_PROJECT_SENTINEL" not in row.get("text", "") for row in expanded)
        binding = load_binding(home)
        capture, _ = EpisodeCapture.from_profile(home, binding, "primary")
        recall, _ = EpisodeRecall.from_capture(capture)
        inbox, _ = DurableCandidateInbox.from_recall(recall)
        # Deliberately attempt bridge admission against read-only policy. This is
        # an operator-layer guard, not a substitute for native elm_note tests.
        atomic_json(home / "elm_operator_review.json", {"format_version": 1, "enabled": True,
                    "root_id": binding.root_id, "project": binding.project, "operator_id": "synthetic_operator"})
        try:
            OperatorReviewBridge.from_inbox(inbox)
        except CaptureRefused as exc:
            blocked = str(exc)
        else:
            raise AssertionError("Read-only review bridge was admitted")
        assert blocked == "operator_review_mode_blocks_submission", blocked
        return {"status": "PASS", "synthetic_only": True, "model_calls": 0, "ai_answer_generated": False,
                "hermes_required": False, "live_profile_modified": False,
                "checks": ["guided_setup", "explicit_only_default", "fresh_process_restart", "project_scope",
                           "exact_source_expansion", "read_only_operator_review_admission_rejected"],
                "mode": binding.mode, "recall_mode": setup["binding"]["recall_mode"],
                "context_result": recalled, "exact_source_result": matching[0], "blocked_review": blocked,
                "limits": ["Synthetic retrieval evidence, not AI answers or answer-quality evidence.",
                           "Query and operation choices are scripted; no model tool selection is tested.",
                           "Native provider discovery, elm_note and automatic recall require the separate Hermes harness.",
                           "Optional configuration is exercised, not episode extraction or review submission."]}


if __name__ == "__main__":
    print(json.dumps(run_demo(), ensure_ascii=False, indent=2))
