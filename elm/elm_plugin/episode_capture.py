"""Experimental, opt-in local episode evidence. No extraction or accepted memory.

Only the latest completed, identity-bearing user/assistant pair is admitted. The
host manager already scrubs provider egress; the small scrub below is additional
defense, not a general sensitive-data classifier or a secure-deletion promise.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time
from uuid import uuid4

from .engine import ElmError
from .explicit_proposals import marker_proposal, EXTRACTOR_VERSION


CONFIG_NAME = "elm_episode_capture.json"
_UID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_SOURCE_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])\Z")
_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----", re.S),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"(?i)\b(?:password|passwd|api[_ -]?key|access[_ -]?token|client[_ -]?secret)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_.~+/-]{8,}=*"),
)
# RFC 2397-style inline URI: a standalone data scheme, non-whitespace header,
# then the required comma. Mere prose labels such as "Metadata:" are not URIs.
_INLINE_DATA_URI = re.compile(r"(?<![A-Za-z0-9+.-])data:[^\s:<>\",]*,", re.I)
_GAP_LIMIT = 2147483647
_GAP_REASONS = frozenset({
    "non_plain_or_empty_text", "inline_media_refused", "turn_too_large",
    "stable_messages_required", "completed_pair_required", "ineligible_source_pair",
    "restricted_turn_data_use", "source_text_mismatch", "unverified_or_bot_author",
    "invalid_author_identity", "stable_message_uid_required", "duplicate_uid_in_pair",
    "invalid_source_speaker_id", "invalid_source_timestamp", "source_speaker_author_mismatch",
    "invalid_session_identity", "message_identity_conflict", "previously_expired_source",
    "capture_capacity_reached",
})
_EPHEMERAL_FLAGS = (
    "_compressed_summary", "_empty_recovery_synthetic", "_empty_terminal_sentinel",
    "_thinking_prefill", "_verification_stop_synthetic", "_pre_verify_synthetic",
    "_kanban_stop_synthetic", "_dropped_toolcall_nudge",
)


class CaptureRefused(ValueError):
    """A fixed reason code, without source text in logs or status."""


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                                     sort_keys=True).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CaptureConfig:
    root_id: str
    project: str
    retention_seconds: int = 259200
    max_text_bytes: int = 1048576
    max_messages: int = 1024
    max_seen_ids: int = 8192
    episode_turns: int = 8
    episode_text_bytes: int = 12000
    explicit_proposals: bool = False
    proposal_author_id: str | None = None
    max_proposal_records: int = 256
    max_submissions_per_flush: int = 2
    max_batch_episodes: int = 8

    @classmethod
    def parse(cls, value, binding):
        required = {"format_version", "enabled", "root_id", "project"}
        optional = set(cls.__dataclass_fields__) - {"root_id", "project"}
        if (not isinstance(value, dict) or set(value) - required - optional
                or required - set(value) or type(value["format_version"]) is not int
                or value["format_version"] != 1 or value["enabled"] is not True):
            raise CaptureRefused("invalid_or_disabled_capture_config")
        if value["root_id"] != binding.root_id or value["project"] != binding.project:
            raise CaptureRefused("capture_scope_mismatch")
        config = cls(**{key: value[key] for key in cls.__dataclass_fields__ if key in value})
        ranges = {"retention_seconds": (60, 604800), "max_text_bytes": (256, 16777216),
                  "max_messages": (2, 10000), "max_seen_ids": (2, 100000),
                  "episode_turns": (1, 100), "episode_text_bytes": (128, 1048576),
                  "max_proposal_records": (1, 1024), "max_submissions_per_flush": (1, 8),
                  "max_batch_episodes": (1, 32)}
        for name, (low, high) in ranges.items():
            number = getattr(config, name)
            if type(number) is not int or not low <= number <= high:
                raise CaptureRefused("invalid_capture_limit")
        if config.max_messages > config.max_seen_ids:
            raise CaptureRefused("invalid_capture_limit")
        if type(config.explicit_proposals) is not bool:
            raise CaptureRefused("invalid_proposal_config")
        if config.proposal_author_id is not None and (
                not isinstance(config.proposal_author_id, str) or not _UID.fullmatch(config.proposal_author_id)):
            raise CaptureRefused("invalid_proposal_author")
        if config.explicit_proposals and config.proposal_author_id is None:
            raise CaptureRefused("proposal_author_required")
        return config


def _safe_text(value, maximum):
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise CaptureRefused("non_plain_or_empty_text")
    if len(value.encode("utf-8")) > maximum:
        raise CaptureRefused("turn_too_large")
    if _INLINE_DATA_URI.search(value):
        raise CaptureRefused("inline_media_refused")
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub("[redacted]", value)
    return value


def _eligible(message):
    if not isinstance(message, dict) or message.get("role") not in {"user", "assistant"}:
        return False
    if any(message.get(flag) for flag in _EPHEMERAL_FLAGS):
        return False
    # Nonempty kinds include internal notifications and steering/scaffolding.
    # This narrow prototype admits only ordinary, unclassified conversation.
    if message.get("display_kind") not in (None, "") or message.get("tool_calls") or message.get("data_use"):
        return False
    metadata = message.get("display_metadata")
    if isinstance(metadata, dict) and (
            metadata.get("compaction_inflight_task_restatement") or metadata.get("inflight_task_restatement")
            or metadata.get("withheld_prompt")
            or metadata.get("data_use")):
        return False
    # A merged row cannot be independently attributed by this minimal adapter.
    if message.get("_absorbed_message_uids") or message.get("_merged_turn_prefix"):
        return False
    return True


def _source_metadata(message, author_id):
    """Optional caller observations, never identity verification or authorization.

    Unknown metadata stays null. The host must supply these typed fields before
    capture; neither the body, role, current clock nor model name supplies them.
    Preserve RFC3339 strings (including UTC offset), or finite Unix seconds as
    used by the stock persisted transcript. Do not guess units or naive zones.
    """
    speaker = message.get("speaker_id")
    stamp = message.get("timestamp")
    if speaker is not None and (not isinstance(speaker, str) or not _UID.fullmatch(speaker)):
        raise CaptureRefused("invalid_source_speaker_id")
    if stamp is not None:
        try:
            if type(stamp) in (int, float):
                if not math.isfinite(stamp):
                    raise ValueError
                datetime.fromtimestamp(stamp, timezone.utc)
            elif isinstance(stamp, str) and _SOURCE_TIME.fullmatch(stamp):
                parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                if parsed.utcoffset() is None:
                    raise ValueError
            else:
                raise ValueError
        except (ValueError, OverflowError, OSError):
            raise CaptureRefused("invalid_source_timestamp") from None
    if message["role"] == "user" and speaker is not None and author_id is not None and speaker != author_id:
        raise CaptureRefused("source_speaker_author_mismatch")
    return {"source_speaker_id": speaker, "source_timestamp": stamp,
            "source_metadata_sha256": _digest([speaker, stamp])}


def completed_pair(user_content, assistant_content, messages, turn_author, maximum):
    """Select the LAST user and LAST assistant, never search older matching text."""
    if not isinstance(messages, list):
        raise CaptureRefused("stable_messages_required")
    conversational = [m for m in messages if isinstance(m, dict)
                      and m.get("role") in {"user", "assistant"}]
    if not conversational or conversational[-1].get("role") != "assistant":
        raise CaptureRefused("completed_pair_required")
    assistant = conversational[-1]
    user = next((m for m in reversed(conversational[:-1]) if m.get("role") == "user"), None)
    if user is None or not _eligible(user) or not _eligible(assistant):
        raise CaptureRefused("ineligible_source_pair")
    # Any restricted source still in context may be paraphrased into this reply.
    # Without reliable derivation tracking, refuse the whole supplied transcript.
    for message in messages:
        metadata = message.get("display_metadata") if isinstance(message, dict) else None
        if isinstance(message, dict) and (message.get("data_use") or (
                isinstance(metadata, dict) and metadata.get("data_use"))):
            raise CaptureRefused("restricted_turn_data_use")
    if user.get("content") != user_content or assistant.get("content") != assistant_content:
        raise CaptureRefused("source_text_mismatch")
    author_id = None
    if turn_author is not None:
        if not isinstance(turn_author, dict) or turn_author.get("is_bot") is not False:
            raise CaptureRefused("unverified_or_bot_author")
        author_id = turn_author.get("id")
        if not isinstance(author_id, str) or not _UID.fullmatch(author_id):
            raise CaptureRefused("invalid_author_identity")
    output = []
    for message in (user, assistant):
        uid = message.get("message_uid")
        if not isinstance(uid, str) or not _UID.fullmatch(uid):
            raise CaptureRefused("stable_message_uid_required")
        role = message["role"]
        text = _safe_text(message["content"], maximum)
        # Only these two typed metadata fields survive, separately from author authority.
        output.append({"uid": uid, "role": role, "text": text,
                       "author_id": author_id if role == "user" else None,
                       "content_sha256": _digest([role, text]),
                       **_source_metadata(message, author_id)})
    if output[0]["uid"] == output[1]["uid"]:
        raise CaptureRefused("duplicate_uid_in_pair")
    return output


class EpisodeCapture:
    """Profile/root/project-local, bounded durable evidence and replay ledger.

    Text expiry is logical; SQLite pages, journals and other host copies are not
    promised securely erased. The bounded UID ledger deliberately outlives text
    to prevent expiration followed by transcript replay from resurrecting it.
    """

    def __init__(self, home, binding, config, config_digest, *, clock=time.time):
        self.home = Path(home).resolve(strict=True)
        self.binding, self.config, self.clock = binding, config, clock
        self.config_path = self.home / CONFIG_NAME
        self.config_digest = config_digest
        self._gap_recording_failed = False
        self.scope = _digest([str(self.home), binding.root_id, binding.project])
        directory = self.home / "elm" / "episodes"
        for parent in (self.home / "elm", directory):
            if parent.is_symlink():
                raise CaptureRefused("unsafe_capture_path")
            parent.mkdir(mode=0o700, exist_ok=True)
        self.path = directory / (self.scope + ".sqlite3")
        if self.path.is_symlink():
            raise CaptureRefused("unsafe_capture_path")
        if not self.path.exists():
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
            except FileExistsError:
                pass
        with closing(self._connect()) as con, con:
            # No automatic migration of historical evidence or identity ledgers.
            # Reject an old schema before making any schema/data changes.
            expected = {"schema_version": "2", "scope": self.scope,
                        "root_id": binding.root_id, "project": binding.project}
            if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone():
                current = dict(con.execute("SELECT key,value FROM meta"))
                if current and current != expected:
                    raise CaptureRefused("stored_scope_or_schema_mismatch")
            if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='capture_gap_events'").fetchone():
                gaps = con.execute("SELECT singleton,refused_attempts,last_reason FROM capture_gap_events").fetchall()
                if (len(gaps) != 1 or gaps[0][0] != 1 or type(gaps[0][1]) is not int
                        or not 0 <= gaps[0][1] <= _GAP_LIMIT or gaps[0][2] not in _GAP_REASONS | {"none"}):
                    raise CaptureRefused("capture_gap_state_invalid")
            con.executescript("""
                CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS capture_gap_events(
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    refused_attempts INTEGER NOT NULL CHECK(refused_attempts BETWEEN 0 AND 2147483647),
                    last_reason TEXT NOT NULL);
                INSERT OR IGNORE INTO capture_gap_events VALUES(1,0,'none');
                CREATE TABLE IF NOT EXISTS seen(uid TEXT PRIMARY KEY,hash TEXT NOT NULL,author_id TEXT,
                    source_metadata_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS messages(
                    uid TEXT PRIMARY KEY,role TEXT NOT NULL,text TEXT NOT NULL,
                    author_id TEXT,hash TEXT NOT NULL,captured REAL NOT NULL,expires REAL NOT NULL,
                    text_bytes INTEGER NOT NULL,source_speaker_id TEXT,source_timestamp);
                CREATE TABLE IF NOT EXISTS episodes(
                    id TEXT PRIMARY KEY,session TEXT NOT NULL,started REAL NOT NULL,
                    sealed REAL,reason TEXT,turn_count INTEGER NOT NULL DEFAULT 0,
                    text_bytes INTEGER NOT NULL DEFAULT 0);
                CREATE UNIQUE INDEX IF NOT EXISTS open_episode ON episodes(session) WHERE sealed IS NULL;
                CREATE TABLE IF NOT EXISTS turns(
                    id TEXT PRIMARY KEY,episode_id TEXT NOT NULL,user_uid TEXT NOT NULL,
                    assistant_uid TEXT NOT NULL,captured REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS episode_batches(
                    episode_id TEXT PRIMARY KEY,processed REAL NOT NULL,source_count INTEGER NOT NULL,
                    staged_count INTEGER NOT NULL,extractor TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS episode_proposals(
                    submission_id TEXT PRIMARY KEY,source_uid TEXT NOT NULL UNIQUE,episode_id TEXT NOT NULL,
                    status TEXT NOT NULL,key_hash TEXT NOT NULL,object_hash TEXT NOT NULL,
                    conflict INTEGER NOT NULL DEFAULT 0,payload TEXT NOT NULL,evidence TEXT NOT NULL,
                    result TEXT,error_code TEXT,created REAL NOT NULL,attempts INTEGER NOT NULL DEFAULT 0);
            """)
            current = dict(con.execute("SELECT key,value FROM meta"))
            if current and current != expected:
                raise CaptureRefused("stored_scope_mismatch")
            if not current:
                con.executemany("INSERT INTO meta VALUES(?,?)", expected.items())

    @classmethod
    def from_profile(cls, home, binding, agent_context, *, clock=time.time):
        if agent_context != "primary":
            return None, "non_primary_context"
        path = Path(home) / CONFIG_NAME
        if not path.exists():
            return None, "disabled"
        if path.is_symlink():
            raise CaptureRefused("unsafe_capture_config")
        raw = path.read_bytes()
        if len(raw) > 8192:
            raise CaptureRefused("invalid_capture_config")
        try:
            value = json.loads(raw)
        except (UnicodeError, ValueError):
            raise CaptureRefused("invalid_capture_config") from None
        if isinstance(value, dict) and value.get("enabled") is False:
            return None, "disabled"
        config = CaptureConfig.parse(value, binding)
        return cls(home, binding, config, hashlib.sha256(raw).hexdigest(), clock=clock), "ready"

    def _connect(self):
        if any(path.is_symlink() for path in (self.home, self.home / "elm", self.path.parent, self.path)):
            raise CaptureRefused("unsafe_capture_path")
        con = sqlite3.connect(f"{self.path.as_uri()}?mode=rw", uri=True, timeout=2)
        try:
            con.execute("PRAGMA busy_timeout=2000")
            con.execute("PRAGMA synchronous=FULL")
            return con
        except BaseException:
            con.close()
            raise

    def _guard(self):
        self.binding.check_identity()
        if self.config_path.is_symlink():
            raise CaptureRefused("capture_config_changed")
        try:
            raw = self.config_path.read_bytes()
        except OSError:
            raise CaptureRefused("capture_config_changed") from None
        if hashlib.sha256(raw).hexdigest() != self.config_digest:
            raise CaptureRefused("capture_config_changed")
        now = self.clock()
        if not isinstance(now, (int, float)) or not math.isfinite(now):
            raise CaptureRefused("invalid_clock")
        return now

    @staticmethod
    def _expire(con, now):
        from .candidate_inbox_store import expire as expire_span_inbox
        expire_span_inbox(con, now)
        con.execute("DELETE FROM messages WHERE expires<=?", (now,))
        # Keep UID pair links after text expiry so operator forgetting can still
        # trace shared-pair local proposal copies. Each admitted turn consumes at
        # least one never-evicted seen ID, so links/episodes remain bounded by the
        # existing max_seen_ids admission ceiling. No source text is retained here.
        con.execute("UPDATE episodes SET sealed=?,reason='source_expired' WHERE sealed IS NULL AND NOT EXISTS "
                    "(SELECT 1 FROM turns t JOIN messages u ON u.uid=t.user_uid "
                    "JOIN messages a ON a.uid=t.assistant_uid WHERE t.episode_id=episodes.id)", (now,))

    def _record_gap(self, reason):
        # One bounded row, no rejected text, author, UID or timestamp. Count
        # attempts, not unique missing messages: an explicit retry increments it.
        if reason not in _GAP_REASONS:
            return
        try:
            self._guard()  # Withdrawal or changed scope must not authorize writes.
            with closing(self._connect()) as con, con:
                updated = con.execute("UPDATE capture_gap_events SET refused_attempts=min(refused_attempts+1,?),"
                                      "last_reason=? WHERE singleton=1", (_GAP_LIMIT, reason))
                if updated.rowcount != 1:
                    raise CaptureRefused("capture_gap_state_invalid")
        except (CaptureRefused, ElmError, OSError, sqlite3.Error):
            self._gap_recording_failed = True

    def append_turn(self, session_id, user_content, assistant_content, *, messages=None, turn_author=None):
        try:
            return self._append_turn(session_id, user_content, assistant_content,
                                     messages=messages, turn_author=turn_author)
        except CaptureRefused as exc:
            self._record_gap(str(exc))
            raise

    def _append_turn(self, session_id, user_content, assistant_content, *, messages=None, turn_author=None):
        if not isinstance(session_id, str) or not _UID.fullmatch(session_id):
            raise CaptureRefused("invalid_session_identity")
        pair = completed_pair(user_content, assistant_content, messages, turn_author, self.config.max_text_bytes)
        now = self._guard()
        with closing(self._connect()) as con, con:
            con.execute("BEGIN IMMEDIATE")
            self._expire(con, now)
            additions = []
            for item in pair:
                old = con.execute("SELECT hash,author_id,source_metadata_hash FROM seen WHERE uid=?", (item["uid"],)).fetchone()
                if old:
                    if old[0] != item["content_sha256"] or (old[1] is not None and item["author_id"] is not None
                                                          and old[1] != item["author_id"]) or old[2] != item["source_metadata_sha256"]:
                        raise CaptureRefused("message_identity_conflict")
                else:
                    additions.append(item)
            if not additions:
                return {"status": "duplicate", "captured_messages": 0}
            # A partially expired/revoked turn must not bring its surviving half back.
            old_uids = [m["uid"] for m in pair if m not in additions]
            if any(not con.execute("SELECT 1 FROM messages WHERE uid=?", (uid,)).fetchone() for uid in old_uids):
                raise CaptureRefused("previously_expired_source")
            count, size = con.execute("SELECT count(*),coalesce(sum(text_bytes),0) FROM messages").fetchone()
            seen = con.execute("SELECT count(*) FROM seen").fetchone()[0]
            added_bytes = sum(len(m["text"].encode("utf-8")) for m in additions)
            if (count + len(additions) > self.config.max_messages or size + added_bytes > self.config.max_text_bytes
                    or seen + len(additions) > self.config.max_seen_ids):
                raise CaptureRefused("capture_capacity_reached")
            for item in additions:
                con.execute("INSERT INTO seen VALUES(?,?,?,?)", (item["uid"], item["content_sha256"], item["author_id"], item["source_metadata_sha256"]))
                con.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?,?)",
                            (item["uid"], item["role"], item["text"], item["author_id"], item["content_sha256"],
                             now, now + self.config.retention_seconds, len(item["text"].encode("utf-8")),
                             item["source_speaker_id"], item["source_timestamp"]))
            row = con.execute("SELECT id FROM episodes WHERE session=? AND sealed IS NULL", (session_id,)).fetchone()
            episode = row[0] if row else "episode_" + str(uuid4())
            if not row:
                con.execute("INSERT INTO episodes(id,session,started) VALUES(?,?,?)", (episode, session_id, now))
            turn_id = _digest([pair[0]["uid"], pair[1]["uid"]])
            con.execute("INSERT INTO turns VALUES(?,?,?,?,?)", (turn_id, episode, pair[0]["uid"], pair[1]["uid"], now))
            con.execute("UPDATE episodes SET turn_count=turn_count+1,text_bytes=text_bytes+? WHERE id=?", (added_bytes, episode))
            turns, size = con.execute("SELECT turn_count,text_bytes FROM episodes WHERE id=?", (episode,)).fetchone()
            sealed = turns >= self.config.episode_turns or size >= self.config.episode_text_bytes
            if sealed:
                con.execute("UPDATE episodes SET sealed=?,reason='size_boundary' WHERE id=?", (now, episode))
            return {"status": "captured", "captured_messages": len(additions), "episode_sealed": sealed}

    def seal(self, session_id, reason):
        if reason not in {"session_end", "session_switch", "pre_compress", "shutdown", "rewind"}:
            raise CaptureRefused("invalid_boundary")
        now = self._guard()
        with closing(self._connect()) as con, con:
            con.execute("BEGIN IMMEDIATE")
            self._expire(con, now)
            con.execute("UPDATE episodes SET sealed=?,reason=? WHERE session=? AND sealed IS NULL", (now, reason, session_id))
        return {"status": "sealed", "reason": reason}

    def status(self):
        now = self._guard()
        with closing(self._connect()) as con:
            count, size = con.execute("SELECT count(*),coalesce(sum(text_bytes),0) FROM messages WHERE expires>?", (now,)).fetchone()
            seen = con.execute("SELECT count(*) FROM seen").fetchone()[0]
            episodes = con.execute("SELECT count(*) FROM episodes").fetchone()[0]
            gap = con.execute("SELECT refused_attempts,last_reason FROM capture_gap_events WHERE singleton=1").fetchone()
            if gap is None or type(gap[0]) is not int or not 0 <= gap[0] <= _GAP_LIMIT or gap[1] not in _GAP_REASONS | {"none"}:
                raise CaptureRefused("capture_gap_state_invalid")
        return {"enabled": True, "automatic_extraction": False, "retrieval_enabled": False,
                "source_metadata": "optional_caller_observations", "source_metadata_is_authorization": False,
                "active_messages": count, "active_text_bytes": size, "seen_ids": seen,
                "episodes": episodes, "retention_seconds": self.config.retention_seconds,
                "capture_gaps": {"known_refused_attempts": gap[0], "last_reason": gap[1],
                                 "counter_saturated": gap[0] == _GAP_LIMIT,
                                 "recording_failed_this_instance": self._gap_recording_failed,
                                 "complete_capture_certified": False}}

    def prepare_batches(self):
        """Stage markers only after sealing. Immutable payload IDs survive restart."""
        if not self.config.explicit_proposals:
            return {"status": "explicit_proposals_disabled", "staged": 0}
        now = self._guard()
        staged = processed = 0
        with closing(self._connect()) as con, con:
            con.row_factory = sqlite3.Row
            con.execute("BEGIN IMMEDIATE")
            episodes = con.execute(
                "SELECT * FROM episodes WHERE sealed IS NOT NULL AND id NOT IN "
                "(SELECT episode_id FROM episode_batches) ORDER BY sealed,rowid LIMIT ?",
                (self.config.max_batch_episodes,)).fetchall()
            for episode in episodes:
                sources = con.execute(
                    "SELECT m.*,min(t.rowid) AS source_order FROM messages m JOIN turns t ON t.user_uid=m.uid "
                    "JOIN messages a ON a.uid=t.assistant_uid "
                    "WHERE t.episode_id=? AND m.expires>? AND a.expires>? AND m.role='user' AND a.role='assistant' "
                    "GROUP BY m.uid ORDER BY source_order,m.uid",
                    (episode["id"], now, now)).fetchall()
                candidates = []
                for message in sources:
                    if con.execute("SELECT 1 FROM episode_proposals WHERE source_uid=?", (message["uid"],)).fetchone():
                        continue
                    candidate = marker_proposal(
                        message=message, episode=episode, scope=self.scope, root_id=self.binding.root_id,
                        project=self.binding.project, allowed_author=self.config.proposal_author_id,
                        submission_id="submission_" + str(uuid4()))
                    if candidate is not None:
                        candidates.append((message, candidate))
                count = con.execute("SELECT count(*) FROM episode_proposals").fetchone()[0]
                if count + len(candidates) > self.config.max_proposal_records:
                    raise CaptureRefused("proposal_queue_capacity_reached")
                for message, candidate in candidates:
                    payload = candidate["payload"]
                    key_hash = _digest([payload["project"], payload["subject"], payload["predicate"]])
                    object_hash = _digest(payload["object"])
                    conflict = bool(con.execute(
                        "SELECT 1 FROM episode_proposals WHERE key_hash=? AND object_hash<>?",
                        (key_hash, object_hash)).fetchone())
                    if conflict:
                        con.execute("UPDATE episode_proposals SET conflict=1 WHERE key_hash=?", (key_hash,))
                    con.execute(
                        "INSERT INTO episode_proposals(submission_id,source_uid,episode_id,status,key_hash,object_hash,"
                        "conflict,payload,evidence,created) VALUES(?,?,?,'queued',?,?,?,?,?,?)",
                        (payload["submission_id"], message["uid"], episode["id"], key_hash, object_hash,
                         int(conflict), json.dumps(payload, ensure_ascii=False, sort_keys=True),
                         json.dumps(candidate["evidence"], ensure_ascii=False, sort_keys=True), now))
                con.execute("INSERT INTO episode_batches VALUES(?,?,?,?,?)",
                            (episode["id"], now, len(sources), len(candidates), EXTRACTOR_VERSION))
                staged += len(candidates)
                processed += 1
        return {"status": "staged", "staged": staged, "processed_episodes": processed}

    def next_proposal(self):
        """Claim one row before external dispatch. 'submitting' is never retried automatically."""
        now = self._guard()
        if not self.config.explicit_proposals:
            return None
        with closing(self._connect()) as con, con:
            con.row_factory = sqlite3.Row
            con.execute("BEGIN IMMEDIATE")
            unresolved = con.execute(
                "SELECT submission_id FROM episode_proposals WHERE status IN ('submitting','unknown','revoked_unknown') "
                "ORDER BY created,rowid LIMIT 1").fetchone()
            if unresolved is not None:
                return {"blocked": True, "submission_id": unresolved["submission_id"],
                        "error_code": "unresolved_previous_submission"}
            row = con.execute("SELECT * FROM episode_proposals WHERE status='queued' ORDER BY created,rowid LIMIT 1").fetchone()
            if row is None:
                return None
            evidence = json.loads(row["evidence"])
            payload = json.loads(row["payload"])
            reason = None
            if evidence.get("source_author_id") != self.config.proposal_author_id:
                reason = "proposal_author_changed"
            elif (evidence.get("scope") != self.scope or evidence.get("root_id") != self.binding.root_id
                  or evidence.get("project") != self.binding.project or payload.get("project") != self.binding.project):
                reason = "queued_proposal_scope_mismatch"
            elif (not isinstance(evidence.get("source_expires_at"), (int, float))
                  or evidence["source_expires_at"] <= now):
                reason = "source_expired_before_submission"
            if reason:
                con.execute("UPDATE episode_proposals SET status='blocked',error_code=? WHERE submission_id=?",
                            (reason, row["submission_id"]))
                return {"blocked": True, "submission_id": row["submission_id"], "error_code": reason}
            con.execute("UPDATE episode_proposals SET status='submitting',attempts=attempts+1 WHERE submission_id=?",
                        (row["submission_id"],))
        return {"submission_id": row["submission_id"], "payload": payload}

    @contextmanager
    def dispatch_guard(self, submission_id):
        """Serialize actual dispatch with operator revocation across processes.

        If revocation committed after claim, do not dispatch. If dispatch already
        owns the write transaction, forgetting must wait or fail without writes.
        The lock ends before outcome persistence; late results stay text-free.
        """
        self._guard()
        with closing(self._connect()) as con, con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT status,evidence FROM episode_proposals WHERE submission_id=?",
                              (submission_id,)).fetchone()
            if row is None or row[0] != "submitting":
                raise CaptureRefused("proposal_revoked_before_dispatch")
            evidence = json.loads(row[1])
            now = self._guard()
            expiry = evidence.get("source_expires_at")
            if type(expiry) not in (int, float) or not math.isfinite(expiry) or expiry <= now:
                raise CaptureRefused("source_expired_before_submission")
            yield

    def finish_proposal(self, submission_id, *, result=None, error_code=None):
        # Persist the outcome of a previously authorized in-flight operation even
        # if opt-out arrived meanwhile. This does not authorize another dispatch.
        status = "submitted" if isinstance(result, dict) and result.get("canonical_committed") is True else "unknown"
        if error_code in {"engine_refused", "dispatch_cancelled"}:
            status = "blocked"
        with closing(self._connect()) as con, con:
            con.execute("BEGIN IMMEDIATE")
            revoked = con.execute("SELECT status FROM episode_proposals WHERE submission_id=?",
                                  (submission_id,)).fetchone()
            if revoked and revoked[0] == "revoked_unknown":
                # Never restore payload, evidence or a response body after forget.
                status = "revoked_submitted" if status == "submitted" else (
                    "revoked" if error_code in {"engine_refused", "dispatch_cancelled"} else "revoked_unknown")
                con.execute("UPDATE episode_proposals SET status=?,result=NULL,error_code='source_forgotten' "
                            "WHERE submission_id=?", (status, submission_id))
                return status
            updated = con.execute(
                "UPDATE episode_proposals SET status=?,result=?,error_code=? WHERE submission_id=? AND status='submitting'",
                (status, json.dumps(result, ensure_ascii=False, sort_keys=True) if result is not None else None,
                 error_code, submission_id)).rowcount
            if updated != 1:
                raise CaptureRefused("proposal_outcome_state_mismatch")
        return status

    def proposal_snapshot(self):
        """Operator/test readback only; not a model-facing provider tool."""
        self._guard()
        with closing(self._connect()) as con:
            con.row_factory = sqlite3.Row
            records = []
            for row in con.execute("SELECT * FROM episode_proposals ORDER BY created,rowid"):
                item = dict(row)
                for key in ("payload", "evidence", "result"):
                    item[key] = json.loads(item[key]) if item[key] is not None else None
                item["conflict"] = bool(item["conflict"])
                records.append(item)
            batches = [dict(row) for row in con.execute("SELECT * FROM episode_batches ORDER BY processed,rowid")]
        return {"enabled": self.config.explicit_proposals, "records": records, "batches": batches}
