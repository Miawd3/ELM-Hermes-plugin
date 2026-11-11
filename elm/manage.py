"""Explicit operator-only store setup and maintenance; no Hermes imports needed."""
from dataclasses import asdict
import argparse
import json
import sqlite3
from pathlib import Path

from elm_plugin.engine import ElmError, run_engine
from elm_plugin.storage import adopt, load_binding, MODES, RECALL_MODES
from elm_plugin.token_budget import BUDGET_MODES, validate_settings, TokenCounter
from elm_plugin.measured_context import measured_context, legacy_accounting
from elm_plugin.episode_forgetting import EpisodeForget
from elm_plugin.episode_capture import CaptureRefused


def main(argv=None):
    parser = argparse.ArgumentParser(description="ELM operator helper. Never auto-adopts cwd or a user's live ELM.")
    sub = parser.add_subparsers(dest="operation", required=True)
    for name in ("init", "adopt", "status", "context", "read", "sync", "doctor", "history", "episode-forget-preview", "episode-forget"):
        command = sub.add_parser(name)
        command.add_argument("--hermes-home", required=True, help="Explicit profile home; not inferred from cwd")
        if name in {"init", "adopt"}:
            command.add_argument("--root", required=True)
            command.add_argument("--project", required=True)
            command.add_argument("--mode", choices=MODES, default="read-only")
            command.add_argument("--recall-mode", choices=RECALL_MODES, default="explicit-only",
                                 help="Default: explicit tools only. Legacy background mode risks authoritative host treatment of untrusted evidence.")
            command.add_argument("--budget", type=int, default=700)
            command.add_argument("--budget-mode", choices=BUDGET_MODES, default="measured")
            command.add_argument("--tokenizer", choices=("cl100k_base", "o200k_base"))
            command.add_argument("--tokenizer-vocab")
        if name in {"episode-forget-preview", "episode-forget"}:
            command.add_argument("--locator", required=True, help="Exact scoped source locator from episode recall")
            if name == "episode-forget":
                command.add_argument("--confirm-plan", required=True, help="Exact plan_sha256 from reviewed preview")
        if name == "context":
            command.add_argument("query")
        if name == "read":
            command.add_argument("section")
            command.add_argument("--document", action="store_true")
    args = parser.parse_args(argv)
    try:
        home = Path(args.hermes_home).expanduser()
        if not home.is_absolute():
            raise ElmError("invalid_home", "Profile home must be absolute")
        home = home.resolve()
        if args.operation in {"init", "adopt"}:
            validate_settings(args.budget_mode, args.tokenizer, args.tokenizer_vocab)
            if args.budget_mode == "measured":
                TokenCounter(args.tokenizer, args.tokenizer_vocab)
            home.mkdir(parents=True, exist_ok=True)
            root = Path(args.root).expanduser()
            if not root.is_absolute():
                raise ElmError("invalid_root", "Root must be absolute")
            if args.operation == "init":
                run_engine(home, root, "init", "--project", args.project)
                doctor = run_engine(home, root, "doctor", "--no-sync")
                if doctor["issues"]:
                    raise ElmError("init_doctor_failed", "Store created but not adopted: doctor reports issues", result=doctor)
            result = asdict(adopt(home, vars(args)))
        else:
            binding = load_binding(home)
            root = binding.path
            if args.operation in {"episode-forget-preview", "episode-forget"}:
                forget = EpisodeForget(home, binding)
                result = (forget.preview(args.locator) if args.operation == "episode-forget-preview"
                          else forget.apply(args.locator, args.confirm_plan))
            elif args.operation == "status":
                result = {**run_engine(home, root, "status", "--readiness-only"),
                          "project": binding.project, "mode": binding.mode, "automatic_learning": False,
                          "recall_mode": binding.recall_mode, "budget_mode": binding.budget_mode,
                          "tokenizer": binding.tokenizer,
                          "automatic_recall_configured": binding.recall_mode == "legacy-background",
                          "automatic_recall": binding.recall_mode == "legacy-background" and binding.budget_mode == "legacy-estimate"}
            elif args.operation == "context":
                if not args.query.strip():
                    raise ElmError("no_query", "Empty query: no recall performed")
                if binding.budget_mode == "measured":
                    print(measured_context(home, binding, args.query)["wire"], end="")
                    return 0
                raw = run_engine(home, root, "context", args.query, "--budget", str(binding.budget),
                                 "--no-sync", "--no-trace", *binding.read_flags())
                result = {"packet": raw["packet"], "project": binding.project, "estimated_tokens": raw["estimated_tokens"], "token_budget": legacy_accounting()}
            elif args.operation == "read":
                extra = ["--document"] if args.document else []
                result = run_engine(home, root, "read", args.section.removeprefix("elm://section/"),
                                    *extra, *binding.read_flags())
            elif args.operation == "history":
                result = run_engine(home, root, "history", "--project", binding.project, "--no-sync")
            elif args.operation == "doctor":
                result = run_engine(home, root, "doctor", "--no-sync")
            else:
                result = run_engine(home, root, "sync")
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ElmError, CaptureRefused, OSError, sqlite3.Error) as exc:
        print(json.dumps({"error": (str(exc) if isinstance(exc, CaptureRefused) else getattr(exc, "code", "operator_io_failed")), "message": str(exc),
                          "engine_result": getattr(exc, "result", None)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
