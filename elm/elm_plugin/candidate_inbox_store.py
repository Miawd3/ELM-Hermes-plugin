"""Bounded storage helpers for quarantined spans. No source copies or dispatch.

All callers hold a transaction on the existing scoped episode database. The
unkeyed record digest detects inconsistency, not a hostile database owner.
"""
import hashlib
import json
import math
import re

from .episode_capture import CaptureRefused
from .episode_recall import LOCATOR_PATTERN, encoded
from .batch_extraction import MAX_SOURCES, MAX_ATTEMPTS, MAX_CANDIDATES, _decode

TABLE = 'span_candidate_inbox'
MAX_RECORDS = 128  # Lifetime per profile scope, including replay tombstones.
COLUMNS = ('batch_id', 'request_key_hash', 'state', 'locators', 'fingerprint',
           'config_pin', 'created', 'expires', 'attempts', 'response_digest',
           'selections', 'record_digest')
HEX = re.compile(r'[0-9a-f]{64}\Z')
ID = re.compile(r'batch_[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z')


def digest(row):
    return hashlib.sha256(encoded([row[k] for k in COLUMNS[:-1]]).encode()).hexdigest()


def exists(con):
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone())


def initialize(con):
    con.execute('CREATE TABLE IF NOT EXISTS span_candidate_inbox ('
                'batch_id TEXT PRIMARY KEY, request_key_hash TEXT NOT NULL UNIQUE, '
                'state TEXT NOT NULL, locators TEXT NOT NULL, fingerprint TEXT NOT NULL, '
                'config_pin TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL, '
                'attempts INTEGER NOT NULL, response_digest TEXT, selections TEXT NOT NULL, '
                'record_digest TEXT NOT NULL)')


def checked(row, scope):
    value = dict(row)
    if (set(value) != set(COLUMNS)
            or not isinstance(value['batch_id'], str) or not ID.fullmatch(value['batch_id'])
            or not isinstance(value['request_key_hash'], str) or not HEX.fullmatch(value['request_key_hash'])
            or value['state'] not in ('pending', 'validated', 'failed', 'revoked')
            or type(value['attempts']) is not int or not 0 <= value['attempts'] <= MAX_ATTEMPTS
            or any(type(value[k]) not in (int, float) or not math.isfinite(value[k]) for k in ('created', 'expires'))
            or value['expires'] <= value['created']
            or value['expires'] > value['created'] + 86400
            or any(not isinstance(value[k], str) or len(value[k]) > 16384 for k in ('locators', 'selections'))
            or value['record_digest'] != digest(value)):
        raise CaptureRefused('inbox_record_integrity_failed')
    locators, selections = _decode(value['locators']), _decode(value['selections'])
    if not isinstance(locators, list) or not isinstance(selections, list) or len(selections) > MAX_CANDIDATES:
        raise CaptureRefused('inbox_record_integrity_failed')
    if value['state'] == 'revoked':
        if (locators or selections or value['fingerprint'] or value['config_pin']
                or value['response_digest'] is not None):
            raise CaptureRefused('inbox_record_integrity_failed')
    else:
        if (not 1 <= len(locators) <= MAX_SOURCES
                or any(not isinstance(x, str) or len(x) > 256 for x in locators)
                or len(set(locators)) != len(locators)
                or any(not (m := re.fullmatch(LOCATOR_PATTERN, x)) or m[1] != scope for x in locators)
                or any(not isinstance(value[k], str) or not HEX.fullmatch(value[k]) for k in ('fingerprint', 'config_pin'))):
            raise CaptureRefused('inbox_record_integrity_failed')
        if value['state'] == 'validated':
            if (not isinstance(value['response_digest'], str) or not HEX.fullmatch(value['response_digest'])
                    or value['attempts'] == 0):
                raise CaptureRefused('inbox_record_integrity_failed')
        elif selections or value['response_digest'] is not None:
            raise CaptureRefused('inbox_record_integrity_failed')
        if value['state'] == 'failed' and value['attempts'] != MAX_ATTEMPTS:
            raise CaptureRefused('inbox_record_integrity_failed')
    return value


