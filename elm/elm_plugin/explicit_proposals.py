"""Narrow deterministic marker grammar. Output is untrusted proposals, not truth."""
from datetime import datetime, timezone
import hashlib
import re

EXTRACTOR_VERSION = "explicit-markers/2-metadata"
MARKER = re.compile(r"\A(Remember|Preference|Decision): ([a-z][a-z0-9_.-]{0,63}) = (\S(?:[^\r\n]{0,998}\S)?)\Z")


def marker_proposal(*, message, episode, scope, root_id, project, allowed_author, submission_id):
    """Do not parse quotes, natural language, assistant output or unnamed authors.

    This cannot prove an unquoted pasted string was authored by its sender. It
    records precisely who supplied the text and never interprets it as approval.
    """
    if message["role"] != "user" or not allowed_author or message["author_id"] != allowed_author:
        return None
    text = message["text"]
    if "[redacted]" in text or "\x00" in text or len(text.splitlines()) != 1:
        return None
    match = MARKER.fullmatch(text)
    if not match:
        return None
    kind, key, value = match.groups()
    if kind == "Decision":
        subject, predicate = "project:" + project, "proposed_decision." + key
    else:
        subject = "speaker:" + allowed_author
        predicate = ("preference." if kind == "Preference" else "explicit_note.") + key
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    uri = f"urn:elm:episode:{scope}:{episode['id']}:message:{message['uid']}"
    evidence = {
        "extractor_version": EXTRACTOR_VERSION, "scope": scope, "root_id": root_id,
        "project": project, "episode_id": episode["id"], "session_id": episode["session"],
        "source_uid": message["uid"], "source_role": "user", "source_author_id": allowed_author,
        "source_uri": uri, "source_text": text, "source_sha256": digest,
        "source_span": [0, len(text)], "value_span": [match.start(3), match.end(3)],
        "captured_at": message["captured"], "source_expires_at": message["expires"], "marker": kind,
        "authority": "untrusted_source_statement", "is_authorization": False,
        "source_speaker_id": message["source_speaker_id"] if "source_speaker_id" in message.keys() else None,
        "source_timestamp": message["source_timestamp"] if "source_timestamp" in message.keys() else None,
        "source_metadata_basis": "optional_caller_observations",
        "valid_from_basis": "capture_time_placeholder_not_fact_validity",
    }
    payload = {
        "submission_id": submission_id, "project": project, "subject": subject,
        "predicate": predicate, "object": value,
        "valid_from": datetime.fromtimestamp(message["captured"], timezone.utc).isoformat(timespec="microseconds"),
        "sensitivity": "restricted",
        "rationale": (
            f"Deterministic {EXTRACTOR_VERSION} candidate, not accepted memory or authorization.\n"
            "valid_from records capture time, not established source event time or fact validity.\n"
            f"Supplied by user author {allowed_author}; source UID {message['uid']}; "
            f"episode {episode['id']}; session {episode['session']}; scope {scope}; root {root_id}.\n"
            f"Exact captured source, characters 0:{len(text)}, SHA-256 {digest}:\n{text}"
        ),
        "source_refs": [uri + "@sha256:" + digest],
        "evidence": [{"kind": "document_section", "source_uri": uri,
                      "content_sha256": digest, "excerpt_sha256": digest, "sensitivity": "restricted"}],
    }
    return {"payload": payload, "evidence": evidence}
