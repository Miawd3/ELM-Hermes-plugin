"""Pinned canonical observation boundary, not a submission transport."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from .batch_extraction import _decode
from .engine import ElmError

FORMAT = 'ELM-SUBMISSION-OBSERVATION/1'
FIELDS = {'format', 'classification', 'reason', 'root_id', 'project', 'submission_id',
          'expected_payload_sha256', 'request_sha256', 'proposal_id', 'observed_canonical_status',
          'authoritative_snapshot', 'canonical_write', 'submission_performed', 'acceptance_performed'}
REASONS = {
    'matched': {'exact_persisted_submission_and_payload'},
    'absent_uncertain': {'not_observed_dispatch_may_still_complete'},
    'conflict': {'submission_id_retired', 'duplicate_submission_identity', 'proposal_version_mismatch', 'payload_digest_mismatch'},
    'unverifiable': {'canonical_evidence_redacted'},
    'unavailable': {'root_identity_mismatch', 'unfinished_governance_transaction', 'writer_lock_unavailable', 'canonical_state_invalid'},
}


def observe_submission(home, binding, row):
    request = {'root': str(binding.path), 'root_id': binding.root_id, 'identity_sha256': binding.identity_sha256,
               'project': binding.project, 'submission_id': row['submission_id'], 'payload': _decode(row['payload'])}
    env = {key: value for key, value in os.environ.items()
           if key.upper() in {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'TMPDIR'}}
    env.update(HOME=str(home), USERPROFILE=str(home))
    command = [sys.executable, '-B', '-I', '-S', str(Path(__file__).with_name('governance_reconcile_worker.py'))]
    try:
        completed = subprocess.run(command, input=json.dumps(request, ensure_ascii=False),
            encoding='utf-8', capture_output=True, cwd=Path(__file__).resolve().parent, env=env,
            timeout=10, shell=False)
        if completed.returncode != 0 or len(completed.stdout) > 8192:
            raise ValueError()
        result = _decode(completed.stdout)
        if (not isinstance(result, dict) or set(result) != FIELDS or result['format'] != FORMAT
                or result['classification'] not in REASONS
                or result['reason'] not in REASONS[result['classification']]
                or any(result[k] != request[k] for k in ('root_id', 'project', 'submission_id'))
                or result['request_sha256'] != hashlib.sha256(json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                or not isinstance(result['expected_payload_sha256'], str)
                or not re.fullmatch(r'[0-9a-f]{64}', result['expected_payload_sha256'])
                or any(result[k] is not False for k in ('canonical_write', 'submission_performed', 'acceptance_performed'))
                or type(result['authoritative_snapshot']) is not bool
                or result['authoritative_snapshot'] != (result['classification'] != 'unavailable')
                or result['observed_canonical_status'] not in {None, 'pending', 'accepted', 'rejected', 'deferred'}
                or result['proposal_id'] is not None and (not isinstance(result['proposal_id'], str)
                    or not re.fullmatch(r'proposal_[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', result['proposal_id']))
                or result['classification'] == 'matched' and (result['proposal_id'] is None or result['observed_canonical_status'] is None)):
            raise ValueError()
        return result
    except (subprocess.TimeoutExpired, OSError, ValueError, TypeError, KeyError):
        raise ElmError('reconciliation_unavailable', 'Authoritative submission observation unavailable; no retry is authorized.') from None