def records(con, scope):
    if con.execute("SELECT 1 FROM sqlite_master WHERE name='span_candidate_inbox_blocked'").fetchone():
        raise CaptureRefused('inbox_permanently_blocked_after_corruption')
    if not exists(con):
        return []
    rows = con.execute('SELECT * FROM span_candidate_inbox ORDER BY created,batch_id').fetchmany(MAX_RECORDS + 1)
    if len(rows) > MAX_RECORDS:
        raise CaptureRefused('inbox_store_capacity_exceeded')
    return [checked(row, scope) for row in rows]


def save(con, row, *, insert=False):
    row['record_digest'] = digest(row)
    if insert:
        con.execute('INSERT INTO span_candidate_inbox VALUES (' + ','.join('?' for _ in COLUMNS) + ')',
                    tuple(row[k] for k in COLUMNS))
    else:
        con.execute('UPDATE span_candidate_inbox SET ' + ','.join(k+'=?' for k in COLUMNS[1:]) + ' WHERE batch_id=?',
                    (*[row[k] for k in COLUMNS[1:]], row['batch_id']))


def scrub(con, row):
    from .operator_review_store import revoke_batch
    revoke_batch(con, row['batch_id'])
    row.update(state='revoked', locators='[]', fingerprint='', config_pin='', response_digest=None, selections='[]')
    save(con, row)


def quarantine(con):
    """Erase unusable derivatives, retain a permanent whole-inbox replay gate.

    The source cleanup path must not depend on optional derivative integrity.
    No API resets this gate; restoring/replacing local databases is outside it.
    """
    from .operator_review_store import revoke_batch
    revoke_batch(con)
    con.execute('CREATE TABLE IF NOT EXISTS span_candidate_inbox_blocked (reason TEXT NOT NULL)')
    con.execute('DELETE FROM span_candidate_inbox_blocked')
    con.execute("INSERT INTO span_candidate_inbox_blocked VALUES ('derivative_integrity_failure')")
    if exists(con):
        con.execute('DELETE FROM span_candidate_inbox')


def forgetting_plan(con, scope, selected):
    try:
        rows = records(con, scope)
        matches = [row for row in rows if row['state'] != 'revoked'
                   and any(re.fullmatch(LOCATOR_PATTERN, loc)[3] in selected for loc in json.loads(row['locators']))]
        from .operator_review_store import plan
        return {'corrupt': False, 'records': matches, 'review_plan': plan(con, {r['batch_id'] for r in matches})}
    except CaptureRefused:
        # Preview is read-only. Bind the reviewed cleanup plan to a bounded
        # snapshot without exposing possibly corrupt content in its output.
        snapshot = con.execute('SELECT * FROM span_candidate_inbox LIMIT ?', (MAX_RECORDS + 1,)).fetchall() if exists(con) else []
        count = con.execute('SELECT count(*) FROM span_candidate_inbox').fetchone()[0] if exists(con) else 0
        from .operator_review_store import plan
        return {'corrupt': True, 'records': [], 'count': count, 'review_plan': plan(con),
                'snapshot_hash': hashlib.sha256(repr([tuple(r) for r in snapshot]).encode()).hexdigest()}


def apply_forgetting(con, plan):
    from .operator_review_store import apply
    apply(con, plan['review_plan'])
    if plan['corrupt']:
        quarantine(con)
    else:
        for row in plan['records']:
            scrub(con, row)


def expire(con, now):
    if not exists(con):
        return
    scope = dict(con.execute('SELECT key,value FROM meta'))['scope']
    original_factory = con.row_factory
    try:
        import sqlite3
        con.row_factory = sqlite3.Row
        try:
            rows = records(con, scope)
        except CaptureRefused:
            quarantine(con)
            return
        for row in rows:
            if row['state'] != 'revoked' and row['expires'] <= now:
                scrub(con, row)
    finally:
        con.row_factory = original_factory
