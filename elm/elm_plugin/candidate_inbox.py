"""Optional durable, scoped review inbox for untrusted exact-span candidates.

No model, network, canonical/governance write, submission, or acceptance path.
Sources and whole configuration pins are revalidated before every disclosure.
"""
from contextlib import closing, contextmanager
import hashlib
import json
import re
import sqlite3
from uuid import uuid4

from .batch_extraction import BatchExtraction, _decode, _hash, MAX_INPUT_BYTES, MAX_ATTEMPTS
from .engine import ElmError
from .episode_capture import CaptureRefused
from .episode_forgetting import EpisodeForget
from .episode_recall import encoded
from . import candidate_inbox_store as store

CONFIG_NAME = 'elm_candidate_inbox.json'
FORMAT = 'ELM-CANDIDATE-INBOX/1'
MAX_LIFETIME_SECONDS = 86400


class CandidateInboxControl:
    """Explicit revocation works after capture/recall/batch/inbox opt-out.

    No initialization or configuration is performed. Only existing local inbox
    rows are scrubbed; request-key and ID tombstones retain replay prevention.
    """
    def __init__(self, home, binding=None):
        self.owner = EpisodeForget(home, binding)

    @contextmanager
    def transaction(self):
        with closing(self.owner._connect(write=True)) as con:
            con.execute('PRAGMA trusted_schema=OFF')
            con.execute('BEGIN IMMEDIATE')
            try:
                expected = {'schema_version': '2', 'scope': self.owner.scope,
                            'root_id': self.owner.binding.root_id, 'project': self.owner.binding.project}
                if dict(con.execute('SELECT key,value FROM meta')) != expected:
                    raise CaptureRefused('inbox_scope_or_schema_mismatch')
                try:
                    yield con
                except CaptureRefused:
                    # Only deliberate in-body refusal may persist scrub/counter
                    # writes. A failed final binding guard always rolls back.
                    self.owner._guard()
                    con.execute('COMMIT')
                    raise
                else:
                    self.owner._guard()
                    con.execute('COMMIT')
            except BaseException:
                if con.in_transaction:
                    con.execute('ROLLBACK')
                raise

    def revoke(self, batch_id=None):
        if batch_id is not None and (not isinstance(batch_id, str) or not store.ID.fullmatch(batch_id)):
            raise CaptureRefused('unknown_batch_id')
        with self.transaction() as con:
            try:
                rows = store.records(con, self.owner.scope)
            except CaptureRefused:
                store.quarantine(con)
                return {'format': FORMAT, 'status': 'revoked', 'batches': 'all',
                        'inbox_permanently_blocked': True, 'canonical_write': False,
                        'external_effects': False, 'secure_erasure': False}
            selected = rows if batch_id is None else [r for r in rows if r['batch_id'] == batch_id]
            if batch_id is not None and not selected:
                raise CaptureRefused('unknown_batch_id')
            for row in selected:
                store.scrub(con, row)
        return {'format': FORMAT, 'status': 'revoked', 'batches': len(selected),
                'canonical_write': False, 'external_effects': False, 'secure_erasure': False}


