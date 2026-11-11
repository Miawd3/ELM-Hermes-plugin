"""Explicit, deterministic retrieval of local episode evidence, never authority.

This module makes no writes and does not call an extractor, model, index, note,
or proposal API. A locator identifies data within one pinned capture scope; it
is not an authorization capability. SQLite content is treated as untrusted.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3

from .episode_capture import CaptureRefused, _digest, _source_metadata, _UID
from .storage import load_binding


CONFIG_NAME = "elm_episode_recall.json"
LOCATOR_PATTERN = (r"elm-episode://([0-9a-f]{64})/"
                   r"(episode_[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})/"
                   r"([A-Za-z0-9_-]{1,128})")


def encoded(value):
    # Escapes preserve data and prevent literal fence/control characters from
    # being presented as markup. This is serialization, not injection immunity.
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).replace("<", "\\u003c").replace(">", "\\u003e")


def estimate(value):
    """Bound the entire serialized result with a deterministic byte/4 estimate.

    This is NOT a model-tokenizer guarantee. The separate byte limit is exact.
    """
    return (len(encoded(value).encode("utf-8")) + 3) // 4


class EpisodeRecall:
    def __init__(self, capture, config_digest, budget):
        self.capture = capture
        self.config_digest, self.budget = config_digest, budget
        self.config_path = capture.home / CONFIG_NAME

    @classmethod
    def from_capture(cls, capture):
        if capture is None:
            return None, "capture_unavailable"
        path = capture.home / CONFIG_NAME
        if not path.exists():
            return None, "disabled"
        if path.is_symlink():
            raise CaptureRefused("unsafe_recall_config")
        raw = path.read_bytes()
        if len(raw) > 2048:
            raise CaptureRefused("invalid_recall_config")
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError):
            raise CaptureRefused("invalid_recall_config") from None
        if isinstance(value, dict) and value.get("enabled") is False:
            return None, "disabled"
        if (not isinstance(value, dict)
                or set(value) != {"format_version", "enabled", "root_id", "project", "budget"}
                or type(value["format_version"]) is not int or value["format_version"] != 1
                or value["enabled"] is not True or type(value["budget"]) is not int
                or not 256 <= value["budget"] <= 1200):
            raise CaptureRefused("invalid_recall_config")
        if value["root_id"] != capture.binding.root_id or value["project"] != capture.binding.project:
            raise CaptureRefused("recall_scope_mismatch")
        recall = cls(capture, hashlib.sha256(raw).hexdigest(), value["budget"])
        recall._guard()
        return recall, "ready"

    def _guard(self):
        capture = self.capture
        now = capture._guard()
        for path in (capture.home, capture.home / "elm", capture.path.parent, capture.path,
                     capture.home / "elm.json", self.config_path):
            if path.is_symlink():
                raise CaptureRefused("unsafe_recall_path")
        if load_binding(capture.home) != capture.binding:
            raise CaptureRefused("recall_binding_changed")
        try:
            raw = self.config_path.read_bytes()
        except OSError:
            raise CaptureRefused("recall_config_changed") from None
        if hashlib.sha256(raw).hexdigest() != self.config_digest:
            raise CaptureRefused("recall_config_changed")
        return now

    def _rows(self, episode=None, uid=None):
        now = self._guard()
        capture = self.capture
        with closing(sqlite3.connect(f"{capture.path.as_uri()}?mode=ro", uri=True,
                                     timeout=0.1, isolation_level=None)) as con:
            con.execute("PRAGMA query_only=ON")
            con.execute("BEGIN")
            expected = {"schema_version": "2", "scope": capture.scope,
                        "root_id": capture.binding.root_id, "project": capture.binding.project}
            if dict(con.execute("SELECT key,value FROM meta")) != expected:
                raise CaptureRefused("recall_stored_scope_or_schema_mismatch")
            con.row_factory = sqlite3.Row
            # Only complete, still-live source pairs are eligible. Never read the
            # durable proposal copies or UID ledger as an alternate text source.
            rows = con.execute(
                "SELECT DISTINCT e.id AS episode_id,e.session,e.started,e.sealed,e.reason,"
                "m.*,s.hash AS seen_hash,s.author_id AS seen_author_id,s.source_metadata_hash,u.expires AS user_expires,"
                "a.expires AS assistant_expires "
                "FROM episodes e JOIN turns t ON t.episode_id=e.id "
                "JOIN messages u ON u.uid=t.user_uid JOIN messages a ON a.uid=t.assistant_uid "
                "JOIN messages m ON m.uid IN (t.user_uid,t.assistant_uid) "
                "JOIN seen s ON s.uid=m.uid "
                "WHERE u.role='user' AND a.role='assistant' AND u.expires>? AND a.expires>? "
                "AND u.captured<=? AND a.captured<=? AND (? IS NULL OR e.id=?) "
                "AND (? IS NULL OR m.uid=?) ORDER BY m.captured DESC,e.id,m.uid",
                (now, now, now, now, episode, episode, uid, uid)).fetchmany(capture.config.max_messages + 1)
        if len(rows) > capture.config.max_messages:
            raise CaptureRefused("recall_capacity_exceeded")
        now = self._guard()  # Observe withdrawal/expiry during the read before disclosure.
        valid = []
        for row in rows:
            item = dict(row)
            for field in ("captured", "expires", "user_expires", "assistant_expires"):
                if type(item[field]) not in (int, float) or not math.isfinite(item[field]):
                    raise CaptureRefused("recall_source_integrity_failed")
            if min(item["expires"], item["user_expires"], item["assistant_expires"]) <= now:
                continue
            if (not isinstance(item["text"], str) or item["role"] not in {"user", "assistant"}
                    or not isinstance(item["uid"], str) or not _UID.fullmatch(item["uid"])
                    or not isinstance(item["session"], str) or not _UID.fullmatch(item["session"])
                    or not isinstance(item["episode_id"], str)
                    or re.fullmatch(r"episode_[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", item["episode_id"]) is None
                    or item["author_id"] != item["seen_author_id"]
                    or (item["author_id"] is not None and (not isinstance(item["author_id"], str)
                        or not _UID.fullmatch(item["author_id"]) or item["role"] != "user"))
                    or item["captured"] > now or item["expires"] <= item["captured"]
                    or item["expires"] > item["captured"] + capture.config.retention_seconds
                    or len(item["text"].encode("utf-8")) != item["text_bytes"]
                    or item["text_bytes"] > capture.config.max_text_bytes
                    or _digest([item["role"], item["text"]]) != item["hash"]
                    or item["hash"] != item["seen_hash"]):
                raise CaptureRefused("recall_source_integrity_failed")
            observed = _source_metadata({"role": item["role"], "speaker_id": item["source_speaker_id"],
                                         "timestamp": item["source_timestamp"]}, item["author_id"])
            if observed["source_metadata_sha256"] != item["source_metadata_hash"]:
                raise CaptureRefused("recall_source_integrity_failed")
            valid.append(item)
        return valid

    def _envelope(self):
        c = self.capture
        return {"format": "ELM-EPISODE/1", "trust": "untrusted_source_evidence",
                "instructions": False, "accepted_memory": False, "source_identity_verified": False,
                "source_metadata": "caller_observations", "scope": c.scope,
                "root_id": c.binding.root_id, "project": c.binding.project,
                "budget_basis": "serialized_utf8_bytes_div_4_estimate_not_tokenizer"}

    def _source(self, row):
        return {"locator": f"elm-episode://{self.capture.scope}/{row['episode_id']}/{row['uid']}",
                "episode_id": row["episode_id"], "session_id": row["session"], "message_uid": row["uid"],
                "role": row["role"], "source_author_id": row["author_id"],
                "source_speaker_id": row["source_speaker_id"], "source_timestamp": row["source_timestamp"],
                "captured_at": row["captured"], "expires_at": row["expires"],
                "retrieval_expires_at": min(row["expires"], row["user_expires"], row["assistant_expires"]),
                "content_sha256": row["hash"], "text_representation": "stored_scrubbed_text"}

    def _finish(self, value):
        # Include accounting overhead itself, including the digit count.
        value.update(estimated_tokens=0, serialized_bytes=0)
        for _ in range(4):
            value["serialized_bytes"] = len(encoded(value).encode("utf-8"))
            value["estimated_tokens"] = estimate(value)
        if value["estimated_tokens"] > self.budget:
            raise CaptureRefused("episode_result_exceeds_budget")
        now = self._guard()
        sources = value.get("results", []) if "results" in value else [value["source"]]
        if any(source["retrieval_expires_at"] <= now or source["captured_at"] > now for source in sources):
            raise CaptureRefused("episode_source_unavailable")
        # A concurrent operator may have forgotten sources after _rows returned.
        # Revalidate complete live pair linkage at the final disclosure boundary.
        if sources:
            live = {(r["episode_id"], r["uid"]): r for r in self._rows()}
            for source in sources:
                row = live.get((source["episode_id"], source["message_uid"]))
                if row is None or self._source(row) != {key: source[key] for key in self._source(row)}:
                    raise CaptureRefused("episode_source_unavailable")
        return value

    def search(self, query, limit=4):
        if not isinstance(query, str) or not query.strip() or len(query) > 256 or "\x00" in query:
            raise CaptureRefused("invalid_episode_query")
        terms = sorted(set(query.casefold().split()))
        if len(terms) > 16 or type(limit) is not int or not 1 <= limit <= 8:
            raise CaptureRefused("invalid_episode_query")
        hits = [row for row in self._rows() if all(term in row["text"].casefold() for term in terms)]
        result = {**self._envelope(), "match_policy": "all_casefolded_literal_terms_newest_capture_first",
                  "results": [], "matched_messages": len(hits), "omitted_messages": len(hits)}
        for row in hits[:limit]:
            # Prefix excerpt is explicitly partial; full text requires exact read.
            candidate = {**self._source(row), "excerpt": row["text"][:160],
                         "excerpt_truncated": len(row["text"]) > 160}
            proposed = {**result, "results": result["results"] + [candidate],
                        "omitted_messages": len(hits) - len(result["results"]) - 1}
            try:
                result = self._finish(proposed)
            except CaptureRefused as exc:
                if str(exc) != "episode_result_exceeds_budget":
                    raise
                break
        return self._finish(result)

    def read(self, locator):
        matched = re.fullmatch(LOCATOR_PATTERN, locator) if isinstance(locator, str) else None
        if matched is None or matched[1] != self.capture.scope:
            raise CaptureRefused("episode_source_unavailable")
        rows = self._rows(matched[2], matched[3])
        if len(rows) != 1:
            raise CaptureRefused("episode_source_unavailable")
        return self._finish({**self._envelope(), "source": {**self._source(rows[0]), "text": rows[0]["text"]},
                             "complete_stored_text": True})
