"""Explicit local read-only inspection, separate from setup and model tools."""
import argparse
import sqlite3
import sys
sys.dont_write_bytecode = True
from elm_plugin.episode_capture import CaptureRefused
from elm_plugin.episode_inspect import EpisodeInspection
from elm_plugin.episode_recall import encoded
from elm_plugin.engine import ElmError


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only local ELM evidence inspection. Suggestions are not verified facts.")
    parser.add_argument("--hermes-home", required=True, help="Explicit absolute profile home")
    parser.add_argument("--root-id", required=True, help="Expected adopted root ID")
    parser.add_argument("--project", required=True, help="Expected adopted project")
    sub = parser.add_subparsers(dest="operation", required=True)
    sub.add_parser("status", help="Capture settings and content-free counts")
    candidates = sub.add_parser("candidates", help="Active and submitted-unverified marker candidates, no bodies")
    candidates.add_argument("--limit", type=int, default=20)
    candidates.add_argument("--include-resolved", action="store_true", help="Also include locally revoked records; does not prove governance resolution")
    evidence = sub.add_parser("evidence", help="Metadata for one current scoped source")
    evidence.add_argument("--locator", required=True)
    evidence.add_argument("--include-source-text", action="store_true", help="Explicitly display stored scrubbed text locally; it may still be sensitive")
    args = parser.parse_args(argv)
    try:
        inspect = EpisodeInspection(args.hermes_home, root_id=args.root_id, project=args.project)
        if args.operation == "status":
            result = inspect.status()
        elif args.operation == "candidates":
            result = inspect.candidates(limit=args.limit, include_resolved=args.include_resolved)
        else:
            result = inspect.evidence(args.locator, include_source_text=args.include_source_text)
        print(encoded(result))
        return 0
    except (CaptureRefused, ElmError, OSError, sqlite3.Error, ValueError, TypeError, KeyError) as exc:
        # Do not echo filenames, SQL values, payloads, or untrusted exception text.
        code = str(exc) if isinstance(exc, CaptureRefused) else "inspection_unavailable"
        print(encoded({"error": code, "read_only": True, "contents_included": False}))
        return 2


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
