"""Explicit operator semantics -> existing pending governance proposal.

No extractor labels are interpreted. Exact evidence is not semantic authority.
Not registered with the provider or any model tool. No transport or acceptance.
"""
from datetime import datetime
import hashlib
import json
import re
import sqlite3
from uuid import uuid4
from .batch_extraction import _decode, _hash
from .candidate_inbox import CandidateInboxControl
from .episode_capture import CaptureRefused
from .episode_recall import encoded
from .engine import ElmError, run_engine
from . import operator_review_store as store
from .submission_reconciliation import observe_submission

CONFIG_NAME = 'elm_operator_review.json'
FORMAT = 'ELM-OPERATOR-REVIEW/1'
SEMANTIC_FIELDS = {'subject', 'predicate', 'object', 'scope', 'valid_from', 'context', 'attribution', 'uncertainty'}
LIMITS = {'subject': 200, 'predicate': 100, 'object': 1000, 'scope': 100,
          'valid_from': 50, 'context': 1000, 'attribution': 300, 'uncertainty': 500}


class ReviewBridgeControl:
    """Local revocation after opt-out; cannot erase pending canonical proposals."""
    def __init__(self, home, binding=None):
        self.control = CandidateInboxControl(home, binding)

    def revoke(self, review_id=None):
        if review_id is not None and (not isinstance(review_id, str) or not store.REVIEW.fullmatch(review_id)):
            raise CaptureRefused('unknown_operator_review')
        with self.control.transaction() as con:
            value = store.plan(con)
            if review_id is not None and not value['corrupt']:
                # Include tombstones to make explicit revocation replay-safe.
                value['records'] = [r for r in store.records(con) if r['review_id'] == review_id]
                if not value['records']:
                    raise CaptureRefused('unknown_operator_review')
            external = value['corrupt'] or any(r['state'] in store.EXTERNAL for r in value['records'])
            store.apply(con, value)
            return {'format': FORMAT, 'status': 'revoked', 'reviews': len(value['records']),
                    'external_outcome_review_required': external, 'canonical_proposals_removed': False,
                    'accepted_claims_removed': False, 'secure_erasure': False,
                    'permanently_blocked': value['corrupt']}


