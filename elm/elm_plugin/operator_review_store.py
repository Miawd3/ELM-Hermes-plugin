"""Bounded operator interpretations, not truth. Callers own the episode transaction.

Digests detect inconsistent storage, not a malicious database administrator.
Tombstones retain IDs/outcome uncertainty; no API recycles them.
"""
import hashlib
import json
import math
import re
from .episode_capture import CaptureRefused
from .episode_recall import encoded

TABLE = 'operator_span_reviews'
MAX_RECORDS = 128
COLUMNS = ('review_id', 'request_key_hash', 'batch_id', 'candidate_id', 'config_pin',
           'state', 'semantics', 'payload', 'plan_digest', 'created', 'expires',
           'submission_id', 'replaces_review_id', 'record_digest')
HEX = re.compile(r'[0-9a-f]{64}\Z')
REVIEW = re.compile(r'review_[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z')
SUBMISSION = re.compile(r'submission_[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z')
STATES = {'prepared', 'submitting', 'submitted', 'unknown', 'revoked', 'revoked_unknown', 'revoked_submitted'}
UNCERTAIN = {'submitting', 'unknown', 'revoked_unknown'}
EXTERNAL = UNCERTAIN | {'submitted', 'revoked_submitted'}


def exists(con):
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE name=?", (TABLE,)).fetchone())


def initialize(con):
    con.execute('CREATE TABLE IF NOT EXISTS operator_span_reviews ('
                'review_id TEXT PRIMARY KEY, request_key_hash TEXT NOT NULL UNIQUE, '
                'batch_id TEXT NOT NULL, candidate_id TEXT NOT NULL, config_pin TEXT NOT NULL, '
                'state TEXT NOT NULL, semantics TEXT NOT NULL, payload TEXT NOT NULL, '
                'plan_digest TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL, '
                'submission_id TEXT NOT NULL UNIQUE, replaces_review_id TEXT, record_digest TEXT NOT NULL)')


def digest(row):
    return hashlib.sha256(encoded([row[k] for k in COLUMNS[:-1]]).encode()).hexdigest()


def checked(row):
    value = dict(row)
    if (set(value) != set(COLUMNS) or not isinstance(value['review_id'], str)
            or not REVIEW.fullmatch(value['review_id']) or not isinstance(value['submission_id'], str)
            or not SUBMISSION.fullmatch(value['submission_id']) or value['state'] not in STATES
            or any(not isinstance(value[k], str) or not HEX.fullmatch(value[k]) for k in ('request_key_hash', 'plan_digest'))
            or any(type(value[k]) not in (int, float) or not math.isfinite(value[k]) for k in ('created', 'expires'))
            or not value['created'] < value['expires'] <= value['created'] + 86400
            or any(not isinstance(value[k], str) or len(value[k]) > 16384 for k in ('semantics', 'payload'))
            or value['replaces_review_id'] is not None and (not isinstance(value['replaces_review_id'], str)
                                                        or not REVIEW.fullmatch(value['replaces_review_id']))
            or value['record_digest'] != digest(value)):
        raise CaptureRefused('operator_review_integrity_failed')
    if value['state'].startswith('revoked'):
        if any(value[k] for k in ('batch_id', 'candidate_id', 'config_pin')) or value['semantics'] != '{}' or value['payload'] != '{}':
            raise CaptureRefused('operator_review_integrity_failed')
    else:
        from .candidate_inbox_store import ID
        if (not isinstance(value['batch_id'], str) or not ID.fullmatch(value['batch_id'])
                or not isinstance(value['candidate_id'], str) or not re.fullmatch(r'candidate_[0-9a-f]{64}', value['candidate_id'])
                or not isinstance(value['config_pin'], str) or not HEX.fullmatch(value['config_pin'])):
            raise CaptureRefused('operator_review_integrity_failed')
        try:
            if not isinstance(json.loads(value['semantics']), dict) or not isinstance(json.loads(value['payload']), dict):
                raise ValueError()
        except (ValueError, RecursionError):
            raise CaptureRefused('operator_review_integrity_failed') from None
    return value


def records(con):
    if con.execute("SELECT 1 FROM sqlite_master WHERE name='operator_review_blocked'").fetchone():
        raise CaptureRefused('operator_review_permanently_blocked_after_corruption')
    if not exists(con):
        return []
    rows = con.execute('SELECT * FROM operator_span_reviews ORDER BY created,review_id').fetchmany(MAX_RECORDS + 1)
    if len(rows) > MAX_RECORDS:
        raise CaptureRefused('operator_review_capacity_exceeded')
    return [checked(row) for row in rows]


def save(con, row, *, insert=False):
    row['record_digest'] = digest(row)
    if insert:
        con.execute('INSERT INTO operator_span_reviews VALUES (' + ','.join('?' for _ in COLUMNS) + ')', tuple(row[k] for k in COLUMNS))
    else:
        con.execute('UPDATE operator_span_reviews SET ' + ','.join(k+'=?' for k in COLUMNS[1:]) + ' WHERE review_id=?',
                    (*[row[k] for k in COLUMNS[1:]], row['review_id']))


def scrub(con, row):
    state = 'revoked_submitted' if row['state'] in {'submitted', 'revoked_submitted'} else (
        'revoked_unknown' if row['state'] in UNCERTAIN else 'revoked')
    row.update(state=state, batch_id='', candidate_id='', config_pin='', semantics='{}', payload='{}')
    save(con, row)


def quarantine(con):
    con.execute('CREATE TABLE IF NOT EXISTS operator_review_blocked (reason TEXT NOT NULL)')
    con.execute('DELETE FROM operator_review_blocked')
    con.execute("INSERT INTO operator_review_blocked VALUES ('integrity_failure_external_outcome_unknown')")
    if exists(con):
        con.execute('DELETE FROM operator_span_reviews')


def plan(con, batch_ids=None):
    try:
        rows = records(con)
        return {'corrupt': False, 'records': [r for r in rows if not r['state'].startswith('revoked')
                                            and (batch_ids is None or r['batch_id'] in batch_ids)]}
    except CaptureRefused:
        snapshot = con.execute('SELECT * FROM operator_span_reviews LIMIT ?', (MAX_RECORDS + 1,)).fetchall() if exists(con) else []
        count = con.execute('SELECT count(*) FROM operator_span_reviews').fetchone()[0] if exists(con) else 0
        return {'corrupt': True, 'records': [], 'count': count,
                'snapshot_hash': hashlib.sha256(repr([tuple(r) for r in snapshot]).encode()).hexdigest()}


def apply(con, value):
    if value['corrupt']:
        quarantine(con)
    else:
        for row in value['records']:
            scrub(con, row)


def revoke_batch(con, batch_id=None):
    apply(con, plan(con, None if batch_id is None else {batch_id}))
