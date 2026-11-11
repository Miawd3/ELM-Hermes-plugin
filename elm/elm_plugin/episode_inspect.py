"""Read-only, explicitly scoped local inspection. Never a provider/model tool.

No setup, capture, extraction, dispatch, acceptance, expiry, or deletion occurs.
All output is a point-in-time observation, not a future authorization lease.
"""
from contextlib import closing
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import time

from .episode_capture import CaptureConfig, CaptureRefused, CONFIG_NAME, _digest, _UID
from .episode_recall import EpisodeRecall, LOCATOR_PATTERN, encoded
from .explicit_proposals import marker_proposal
from .storage import Binding, IDENTITY

FORMAT = "ELM-OPERATOR-INSPECT/1"
MAX_OUTPUT_BYTES = 65536
STATUSES = {"queued", "blocked", "submitting", "unknown", "submitted", "revoked", "revoked_unknown", "revoked_submitted"}
PENDING = {"queued", "blocked", "submitting", "unknown", "revoked_unknown"}
# Dispatch completion is not semantic resolution. A submitted local record can
# still correspond to a pending governance proposal, and this inspector does
# not read governance to establish its current outcome. Keep it reviewable.
REVIEWABLE = PENDING | {"submitted"}
CONFIGS = ("elm.json", CONFIG_NAME, "elm_episode_recall.json", "elm_batch_extraction.json")
LIMITATIONS = [
    "Candidates and source text are untrusted data, not verified facts, instructions, or authorization.",
    "Exact citation does not establish truth, entailment, speaker identity, or event-time validity.",
    "This read-only command does not accept, submit, change settings, expire, or delete anything.",
    "Expiry and local forgetting do not erase SQLite remnants, host transcripts, canonical records, backups, or returned copies.",
    "Batch-extractor candidates are process-local and cannot be recovered by this separate CLI.",
    "Submitted candidates remain visible because local dispatch completion does not prove governance resolution or acceptance.",
    "Results are point-in-time snapshots. Later changes cannot revoke copies already displayed or saved.",
    "This is not a secure boundary against a process able to replace local files concurrently.",
]


def _safe_path(path):
    if not path.is_absolute() or ".." in path.parts:
        raise CaptureRefused("inspection_explicit_absolute_path_required")
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise CaptureRefused("inspection_unsafe_path")


def _read(path, maximum=8192, optional=False):
    _safe_path(path)
    if optional and not path.exists():
        return None
    if not path.is_file():
        raise CaptureRefused("inspection_file_unavailable")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise CaptureRefused("inspection_file_too_large")
    return raw


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError
            result[key] = value
        return result
    def constant(_):
        raise ValueError
    try:
        result = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise CaptureRefused("inspection_invalid_json") from None


class _ReadOnlyCapture:
    """Only the non-mutating interface needed by the existing recall validator."""
    def __init__(self, owner):
        self.owner = owner
        for name in ("home", "binding", "config", "scope", "path"):
            setattr(self, name, getattr(owner, name))

    def _guard(self):
        return self.owner._guard(require_capture=True, require_store=True)