class OperatorReviewBridge:
    def __init__(self, inbox, operator_id, digest):
        self.inbox = inbox
        self.capture = inbox.capture
        self.operator_id = operator_id
        self.config_digest = digest
        self.path = self.capture.home / CONFIG_NAME
        self.pin = _hash([inbox.pin, operator_id, digest])

    @classmethod
    def from_inbox(cls, inbox):
        if inbox is None:
            return None, 'inbox_unavailable'
        path = inbox.capture.home / CONFIG_NAME
        if path.is_symlink():
            raise CaptureRefused('unsafe_operator_review_config')
        if not path.exists():
            ReviewBridgeControl(inbox.capture.home, inbox.capture.binding).revoke()
            return None, 'disabled'
        with path.open('rb') as handle:
            raw = handle.read(2049)
        if len(raw) > 2048:
            raise CaptureRefused('invalid_operator_review_config')
        try:
            value = _decode(raw.decode('utf-8'))
        except (UnicodeError, CaptureRefused):
            raise CaptureRefused('invalid_operator_review_config') from None
        if isinstance(value, dict) and value.get('enabled') is False:
            ReviewBridgeControl(inbox.capture.home, inbox.capture.binding).revoke()
            return None, 'disabled'
        if (not isinstance(value, dict) or set(value) != {'format_version', 'enabled', 'root_id', 'project', 'operator_id'}
                or type(value['format_version']) is not int or value['format_version'] != 1 or value['enabled'] is not True
                or value['root_id'] != inbox.capture.binding.root_id or value['project'] != inbox.capture.binding.project
                or not isinstance(value['operator_id'], str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', value['operator_id'])):
            raise CaptureRefused('invalid_operator_review_config')
        bridge = cls(inbox, value['operator_id'], hashlib.sha256(raw).hexdigest())
        bridge._guard()
        return bridge, 'ready'

    def _guard(self):
        now = self.inbox._guard()
        if self.capture.binding.mode not in {'proposal-only', 'autonomous'}:
            raise CaptureRefused('operator_review_mode_blocks_submission')
        if self.path.is_symlink():
            raise CaptureRefused('operator_review_config_changed')
        try:
            with self.path.open('rb') as handle:
                raw = handle.read(2049)
        except OSError:
            raise CaptureRefused('operator_review_config_changed') from None
        if hashlib.sha256(raw).hexdigest() != self.config_digest:
            raise CaptureRefused('operator_review_config_changed')
        return now

    def _rows(self, con):
        if self.inbox._closed:
            raise CaptureRefused('operator_review_handle_closed')
        rows = store.records(con)
        try:
            self._guard()
        except (CaptureRefused, ElmError):
            for row in rows:
                store.scrub(con, row)
            raise CaptureRefused('operator_reviews_revoked_configuration_unavailable') from None
        for row in rows:
            if not row['state'].startswith('revoked') and row['config_pin'] != self.pin:
                store.scrub(con, row)
        return rows

    @staticmethod
    def _find(rows, review_id):
        row = next((r for r in rows if r['review_id'] == review_id), None)
        if row is None:
            raise CaptureRefused('unknown_operator_review')
        return row

    def _semantics(self, value):
        if (not isinstance(value, dict) or set(value) != SEMANTIC_FIELDS
                or any(not isinstance(value[k], str) or not value[k].strip() or value[k] != value[k].strip()
                       or len(value[k]) > LIMITS[k] or any(ord(c) < 32 or ord(c) == 127 for c in value[k]) for k in SEMANTIC_FIELDS)
                or value['scope'] != 'project:' + self.capture.binding.project):
            raise CaptureRefused('explicit_operator_meaning_scope_context_required')
        try:
            when = datetime.fromisoformat(value['valid_from'].replace('Z', '+00:00'))
            if when.tzinfo is None or when.utcoffset() is None:
                raise ValueError()
        except ValueError:
            raise CaptureRefused('explicit_operator_valid_from_required') from None
        return dict(value)

    def _source(self, con, batch_id, candidate_id):
        row = self.inbox._find(self.inbox._rows(con), batch_id)
        sources = self.inbox._live(con, row)
        if row['state'] != 'validated':
            raise CaptureRefused('batch_not_validated')
        bundle = self.inbox._result(con, row, sources)
        candidate = next((c for c in bundle['candidates'] if c['candidate_id'] == candidate_id), None)
        if candidate is None:
            raise CaptureRefused('unknown_span_candidate')
        source = next(s for s in sources if s['source_id'] == candidate['selection']['source_id'])
        return row, bundle, candidate, source

    def _payload(self, row, source, candidate, semantics):
        # Closed payload: no acceptance, authority escalation or supersession.
        uri = f"urn:elm:episode:{self.capture.scope}:{source['episode_id']}:message:{source['message_uid']}"
        content_hash = hashlib.sha256(source['text'].encode()).hexdigest()
        excerpt_hash = hashlib.sha256(candidate['selection']['quote'].encode()).hexdigest()
        return {'submission_id': row['submission_id'], 'project': self.capture.binding.project,
                'subject': semantics['subject'], 'predicate': semantics['predicate'], 'object': semantics['object'],
                'valid_from': semantics['valid_from'], 'sensitivity': 'restricted',
                'rationale': 'Operator interpretation, not verified truth or authorization. Source identity is not authenticated. '
                    'Citation validates stored bytes only. Pending governance review, not accepted memory.\n'
                    + f"Operator {self.operator_id}; review {row['review_id']}; candidate {candidate['candidate_id']}; "
                    + f"scope {semantics['scope']}; span {candidate['selection']['start']}:{candidate['selection']['end']}.\n"
                    + f"Context: {semantics['context']}\nAttribution: {semantics['attribution']}\n"
                    + f"Uncertainty: {semantics['uncertainty']}\n"
                    + f"Replaces local review: {row['replaces_review_id'] or 'none'}. No canonical supersession or deletion.",
                'source_refs': [uri + '@sha256:' + content_hash],
                'evidence': [{'kind': 'document_section', 'source_uri': uri, 'content_sha256': content_hash,
                              'excerpt_sha256': excerpt_hash, 'sensitivity': 'restricted'}]}

    @staticmethod
    def _plan(row, batch):
        return _hash([FORMAT, row['review_id'], row['batch_id'], row['candidate_id'], row['config_pin'],
                      row['semantics'], row['payload'], row['created'], row['expires'], row['replaces_review_id'],
                      batch['fingerprint'], batch['response_digest']])

    def _live(self, con, row):
        if row['state'].startswith('revoked'):
            raise CaptureRefused('operator_review_revoked')
        try:
            now = self._guard()
            if row['config_pin'] != self.pin or row['created'] > now or row['expires'] <= now:
                raise CaptureRefused('operator_review_expired_or_config_changed')
            batch, bundle, candidate, source = self._source(con, row['batch_id'], row['candidate_id'])
            semantics = self._semantics(_decode(row['semantics']))
            if (_decode(row['payload']) != self._payload(row, source, candidate, semantics)
                    or row['plan_digest'] != self._plan(row, batch)):
                raise CaptureRefused('operator_review_integrity_failed')
            self._guard()
            return bundle
        except (CaptureRefused, ElmError, sqlite3.Error, OSError, UnicodeError, KeyError, ValueError):
            # A source scrub may already have changed the stored status.
            current = self._find(store.records(con), row['review_id'])
            if not current['state'].startswith('revoked'):
                store.scrub(con, row)
            raise CaptureRefused('operator_review_revoked_source_or_config_unavailable') from None

    @staticmethod
    def _receipt(row):
        return {'format': FORMAT, 'review_id': row['review_id'], 'submission_id': row['submission_id'],
                'state': row['state'], 'accepted_memory': False, 'is_authorization': False,
                'external_transmission': False, 'canonical_proposals_removed': False,
                'acceptance_performed': False, 'current_canonical_status': 'not_inspected',
                'manual_outcome_review_required': row['state'] in store.UNCERTAIN,
                'governance_submission_recorded': row['state'] in {'submitted', 'revoked_submitted'}}

    def _view(self, con, row):
        bundle = self._live(con, row)
        return {**self._receipt(row), 'plan_sha256': row['plan_digest'], 'operator_id': self.operator_id,
                'operator_identity_authenticated': False, 'operator_semantics': _decode(row['semantics']),
                'proposal_payload': _decode(row['payload']), 'evidence': bundle,
                'requires_explicit_confirmation': row['state'] == 'prepared',
                'canonical_effect': 'pending_proposal_only_after_explicit_submit',
                'replaces_review_id': row['replaces_review_id'], 'canonical_supersession': False}

    def prepare(self, batch_id, candidate_id, semantics, *, request_key, replaces_review_id=None):
        if not isinstance(request_key, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', request_key):
            raise CaptureRefused('invalid_operator_review_request_key')
        semantics = self._semantics(semantics)
        key_hash = _hash([self.capture.scope, request_key])
        with self.inbox.control.transaction() as con:
            rows = self._rows(con)
            prior = next((r for r in rows if r['request_key_hash'] == key_hash), None)
            if prior is not None:
                self._live(con, prior)
                if (prior['batch_id'] != batch_id or prior['candidate_id'] != candidate_id
                        or _decode(prior['semantics']) != semantics or prior['replaces_review_id'] != replaces_review_id):
                    raise CaptureRefused('operator_review_request_key_conflict')
                return self._view(con, prior)
            if len(rows) >= store.MAX_RECORDS:
                raise CaptureRefused('operator_review_lifetime_capacity_reached')
            if any(r['state'] in store.UNCERTAIN for r in rows):
                raise CaptureRefused('unresolved_previous_operator_submission')
            if replaces_review_id is not None:
                prior = self._find(rows, replaces_review_id)
                if prior['state'] != 'prepared':
                    raise CaptureRefused('correction_requires_explicit_revocation_then_new_review')
                # Digest confirmation of a replacement is deferred to submit; old
                # draft cannot remain independently submittable after correction.
                if prior['batch_id'] != batch_id or prior['candidate_id'] != candidate_id:
                    raise CaptureRefused('correction_candidate_mismatch')
            else:
                prior = None
            batch, bundle, candidate, source = self._source(con, batch_id, candidate_id)
            now = self._guard()
            row = {'review_id': 'review_' + str(uuid4()), 'request_key_hash': key_hash,
                   'batch_id': batch_id, 'candidate_id': candidate_id, 'config_pin': self.pin, 'state': 'prepared',
                   'semantics': encoded(semantics), 'payload': '{}', 'plan_digest': '', 'created': now,
                   'expires': batch['expires'], 'submission_id': 'submission_' + str(uuid4()),
                   'replaces_review_id': replaces_review_id, 'record_digest': ''}
            row['payload'] = encoded(self._payload(row, source, candidate, semantics))
            row['plan_digest'] = self._plan(row, batch)
            self._source(con, batch_id, candidate_id)
            self._guard()
            if prior:
                store.scrub(con, prior)
            store.initialize(con)
            store.save(con, row, insert=True)
            return self._view(con, row)

    def inspect(self, review_id):
        with self.inbox.control.transaction() as con:
            row = self._find(self._rows(con), review_id)
            return self._view(con, row)

    def list_reviews(self):
        with self.inbox.control.transaction() as con:
            rows = self._rows(con)
            for row in rows:
                if not row['state'].startswith('revoked'):
                    try:
                        self._live(con, row)
                    except CaptureRefused:
                        pass
            self._guard()
            return {'format': FORMAT, 'records': [self._receipt(r) for r in store.records(con)]}

    def reconcile(self, review_id, expected_plan):
        """Resolve only a verified historical submission. Never sends/retries.

        Live source/plan validation is deliberately required in this version.
        Scrubbed, expired or changed plans cannot prove payload equivalence and
        remain blocked. Canonical status is a momentary observation, not truth.
        """
        if not isinstance(expected_plan, str) or not store.HEX.fullmatch(expected_plan):
            raise CaptureRefused('operator_review_plan_required')
        with self.inbox.control.transaction() as con:
            row = self._find(self._rows(con), review_id)
            if row['plan_digest'] != expected_plan:
                raise CaptureRefused('operator_review_plan_changed')
            if row['state'] not in {'submitting', 'unknown', 'submitted'}:
                raise CaptureRefused('operator_review_payload_or_submission_intent_unavailable')
            self._live(con, row)
            observation = observe_submission(self.capture.home, self.capture.binding, row)
            self._guard()
            if observation['classification'] == 'matched':
                row['state'] = 'submitted'
                store.save(con, row)
            # The receipt records submission only. Even if an external operator
            # accepted the proposal, this operation neither accepts nor verifies
            # accepted claims; no source/semantic text leaves in the receipt.
            return {**self._receipt(row), 'reconciliation': observation,
                    'submission_performed': False, 'retry_permitted': False,
                    'current_canonical_status': 'snapshot_only_see_reconciliation' if observation['authoritative_snapshot'] else 'not_verified',
                    'acceptance_observed_in_governance': observation['classification'] == 'matched'
                        and observation['observed_canonical_status'] == 'accepted'}

    def submit(self, review_id, expected_plan, *, confirm=False):
        if confirm is not True or not isinstance(expected_plan, str) or not store.HEX.fullmatch(expected_plan):
            raise CaptureRefused('explicit_operator_review_confirmation_required')
        # Durable pre-dispatch intent. Crash here intentionally remains uncertain.
        with self.inbox.control.transaction() as con:
            rows = self._rows(con)
            row = self._find(rows, review_id)
            self._live(con, row)
            if row['plan_digest'] != expected_plan:
                raise CaptureRefused('operator_review_plan_changed')
            if row['state'] == 'submitted':
                return self._receipt(row)
            if any(r['state'] in store.UNCERTAIN for r in rows):
                raise CaptureRefused('unresolved_previous_operator_submission')
            if row['state'] != 'prepared':
                raise CaptureRefused('operator_review_not_prepared')
            row['state'] = 'submitting'
            store.save(con, row)
        # Same database lock as source forgetting and explicit inbox revocation.
        # No generic callback/URL or model transport: only pinned local engine.
        with self.inbox.control.transaction() as con:
            row = self._find(self._rows(con), review_id)
            self._live(con, row)
            if row['state'] != 'submitting':
                raise CaptureRefused('operator_review_revoked_before_dispatch')
            self._guard()
            try:
                result = run_engine(self.capture.home, self.capture.binding.path, 'proposal-submit', '--request-stdin',
                                    '--allow-project', self.capture.binding.project, request=_decode(row['payload']))
            except Exception:
                # Even engine refusal is conservatively uncertain; never infer
                # non-commit from a timeout or malformed/error response.
                row['state'] = 'unknown'
            else:
                row['state'] = 'submitted' if isinstance(result, dict) and result.get('canonical_committed') is True else 'unknown'
            store.save(con, row)
            return self._receipt(row)
