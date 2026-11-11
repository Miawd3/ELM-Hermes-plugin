"""Conservative, explicit profile-local ELM setup. Does not select a Hermes provider.

Use ``new`` for an absent store and ``adopt`` for an existing healthy store.
Existing ELM configuration is never overwritten, even by ``adopt``. To change
an existing binding, inspect it and use the separately documented operator CLI.
"""
from dataclasses import asdict
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sys

from elm_plugin.engine import ElmError, run_engine
from elm_plugin.storage import Binding, IDENTITY, MODES
from elm_plugin.token_budget import BUDGET_MODES, validate_settings, TokenCounter

CONFIGS = ("elm.json", "elm_episode_capture.json", "elm_episode_recall.json",
           "elm_batch_extraction.json", "elm_candidate_inbox.json", "elm_operator_review.json")


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("operation", choices=("new", "adopt"))
    p.add_argument("--hermes-home", required=True, help="Explicit absolute profile path")
    p.add_argument("--root", required=True, help="Explicit absolute store path")
    p.add_argument("--project", required=True)
    p.add_argument("--mode", choices=MODES, default="read-only")
    p.add_argument("--budget", type=int, default=700)
    p.add_argument("--budget-mode", choices=BUDGET_MODES, default="measured")
    p.add_argument("--tokenizer", choices=("cl100k_base", "o200k_base"))
    p.add_argument("--tokenizer-vocab", help="Absolute path to hash-verified local .tiktoken vocabulary")
    for flag in ("capture", "episode-recall", "marker-proposals", "batch-extraction", "inbox", "review-bridge"):
        p.add_argument("--" + flag, action="store_true", help="Explicit opt-in; no implicit dependencies")
    p.add_argument("--author-id", help="Stable trusted source author ID; not a display name")
    p.add_argument("--operator-id", help="Stable review operator ID")
    return p


def refuse(code, message):
    raise ElmError(code, message)


def absolute(raw):
    path = Path(raw)
    if not path.is_absolute() or ".." in path.parts:
        refuse("invalid_path", "Use an explicit absolute path without parent traversal")
    if any(item.is_symlink() for item in (path, *path.parents)):
        refuse("unsafe_path", "Setup refuses symlink paths and symlink ancestors")
    return path


def validate(args):
    home, root = absolute(args.hermes_home), absolute(args.root)
    validate_settings(args.budget_mode, args.tokenizer, args.tokenizer_vocab)
    if args.budget_mode == "measured":
        TokenCounter(args.tokenizer, args.tokenizer_vocab)
    if home == root or home in root.parents or root in home.parents:
        refuse("overlapping_paths", "Profile and store must be separate, non-nested paths")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", args.project):
        refuse("invalid_project", "Invalid project identifier")
    if not 200 <= args.budget <= 1200:
        refuse("invalid_budget", "Budget must be between 200 and 1200 in the selected accounting mode")
    if home.exists() and not home.is_dir():
        refuse("invalid_home", "Profile must be a directory")
    if any((home / name).exists() or (home / name).is_symlink() for name in CONFIGS):
        refuse("existing_config", "Existing ELM configuration is never overwritten; use a fresh profile or inspect it manually")
    if (home / ".elm-setup.lock").exists():
        refuse("setup_locked", "Another setup or an interrupted setup requires inspection")
    if args.episode_recall and args.budget < 256:
        refuse("invalid_recall_budget", "Episode recall requires budget at least 256")
    if args.operation == "new" and (root.exists() or root.is_symlink()):
        refuse("existing_root", "new requires an absent store path; use adopt for an existing store")
    if args.operation == "adopt" and not root.is_dir():
        refuse("missing_root", "adopt requires an existing store directory")
    dependencies = ((args.episode_recall, args.capture, "episode-recall requires capture"),
                    (args.marker_proposals, args.capture, "marker-proposals requires capture"),
                    (args.batch_extraction, args.episode_recall, "batch-extraction requires episode-recall"),
                    (args.inbox, args.batch_extraction, "inbox requires batch-extraction"),
                    (args.review_bridge, args.inbox, "review-bridge requires inbox"))
    for selected, dependency, reason in dependencies:
        if selected and not dependency:
            refuse("missing_opt_in", reason)
    if (args.marker_proposals or args.review_bridge) and args.mode == "read-only":
        refuse("read_only", "Marker proposals and review submission require explicit proposal-only or autonomous mode")
    if args.marker_proposals or args.batch_extraction:
        if not args.author_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", args.author_id):
            refuse("invalid_author", "A valid explicit author-id is required")
    elif args.author_id is not None:
        refuse("unused_author", "author-id requires marker-proposals or batch-extraction")
    if args.review_bridge:
        if not args.operator_id or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", args.operator_id):
            refuse("invalid_operator", "A valid explicit operator-id is required")
    elif args.operator_id is not None:
        refuse("unused_operator", "operator-id requires review-bridge")
    return home, root