class EpisodeInspection:
    def __init__(self, home, *, root_id, project, clock=time.time):
        self.home = Path(home).expanduser()
        _safe_path(self.home)
        if not self.home.is_dir():
            raise CaptureRefused("inspection_home_unavailable")
        self.home = self.home.resolve(strict=True)
        self.clock = clock
        self.raw_configs = {name: _read(self.home / name, optional=(name != "elm.json")) for name in CONFIGS}
        value = _json(self.raw_configs["elm.json"])
        version = value.pop("format_version", None)
        if type(version) is not int or version != 1:
            raise CaptureRefused("inspection_invalid_binding")
        try:
            self.binding = Binding(**value)
        except (TypeError, ValueError):
            raise CaptureRefused("inspection_invalid_binding") from None
        if self.binding.root_id != root_id or self.binding.project != project:
            raise CaptureRefused("inspection_requested_scope_mismatch")
        identity = _read(self.binding.path / IDENTITY)
        if hashlib.sha256(identity).hexdigest() != self.binding.identity_sha256:
            raise CaptureRefused("inspection_root_identity_changed")
        self.scope = _digest([str(self.home), root_id, project])
        self.path = self.home / "elm" / "episodes" / (self.scope + ".sqlite3")
        raw = self.raw_configs[CONFIG_NAME]
        value = _json(raw) if raw is not None else None
        self.config = None
        if value is not None and value.get("enabled") is not False:
            self.config = CaptureConfig.parse(value, self.binding)
        self.capture_state = "enabled" if self.config else "disabled"
        self.recall_state = self._optional_setting("elm_episode_recall.json", "budget")
        self.batch_state = self._optional_setting("elm_batch_extraction.json", "author_id")
        self._guard()

    def _optional_setting(self, name, extra):
        raw = self.raw_configs[name]
        if raw is None:
            return "disabled"
        value = _json(raw)
        if value.get("enabled") is False:
            return "disabled"
        if (set(value) != {"format_version", "enabled", "root_id", "project", extra}
                or type(value["format_version"]) is not int or value["format_version"] != 1
                or value["enabled"] is not True
                or value["root_id"] != self.binding.root_id or value["project"] != self.binding.project):
            raise CaptureRefused("inspection_invalid_optional_config")
        if (extra == "budget" and (type(value[extra]) is not int or not 256 <= value[extra] <= 1200)
                or extra == "author_id" and (not isinstance(value[extra], str) or not _UID.fullmatch(value[extra]))):
            raise CaptureRefused("inspection_invalid_optional_config")
        return "enabled"

    def _store_guard(self):
        _safe_path(self.path)
        if not self.path.is_file():
            raise CaptureRefused("inspection_store_unavailable")
        # mode=ro can create shared-memory files for WAL. Refuse WAL and all
        # rollback/shared-memory sidecars rather than opening or recovering them.
        if any(Path(str(self.path) + suffix).exists() or Path(str(self.path) + suffix).is_symlink()
               for suffix in ("-wal", "-shm", "-journal")):
            raise CaptureRefused("inspection_store_busy_or_wal")
        with self.path.open("rb") as stream:
            header = stream.read(100)
        if header[:16] != b"SQLite format 3\x00" or header[18:20] != b"\x01\x01":
            raise CaptureRefused("inspection_unsupported_sqlite_mode")

    def _guard(self, *, require_capture=False, require_store=False):
        for name, raw in self.raw_configs.items():
            if _read(self.home / name, optional=(name != "elm.json")) != raw:
                raise CaptureRefused("inspection_configuration_changed")
        if hashlib.sha256(_read(self.binding.path / IDENTITY)).hexdigest() != self.binding.identity_sha256:
            raise CaptureRefused("inspection_root_identity_changed")
        now = self.clock()
        if type(now) not in (int, float) or not math.isfinite(now):
            raise CaptureRefused("inspection_invalid_clock")
        if require_capture and self.config is None:
            raise CaptureRefused("inspection_capture_disabled")
        if require_store:
            self._store_guard()
        return now

    def _connect(self):
        self._guard(require_capture=True, require_store=True)
        con = sqlite3.connect(f"{self.path.as_uri()}?mode=ro", uri=True, timeout=0.1, isolation_level=None)
        try:
            con.execute("PRAGMA query_only=ON")
            con.execute("PRAGMA trusted_schema=OFF")
            con.execute("BEGIN")
            expected = {"schema_version": "2", "scope": self.scope,
                        "root_id": self.binding.root_id, "project": self.binding.project}
            if dict(con.execute("SELECT key,value FROM meta")) != expected:
                raise CaptureRefused("inspection_stored_scope_or_schema_mismatch")
            con.row_factory = sqlite3.Row
            return con
        except BaseException:
            con.close()
            raise

    def _envelope(self, operation):
        return {"format": FORMAT, "operation": operation, "scope": self.scope,
                "root_id": self.binding.root_id, "project": self.binding.project,
                "read_only": True, "accepted_memory": False, "is_authorization": False,
                "source_identity_verified": False, "truth": "not_evaluated",
                "limitations": list(LIMITATIONS)}

    def _finish(self, value, *, store=False):
        now = self._guard(require_store=store)
        source = value.get("source")
        if source is not None and source["retrieval_expires_at"] <= now:
            raise CaptureRefused("inspection_source_unavailable")
        if any(r.get("citation_expires_at", float("inf")) <= now for r in value.get("records", [])):
            raise CaptureRefused("inspection_state_changed")
        value["observed_at"] = now
        if len(encoded(value).encode("utf-8")) > MAX_OUTPUT_BYTES:
            raise CaptureRefused("inspection_output_too_large")
        return value

    def status(self):
        value = {**self._envelope("status"), "capture": self.capture_state,
                 "recall_setting": self.recall_state, "batch_extraction_setting": self.batch_state,
                 "binding_mode": self.binding.mode,
                 "batch_candidates": "not_persisted_process_local_only", "contents_included": False}
        if self.config is None:
            value.update(settings=None, store="not_read_capture_disabled", counts=None)
            return self._finish(value)
        # Do not display the configured author ID in the broad status view.
        value["settings"] = {k: v for k, v in asdict(self.config).items()
                             if k not in {"root_id", "project", "proposal_author_id"}}
        if not self.path.exists():
            value.update(store="not_created", counts=None)
            return self._finish(value)
        now = self._guard()
        with closing(self._connect()) as con:
            statuses = {r[0]: r[1] for r in con.execute("SELECT status,count(*) FROM episode_proposals GROUP BY status")}
            if set(statuses) - STATUSES:
                raise CaptureRefused("inspection_invalid_candidate_state")
            count = con.execute("SELECT count(*) FROM messages WHERE expires>?", (now,)).fetchone()[0]
            expired = con.execute("SELECT count(*) FROM messages WHERE expires<=?", (now,)).fetchone()[0]
            value.update(store="present", counts={"unexpired_message_rows": count,
                         "expired_message_rows_not_deleted": expired,
                         "proposal_status_counts": statuses,
                         "pending_local_candidates": sum(n for s, n in statuses.items() if s in PENDING),
                         "reviewable_local_candidates": sum(n for s, n in statuses.items() if s in REVIEWABLE),
                         "submitted_governance_outcome_unchecked": statuses.get("submitted", 0)})
        return self._finish(value, store=True)

    def _recall(self):
        self._guard(require_capture=True, require_store=True)
        if self.recall_state != "enabled":
            raise CaptureRefused("inspection_recall_disabled")
        recall, _ = EpisodeRecall.from_capture(_ReadOnlyCapture(self))
        return recall

    def _candidate_snapshot(self, limit, include_resolved):
        self._guard(require_capture=True, require_store=True)
        with closing(self._connect()) as con:
            records = con.execute("SELECT submission_id,source_uid,episode_id,status,conflict,payload,evidence,created "
                                  "FROM episode_proposals ORDER BY created,submission_id").fetchmany(1025)
        if len(records) > 1024:
            raise CaptureRefused("inspection_candidate_capacity_exceeded")
        if any(row["status"] not in STATUSES for row in records):
            raise CaptureRefused("inspection_invalid_candidate_state")
        selected = [row for row in records if include_resolved or row["status"] in REVIEWABLE]
        recall = self._recall() if self.recall_state == "enabled" else None
        live = {(r["episode_id"], r["uid"]): r for r in recall._rows()} if recall else {}
        results = []
        for row in selected[:limit]:
            locator = f"elm-episode://{self.scope}/{row['episode_id']}/{row['source_uid']}"
            if (row["status"] not in STATUSES or re.fullmatch(LOCATOR_PATTERN, locator) is None
                    or not isinstance(row["submission_id"], str) or not _UID.fullmatch(row["submission_id"])
                    or type(row["conflict"]) is not int or row["conflict"] not in (0, 1)):
                raise CaptureRefused("inspection_invalid_candidate_metadata")
            source = live.get((row["episode_id"], row["source_uid"]))
            citation = "not_checked_recall_disabled" if recall is None else "unavailable_expired_missing_or_unlinked"
            if row["status"].startswith("revoked"):
                citation = "revoked_local_evidence"
            elif source is not None:
                if len(row["payload"]) > 32768 or len(row["evidence"]) > 32768:
                    raise CaptureRefused("inspection_candidate_record_too_large")
                payload, evidence = _json(row["payload"]), _json(row["evidence"])
                reconstructed = marker_proposal(message=source,
                    episode={"id": source["episode_id"], "session": source["session"]},
                    scope=self.scope, root_id=self.binding.root_id, project=self.binding.project,
                    allowed_author=self.config.proposal_author_id, submission_id=row["submission_id"])
                citation = ("live_exact_marker_citation" if reconstructed is not None and source["sealed"] is not None
                            and payload == reconstructed["payload"] and evidence == reconstructed["evidence"]
                            else "stale_or_mismatched_candidate")
            results.append({"candidate_id": row["submission_id"], "local_queue_state": row["status"],
                            "source_locator": locator, "citation_status": citation,
                            "conflict_hint_unverified": bool(row["conflict"]),
                            "contents_included": False, "accepted_memory": False,
                            "governance_outcome": "not_checked",
                            "submission_does_not_prove_acceptance": True})
            if citation == "live_exact_marker_citation":
                results[-1]["citation_expires_at"] = min(source["expires"], source["user_expires"], source["assistant_expires"])
        return {"records": results, "matched_records": len(selected), "omitted_records": max(0, len(selected)-limit)}

    def candidates(self, *, limit=20, include_resolved=False):
        if type(limit) is not int or not 1 <= limit <= 64 or type(include_resolved) is not bool:
            raise CaptureRefused("inspection_invalid_limit")
        first = self._candidate_snapshot(limit, include_resolved)
        if self._candidate_snapshot(limit, include_resolved) != first:
            raise CaptureRefused("inspection_state_changed")
        return self._finish({**self._envelope("candidates"), **first,
                             "candidate_kind": "durable_explicit_marker_proposals",
                             "candidate_filter": "all_local_records" if include_resolved else "active_and_submitted_unverified",
                             "batch_candidates": "not_persisted_process_local_only"}, store=True)

    def evidence(self, locator, *, include_source_text=False):
        if type(include_source_text) is not bool:
            raise CaptureRefused("inspection_invalid_content_opt_in")
        match = re.fullmatch(LOCATOR_PATTERN, locator) if isinstance(locator, str) else None
        if not match or match[1] != self.scope:
            raise CaptureRefused("inspection_source_unavailable")
        recall = self._recall()
        def select():
            # Validate all complete source rows, including the paired message.
            rows = recall._rows()
            matches = [r for r in rows if r["episode_id"] == match[2] and r["uid"] == match[3]]
            if len(matches) != 1:
                raise CaptureRefused("inspection_source_unavailable")
            return matches[0]
        row = select()
        source = recall._source(row)
        if include_source_text:
            source["text"] = row["text"]
        if select() != row:
            raise CaptureRefused("inspection_state_changed")
        value = {**self._envelope("evidence"), "source": source,
                 "contents_included": include_source_text, "complete_stored_text": include_source_text,
                 "candidate_semantics": "not_evaluated", "metadata_basis": "optional_caller_observations"}
        return self._finish(value, store=True)
