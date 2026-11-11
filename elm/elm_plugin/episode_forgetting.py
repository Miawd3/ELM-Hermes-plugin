"""Operator-only logical removal of captured evidence and local proposal copies.

No canonical/governance deletion, secure erasure, host transcript editing, or
model-facing destructive tool. Existing non-pruned seen IDs remain replay
barriers; hashes and caller author IDs in that ledger deliberately survive.
"""
from contextlib import closing
from pathlib import Path
import re
import sqlite3

from .episode_capture import CaptureRefused, _digest
from .episode_recall import LOCATOR_PATTERN
from .storage import load_binding


LIMITS = {
    "canonical_claims_removed": False,
    "canonical_governance_removed": False,
    "host_transcripts_removed": False,
    "backups_or_copies_removed": False,
    "secure_erasure": False,
    "retained_replay_metadata": "seen_uids_content_hashes_author_ids_metadata_hashes",
    "replay_prevention": "same_UIDs_in_this_profile_scope_while_ledger_is_preserved",
    "unknown_derivations": "not_traced_or_removed",
    "pair_linkage_scope": "retained_UID_pair_links_only_historical_missing_links_not_reconstructed",
    "retained_expiry_metadata": "pair_UIDs_episode_IDs_session_IDs_capture_times_until_explicit_forget",
}