def setup(args):
    home, root = validate(args)  # Complete argument checks before creating anything.
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = home / ".elm-setup.lock"
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        if any((home / name).exists() or (home / name).is_symlink() for name in CONFIGS):
            refuse("existing_config", "Existing ELM configuration is never overwritten")
        if args.operation == "new":
            # Engine init independently refuses an existing target.
            run_engine(home, root, "init", "--project", args.project)
        status = run_engine(home, root, "status", "--readiness-only")
        if not status.get("healthy") or not status.get("root_identity"):
            refuse("store_not_ready", "Store must be healthy and indexed before adoption")
        run_engine(home, root, "read", f"20_projects/{args.project}/PROJECT_HUB.md", "--document", "--project", args.project)
        binding = Binding(str(root), args.project, args.mode, args.budget,
                          status["root_identity"]["root_id"], hashlib.sha256((root / IDENTITY).read_bytes()).hexdigest(),
                          budget_mode=args.budget_mode, tokenizer=args.tokenizer, tokenizer_vocab=args.tokenizer_vocab)
        common = {"format_version": 1, "enabled": True, "root_id": binding.root_id, "project": binding.project}
        configs = {}
        if args.capture:
            configs[CONFIGS[1]] = {**common, "explicit_proposals": args.marker_proposals,
                                  "proposal_author_id": args.author_id if args.marker_proposals else None}
        if args.episode_recall:
            configs[CONFIGS[2]] = {**common, "budget": args.budget}
        if args.batch_extraction:
            configs[CONFIGS[3]] = {**common, "author_id": args.author_id}
        if args.inbox:
            configs[CONFIGS[4]] = {**common, "author_id": args.author_id}
        if args.review_bridge:
            configs[CONFIGS[5]] = {**common, "operator_id": args.operator_id}
        # Binding is committed last. Exclusive creation never replaces a config.
        configs[CONFIGS[0]] = {"format_version": 1, **asdict(binding), "recall_mode": "explicit-only"}
        for name, value in configs.items():
            with (home / name).open("x", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
        return {"status": "configured", "operation": args.operation, "binding": configs[CONFIGS[0]],
                "created_configs": list(configs), "hermes_config_modified": False,
                "provider_selection_posix_command": "HERMES_HOME=" + shlex.quote(str(home)) + " hermes config set memory.provider elm",
                "next_steps": ["Install this plugin as elm in this profile if not already installed.",
                               "Select elm as memory.provider in this profile's Hermes configuration, then start a new conversation.",
                               shlex.join([sys.executable, str(Path(__file__).with_name("manage.py")), "status", "--hermes-home", str(home)])],
                "limits": ["Read-only limits canonical mutations, not separately opted-in episode capture.",
                           "Optional capture retains scrubbed transcripts locally for up to 3 days; forgetting is not secure erasure.",
                           "Marker proposals are pending, not verified facts. No model extraction is installed.",
                           "Partial failures preserve created files/store for inspection; setup never deletes or rolls back data."]}
    finally:
        lock.unlink()


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        print(json.dumps(setup(args), ensure_ascii=False, indent=2))
        return 0
    except (ElmError, OSError) as exc:
        print(json.dumps({"error": getattr(exc, "code", "setup_io_failed"), "message": str(exc),
                          "recovery": "Inspect explicit paths before retrying. Existing files are never overwritten."}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
