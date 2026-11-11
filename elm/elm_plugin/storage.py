"""Explicit, profile-owned adoption; never derives ownership from cwd."""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from .engine import ElmError, run_engine
from .token_budget import validate_settings, TokenCounter

CONFIG = "elm.json"
IDENTITY = "00_registry/ELM_ROOT_ID.json"
MODES = ("read-only", "proposal-only", "autonomous")
RECALL_MODES = ("explicit-only", "legacy-background")


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@dataclass(frozen=True)
class Binding:
    root: str
    project: str
    mode: str
    budget: int
    root_id: str
    identity_sha256: str
    recall_mode: str = "explicit-only"
    # Missing fields in historic v1 bindings retain visibly labeled legacy behavior.
    budget_mode: str = "legacy-estimate"
    tokenizer: str | None = None
    tokenizer_vocab: str | None = None

    def __post_init__(self):
        validate_settings(self.budget_mode, self.tokenizer, self.tokenizer_vocab)
        if (self.recall_mode not in RECALL_MODES or self.mode not in MODES or type(self.budget) is not int or not 200 <= self.budget <= 1200
                or not isinstance(self.project, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", self.project)
                or not isinstance(self.root, str) or not Path(self.root).is_absolute()
                or not isinstance(self.root_id, str) or not re.fullmatch(r"root_[0-9a-f-]{36}", self.root_id)
                or not isinstance(self.identity_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", self.identity_sha256)):
            raise ElmError("invalid_config", "Invalid pinned ELM binding; explicit setup required")

    @property
    def path(self):
        return Path(self.root)

    def check_identity(self):
        try:
            current = hashlib.sha256((self.path / IDENTITY).read_bytes()).hexdigest()
        except OSError as exc:
            raise ElmError("root_identity_unavailable", "Configured ELM root identity is unavailable") from exc
        if current != self.identity_sha256:
            raise ElmError("root_identity_changed", "Configured ELM identity changed; explicit operator re-adoption required")

    def read_flags(self):
        return ["--project", self.project, "--require-current-projection",
                "--consistency-profile", "proposal-only", "--expected-root-identity-sha256",
                self.identity_sha256]


def adopt(home: Path, values: dict) -> Binding:
    root = Path(values["root"]).expanduser()
    if not root.is_absolute():
        raise ElmError("invalid_root", "ELM root must be an explicit absolute path")
    root = root.resolve(strict=True)
    project = values["project"]
    if not isinstance(project, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", project):
        raise ElmError("invalid_project", "Project must be an existing ELM project identifier")
    mode = values.get("mode", "read-only")
    if mode not in MODES:
        raise ElmError("invalid_mode", "Unknown mutation mode")
    recall_mode = values.get("recall_mode", "explicit-only")
    if recall_mode not in RECALL_MODES:
        raise ElmError("invalid_recall_mode", "Unknown recall mode")
    budget_value = values.get("budget", 700)
    if type(budget_value) is bool or not (type(budget_value) is int or (isinstance(budget_value, str) and budget_value.isdecimal())):
        raise ElmError("invalid_budget", "Budget must be an integer")
    budget = int(budget_value)
    if not 200 <= budget <= 1200:
        raise ElmError("invalid_budget", "Budget must be between 200 and 1200 in the selected accounting mode")
    budget_mode = values.get("budget_mode", "measured")
    tokenizer, vocab = values.get("tokenizer"), values.get("tokenizer_vocab")
    validate_settings(budget_mode, tokenizer, vocab)
    if budget_mode == "measured":
        TokenCounter(tokenizer, vocab)  # Validate before committing configuration.
    status = run_engine(home, root, "status", "--readiness-only")
    if not status.get("healthy") or not status.get("root_identity"):
        raise ElmError("store_not_ready", "Adoption requires a healthy, indexed, identified ELM root", result=status)
    # Read under the requested project policy, not mere directory existence.
    run_engine(home, root, "read", f"20_projects/{project}/PROJECT_HUB.md", "--document", "--project", project)
    binding = Binding(str(root), project, mode, budget, status["root_identity"]["root_id"],
                      hashlib.sha256((root / IDENTITY).read_bytes()).hexdigest(), recall_mode,
                      budget_mode, tokenizer, vocab)
    atomic_json(home / CONFIG, {"format_version": 1, **asdict(binding)})
    return binding


def load_binding(home: Path) -> Binding:
    try:
        value = json.loads((home / CONFIG).read_text(encoding="utf-8"))
        if value.pop("format_version") != 1:
            raise ValueError("Unsupported config version")
        binding = Binding(**value)
        binding.check_identity()
        return binding
    except (OSError, TypeError, KeyError, ValueError) as exc:
        if isinstance(exc, ElmError):
            raise
        raise ElmError("not_configured", "Run explicit ELM setup/adoption for this profile") from exc
