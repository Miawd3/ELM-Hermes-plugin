"""Pinned, source-only ELM engine subprocess boundary (no shell or credentials)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ENGINE = Path(__file__).resolve().parents[1] / "engine"


class ElmError(ValueError):
    def __init__(self, code, message, *, result=None):
        super().__init__(message)
        self.code = code
        self.result = result


def run_engine(home: Path, root: Path, *args: str, request=None, task: str | None = None) -> dict:
    # Only OS/runtime paths survive. No API keys, ELM_ROOT or user Python hooks.
    env = {key: value for key, value in os.environ.items()
           if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR"}}
    env.update(PYTHONPATH=str(ENGINE), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1",
               HOME=str(home), USERPROFILE=str(home))
    command = [sys.executable, "-B", "-s", "-S", "-m", "elm_memory", *args,
               "--root", str(root), "--json"]
    if task is not None:
        # All trusted options, including root/JSON and provider policy flags,
        # precede the terminator. A model task is one unchanged positional value.
        command.extend(["--", task])
    try:
        completed = subprocess.run(
            command,
            input=json.dumps(request, ensure_ascii=False) if request is not None else None,
            encoding="utf-8", capture_output=True, cwd=ENGINE, env=env,
            timeout=20, shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ElmError("engine_timeout", "ELM timed out; a write may have committed. Inspect history before retrying.") from exc
    try:
        result = json.loads(completed.stdout.strip() or completed.stderr.strip())
    except ValueError as exc:
        raise ElmError("engine_failed", completed.stderr.strip()[:1200] or "ELM returned no JSON") from exc
    if completed.returncode:
        raise ElmError("engine_refused", "ELM refused the operation", result=result)
    return result