class EpisodeForget:
    """Explicit profile-local control; works even after capture/recall opt-out.

    Construction and preview never create or modify a database. Apply requires
    the exact digest returned by a fresh preview; changes require new review.
    """
    def __init__(self, home, binding=None):
        raw = Path(home)
        if not raw.is_absolute() or raw.is_symlink():
            raise CaptureRefused("unsafe_forget_path")
        self.home = raw.resolve(strict=True)
        self.binding = binding or load_binding(self.home)
        self.scope = _digest([str(self.home), self.binding.root_id, self.binding.project])
        self.path = self.home / "elm" / "episodes" / (self.scope + ".sqlite3")
        self._guard()

    def _guard(self):
        for path in (self.home, self.home / "elm", self.path.parent, self.path, self.home / "elm.json"):
            if path.is_symlink():
                raise CaptureRefused("unsafe_forget_path")
        self.binding.check_identity()
        if load_binding(self.home) != self.binding:
            raise CaptureRefused("forget_binding_changed")
        if not self.path.is_file():
            raise CaptureRefused("episode_store_unavailable")

    def _connect(self, *, write=False):
        self._guard()
        con = sqlite3.connect(f"{self.path.as_uri()}?mode={'rw' if write else 'ro'}", uri=True, timeout=2,
                              isolation_level=None)
        con.row_factory = sqlite3.Row
        if not write:
            con.execute("PRAGMA query_only=ON")
        con.execute("PRAGMA synchronous=FULL")
        return con

    def _plan(self, con, locator):
        match = re.fullmatch(LOCATOR_PATTERN, locator) if isinstance(locator, str) else None
        if not match or match[1] != self.scope:
            raise CaptureRefused("episode_source_unavailable")
        expected = {"schema_version": "2", "scope": self.scope,
                    "root_id": self.binding.root_id, "project": self.binding.project}
        if dict(con.execute("SELECT key,value FROM meta")) != expected:
            raise CaptureRefused("forget_stored_scope_or_schema_mismatch")
        episode, uid = match[2], match[3]
        turns = [dict(r) for r in con.execute("SELECT * FROM turns").fetchmany(100001)]
        proposals = [dict(r) for r in con.execute("SELECT * FROM episode_proposals").fetchmany(1025)]
        if len(turns) > 100000 or len(proposals) > 1024:
            raise CaptureRefused("forget_store_capacity_exceeded")
        if not (any(t["episode_id"] == episode and uid in (t["user_uid"], t["assistant_uid"]) for t in turns)
                or any(p["episode_id"] == episode and p["source_uid"] == uid for p in proposals)):
            raise CaptureRefused("episode_source_unavailable")
        # Connected-component closure: a UID can participate in more than one pair.
        adjacency = {}
        for turn in turns:
            user, assistant = turn["user_uid"], turn["assistant_uid"]
            adjacency.setdefault(user, set()).add(assistant)
            adjacency.setdefault(assistant, set()).add(user)
        selected, pending = {uid}, [uid]
        while pending:
            for neighbor in adjacency.get(pending.pop(), ()):
                if neighbor not in selected:
                    selected.add(neighbor)
                    pending.append(neighbor)
        related_turns = sorted((t for t in turns if t["user_uid"] in selected or t["assistant_uid"] in selected), key=lambda t:t["id"])
        related = sorted((p for p in proposals if p["source_uid"] in selected), key=lambda p:p["submission_id"])
        source_rows, ledger = [], []
        for source_uid in sorted(selected):
            row = con.execute("SELECT * FROM messages WHERE uid=?", (source_uid,)).fetchone()
            if row:
                source_rows.append(dict(row))
            row = con.execute("SELECT * FROM seen WHERE uid=?", (source_uid,)).fetchone()
            if not row:
                raise CaptureRefused("forget_replay_ledger_missing")
            ledger.append(dict(row))
        if any(p["status"] not in {"queued", "blocked", "submitting", "unknown", "submitted",
                                     "revoked", "revoked_unknown", "revoked_submitted"} for p in related):
            raise CaptureRefused("forget_proposal_state_invalid")
        from .candidate_inbox_store import forgetting_plan
        span_plan = forgetting_plan(con, self.scope, selected)
        span_batches = span_plan["records"]
        digest = _digest(["ELM-FORGET/1", self.scope, locator, source_rows, ledger, related_turns, related, span_plan])
        counts = {state: sum(p["status"] == state for p in related) for state in sorted({p["status"] for p in related})}
        review_plan = span_plan["review_plan"]
        from .operator_review_store import EXTERNAL
        external = review_plan["corrupt"] or any(r["state"] in EXTERNAL for r in review_plan["records"]) or any(p["status"] in {"submitting", "unknown", "submitted", "revoked_unknown", "revoked_submitted"}
                       for p in related)
        view = {"format": "ELM-FORGET/1", "scope": self.scope, "root_id": self.binding.root_id,
                "project": self.binding.project, "plan_sha256": digest,
                "source_messages_to_remove": len(source_rows), "linked_pair_messages": len(selected),
                "local_proposal_copies": len(related), "proposal_status_counts": counts,
                "local_span_inbox_batches": len(span_batches),
                "local_operator_review_copies": len(review_plan["records"]),
                "operator_review_corruption_will_block": review_plan["corrupt"],
                "affected_operator_submission_ids": [r["submission_id"] for r in review_plan["records"]],
                "canonical_operator_proposals_removed": False,
                "corrupt_span_inbox_will_be_scrubbed_and_blocked": span_plan["corrupt"],
                "affected_span_batch_ids": [r["batch_id"] for r in span_batches],
                "retained_pair_links": len(related_turns),
                "historical_pair_links_unavailable": not bool(related_turns),
                "external_outcome_review_required": external,
                "affected_submission_ids": [p["submission_id"] for p in related],
                "limits": dict(LIMITS)}
        return view, selected, related, span_plan

    def preview(self, locator):
        with closing(self._connect()) as con:
            con.execute("BEGIN")
            view, _, _, _ = self._plan(con, locator)
            self._guard()
            return {"status": "preview_only", **view}

    def apply(self, locator, expected_plan):
        if not isinstance(expected_plan, str) or re.fullmatch("[0-9a-f]{64}", expected_plan) is None:
            raise CaptureRefused("forget_confirmation_plan_required")
        with closing(self._connect(write=True)) as con:
            try:
                con.execute("BEGIN IMMEDIATE")
                view, selected, proposals, span_plan = self._plan(con, locator)
                if view["plan_sha256"] != expected_plan:
                    raise CaptureRefused("forget_plan_changed")
                from .candidate_inbox_store import apply_forgetting
                apply_forgetting(con, span_plan)
                for proposal in proposals:
                    old = proposal["status"]
                    state = "revoked_submitted" if old in {"submitted", "revoked_submitted"} else (
                        "revoked_unknown" if old in {"submitting", "unknown", "revoked_unknown"} else "revoked")
                    con.execute("UPDATE episode_proposals SET status=?,payload='{}',evidence='{}',result=NULL,"
                                "key_hash='',object_hash='',conflict=0,error_code='source_forgotten' WHERE submission_id=?",
                                (state, proposal["submission_id"]))
                for uid in selected:
                    con.execute("DELETE FROM messages WHERE uid=?", (uid,))
                    con.execute("DELETE FROM turns WHERE user_uid=? OR assistant_uid=?", (uid, uid))
                con.execute("DELETE FROM episodes WHERE id NOT IN (SELECT episode_id FROM turns)")
                con.execute("UPDATE episodes SET turn_count=(SELECT count(*) FROM turns WHERE episode_id=episodes.id),"
                            "text_bytes=(SELECT coalesce(sum(text_bytes),0) FROM messages WHERE uid IN "
                            "(SELECT user_uid FROM turns WHERE episode_id=episodes.id UNION "
                            "SELECT assistant_uid FROM turns WHERE episode_id=episodes.id))")
                # Recompute retained conflict hints without treating revoked hashes as evidence.
                con.execute("UPDATE episode_proposals SET conflict=EXISTS(SELECT 1 FROM episode_proposals other "
                            "WHERE other.key_hash=episode_proposals.key_hash AND other.object_hash<>episode_proposals.object_hash "
                            "AND other.status NOT LIKE 'revoked%') WHERE status NOT LIKE 'revoked%'")
                self._guard()
                con.execute("COMMIT")
            except BaseException:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise
        return {"status": "source_evidence_forgotten_locally", **view,
                "replay_ids_retained": len(selected), "local_proposal_payloads_scrubbed": len(proposals),
                "local_span_inbox_batches_scrubbed": "all" if span_plan["corrupt"] else len(span_plan["records"])}