class DurableCandidateInbox:
    """Operator-only durable API. `close` releases the handle, not the records.

    `prepare(locators, request_key=...)` is idempotent across concurrent callers
    and restarts. Reuse with different sources is refused. Raw response bytes
    must match on successful replay. Tombstones cannot be recycled by this API.
    """
    def __init__(self, extractor, config_digest):
        self.extractor = extractor
        self.capture = extractor.recall.capture
        self.config_digest = config_digest
        self.path = self.capture.home / CONFIG_NAME
        self.control = CandidateInboxControl(self.capture.home, self.capture.binding)
        self._closed = False
        self.pin = _hash([self.capture.scope, self.capture.binding.root_id, self.capture.binding.project,
                          self.capture.config_digest, extractor.recall.config_digest,
                          extractor.config_digest, config_digest, extractor.author_id])

    @classmethod
    def from_recall(cls, recall):
        if recall is None:
            return None, 'recall_unavailable'
        path = recall.capture.home / CONFIG_NAME
        if path.is_symlink():
            raise CaptureRefused('unsafe_inbox_config')
        if not path.exists():
            CandidateInboxControl(recall.capture.home, recall.capture.binding).revoke()
            return None, 'disabled'
        with path.open('rb') as handle:
            raw = handle.read(2049)
        if len(raw) > 2048:
            raise CaptureRefused('invalid_inbox_config')
        try:
            value = _decode(raw.decode('utf-8'))
        except (UnicodeError, CaptureRefused):
            raise CaptureRefused('invalid_inbox_config') from None
        if isinstance(value, dict) and value.get('enabled') is False:
            CandidateInboxControl(recall.capture.home, recall.capture.binding).revoke()
            return None, 'disabled'
        if (not isinstance(value, dict) or set(value) != {'format_version', 'enabled', 'root_id', 'project', 'author_id'}
                or type(value['format_version']) is not int or value['format_version'] != 1 or value['enabled'] is not True):
            raise CaptureRefused('invalid_inbox_config')
        extractor, reason = BatchExtraction.from_recall(recall)
        if extractor is None:
            CandidateInboxControl(recall.capture.home, recall.capture.binding).revoke()
            return None, 'batch_' + reason
        if (value['root_id'] != recall.capture.binding.root_id or value['project'] != recall.capture.binding.project
                or value['author_id'] != extractor.author_id):
            raise CaptureRefused('inbox_scope_mismatch')
        instance = cls(extractor, hashlib.sha256(raw).hexdigest())
        instance._guard()
        # Merely opening a configured handle creates no tables or records.
        return instance, 'ready'

    def _guard(self):
        if self._closed:
            raise CaptureRefused('inbox_closed')
        self.extractor._guard()
        if self.path.is_symlink():
            raise CaptureRefused('inbox_config_changed')
        try:
            with self.path.open('rb') as handle:
                raw = handle.read(2049)
        except OSError:
            raise CaptureRefused('inbox_config_changed') from None
        if hashlib.sha256(raw).hexdigest() != self.config_digest:
            raise CaptureRefused('inbox_config_changed')
        return self.extractor.recall._guard()

    def _rows(self, con):
        if self._closed:
            raise CaptureRefused('inbox_closed')
        rows = store.records(con, self.capture.scope)
        try:
            self._guard()
        except CaptureRefused:
            for row in rows:
                store.scrub(con, row)
            raise CaptureRefused('inbox_revoked_configuration_unavailable') from None
        for row in rows:
            if row['state'] != 'revoked' and row['config_pin'] != self.pin:
                store.scrub(con, row)
        return rows

    def _live(self, con, row):
        if row['state'] == 'revoked':
            raise CaptureRefused('inbox_revoked')
        try:
            now = self._guard()
            if row['created'] > now or row['expires'] <= now or row['config_pin'] != self.pin:
                raise CaptureRefused('inbox_expired_or_config_changed')
            sources = self.extractor._sources(json.loads(row['locators']))
            if _hash(sources) != row['fingerprint']:
                raise CaptureRefused('inbox_source_changed')
            return sources
        except (CaptureRefused, ElmError, sqlite3.Error, OSError, UnicodeError):
            store.scrub(con, row)
            raise CaptureRefused('inbox_revoked_source_or_config_unavailable') from None

    @staticmethod
    def _find(rows, batch_id):
        if not isinstance(batch_id, str):
            raise CaptureRefused('unknown_batch_id')
        found = next((row for row in rows if row['batch_id'] == batch_id), None)
        if found is None:
            raise CaptureRefused('unknown_batch_id')
        return found

    def _checked_selections(self, row, sources):
        # Re-apply strict response validation to persistent selection metadata.
        # No truth/status fields stored in SQLite can upgrade the output.
        selections = _decode(row['selections'])
        by_id = {source['source_id']: source for source in sources}
        values = []
        try:
            for item in selections:
                if (not isinstance(item, dict) or set(item) != {'source_id', 'start', 'end', 'kind', 'topic', 'interpretation'}
                        or type(item['start']) is not int or type(item['end']) is not int):
                    raise CaptureRefused('inbox_selection_integrity_failed')
                source = by_id[item['source_id']]
                values.append({**item, 'quote': source['text'][item['start']:item['end']]})
        except (KeyError, TypeError, IndexError):
            raise CaptureRefused('inbox_selection_integrity_failed') from None
        from .batch_extraction import FORMAT as BATCH_FORMAT
        return self.extractor._selections(row['batch_id'], {'format': BATCH_FORMAT,
            'batch_id': row['batch_id'], 'candidates': values}, sources)

    def _result(self, con, row, sources):
        try:
            selections = self._checked_selections(row, sources)
            result = self.extractor._result(row['batch_id'], selections, sources)
        except CaptureRefused:
            store.scrub(con, row)
            raise
        if self._live(con, row) != sources:
            store.scrub(con, row)
            raise CaptureRefused('inbox_source_changed')
        return result

    def prepare(self, locators, *, request_key):
        if not isinstance(request_key, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', request_key):
            raise CaptureRefused('invalid_inbox_request_key')
        # The process-local preparer retains its own small bounds and is used
        # only to validate locators/request size; no pending local batch used.
        if (not isinstance(locators, list) or not 1 <= len(locators) <= 8
                or any(not isinstance(x, str) or len(x) > 256 for x in locators)
                or len(set(locators)) != len(locators)):
            raise CaptureRefused('invalid_batch_locators')
        key_hash = _hash([self.capture.scope, request_key])
        with self.control.transaction() as con:
            rows = self._rows(con)
            row = next((r for r in rows if r['request_key_hash'] == key_hash), None)
            if row is not None:
                sources = self._live(con, row)
                if json.loads(row['locators']) != locators:
                    raise CaptureRefused('inbox_request_key_conflict')
                request = self.extractor._request(row['batch_id'], sources)
            else:
                if len(rows) >= store.MAX_RECORDS:
                    raise CaptureRefused('inbox_lifetime_capacity_reached')
                sources = self.extractor._sources(locators)
                now = self._guard()
                row = dict(batch_id='batch_' + str(uuid4()), request_key_hash=key_hash,
                           state='pending', locators=encoded(locators), fingerprint=_hash(sources),
                           config_pin=self.pin, created=now,
                           expires=min(now + MAX_LIFETIME_SECONDS, *[s['retrieval_expires_at'] for s in sources]),
                           attempts=0, response_digest=None, selections='[]', record_digest='')
                if row['expires'] <= now:
                    raise CaptureRefused('inbox_source_unavailable')
                request = self.extractor._request(row['batch_id'], sources)
            if len(encoded(request).encode()) > MAX_INPUT_BYTES:
                raise CaptureRefused('batch_input_too_large')
            if self.extractor._sources(locators) != sources:
                raise CaptureRefused('inbox_source_changed')
            self._guard()
            if not any(r['batch_id'] == row['batch_id'] for r in rows):
                store.initialize(con)
                store.save(con, row, insert=True)
            return request

    def validate(self, batch_id, raw_response):
        with self.control.transaction() as con:
            row = self._find(self._rows(con), batch_id)
            sources = self._live(con, row)
            if row['state'] == 'failed':
                raise CaptureRefused('batch_attempts_exhausted')
            if row['state'] == 'validated':
                _decode(raw_response)
                if hashlib.sha256(raw_response.encode()).hexdigest() != row['response_digest']:
                    raise CaptureRefused('batch_already_validated_different_response')
                return self._result(con, row, sources)
            row['attempts'] += 1
            try:
                selections = self.extractor._selections(batch_id, _decode(raw_response), sources)
                result = self.extractor._result(batch_id, selections, sources)
                if self._live(con, row) != sources:
                    raise CaptureRefused('inbox_source_changed')
            except (CaptureRefused, UnicodeError, RecursionError):
                if row['state'] != 'revoked':
                    row['state'] = 'failed' if row['attempts'] >= MAX_ATTEMPTS else 'pending'
                    store.save(con, row)
                raise
            row.update(state='validated', selections=encoded(selections),
                       response_digest=hashlib.sha256(raw_response.encode()).hexdigest())
            store.save(con, row)
            return result

    def review(self, batch_id):
        with self.control.transaction() as con:
            row = self._find(self._rows(con), batch_id)
            sources = self._live(con, row)
            if row['state'] != 'validated':
                raise CaptureRefused('batch_not_validated')
            return self._result(con, row, sources)

    def list_batches(self):
        """Metadata-only inventory; source validation occurs even without quotes.

        Invalid/expired entries are tombstoned. No source locators or labels
        are exposed in the inventory. Use review for full current context.
        """
        with self.control.transaction() as con:
            rows = self._rows(con)
            for row in rows:
                if row['state'] != 'revoked':
                    try:
                        sources = self._live(con, row)
                        if row['state'] == 'validated':
                            self._result(con, row, sources)
                    except CaptureRefused:
                        store.scrub(con, row)
            self._rows(con)  # Final configuration guard before inventory disclosure.
            return {'format': FORMAT, 'scope': self.capture.scope, 'accepted_memory': False,
                    'canonical_write': False, 'governance_submission': False,
                    'records': [{'batch_id': row['batch_id'], 'state': row['state'],
                                 'created_at': row['created'], 'expires_at': row['expires'],
                                 'attempts': row['attempts']} for row in rows]}

    def revoke(self, batch_id):
        return self.control.revoke(batch_id)

    def revoke_all(self):
        return self.control.revoke()

    def close(self):
        self._closed = True
        self.extractor.close()
