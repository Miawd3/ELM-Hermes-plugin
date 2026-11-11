"""Source-only canonical snapshot helper. Never submits, recovers, or accepts.

Executed with isolated Python (-I -S), importing only this delivery's engine.
Canonical data reads share the engine writer lock; SQLite is never consulted.
"""
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
from elm_memory.canonical import canonical_json_bytes, parse_closed_json
from elm_memory.governance import (GovernanceError, load_root_identity, root_identity_path,
    normalize_proposal_submission, SUBMISSION_DIGEST_DOMAIN, PROPOSAL_V2_FORMAT_VERSION,
    pending_transactions, load_governance, proposal_statuses, submission_replay_key)
from elm_memory.locking import WriterLock, WriterLockError

FORMAT = 'ELM-SUBMISSION-OBSERVATION/1'


def inspect(request):
    if (not isinstance(request, dict) or set(request) != {
            'root', 'root_id', 'identity_sha256', 'project', 'submission_id', 'payload'}):
        raise ValueError('invalid_request')
    root = Path(request['root'])
    if not root.is_absolute() or not root.is_dir() or root.is_symlink():
        raise ValueError('invalid_root')
    # No lock-directory initialization through a missing/symlinked .elm path.
    if not (root / '.elm').is_dir() or (root / '.elm').is_symlink():
        raise ValueError('invalid_lock_directory')
    submission_id, payload, _ = normalize_proposal_submission(request['payload'])
    if submission_id != request['submission_id'] or payload['project'] != request['project']:
        raise ValueError('local_identity_mismatch')
    expected = hashlib.sha256(SUBMISSION_DIGEST_DOMAIN + canonical_json_bytes(payload)).hexdigest()
    result = {'format': FORMAT, 'classification': 'unavailable', 'reason': 'unverified',
        'root_id': request['root_id'], 'project': request['project'], 'submission_id': submission_id,
        'request_sha256': hashlib.sha256(json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'expected_payload_sha256': expected, 'proposal_id': None, 'observed_canonical_status': None,
        'authoritative_snapshot': False, 'canonical_write': False, 'submission_performed': False,
        'acceptance_performed': False}
    try:
        with WriterLock(root, 'operator-submission-reconcile', timeout=2.0, recover_stale=False):
            identity = load_root_identity(root, required=True)
            if (identity['root_id'] != request['root_id'] or hashlib.sha256(
                    root_identity_path(root).read_bytes()).hexdigest() != request['identity_sha256']):
                result['reason'] = 'root_identity_mismatch'
                return result
            # Even committed journals require explicit external recovery. A
            # prepared journal can contain matching bytes that later roll back.
            if pending_transactions(root):
                result['reason'] = 'unfinished_governance_transaction'
                return result
            proposals, evidence, events, tombstones = load_governance(root)
            statuses = proposal_statuses(proposals, events, tombstones)
            result['authoritative_snapshot'] = True
            key = submission_replay_key(request['project'], submission_id)
            if any(item.get('submission_replay_key') == key for item in tombstones.values()):
                result.update(classification='conflict', reason='submission_id_retired')
                return result
            matches = [p for p in proposals.values() if p.get('project') == request['project']
                       and p.get('submission_id') == submission_id]
            if not matches:
                result.update(classification='absent_uncertain', reason='not_observed_dispatch_may_still_complete')
                return result
            if len(matches) != 1:
                result.update(classification='conflict', reason='duplicate_submission_identity')
                return result
            proposal = matches[0]
            result.update(proposal_id=proposal['proposal_id'],
                          observed_canonical_status=statuses[proposal['proposal_id']])
            if proposal.get('format_version') != PROPOSAL_V2_FORMAT_VERSION:
                result.update(classification='conflict', reason='proposal_version_mismatch')
            elif proposal.get('_payload_digest_verified') is not True:
                result.update(classification='unverifiable', reason='canonical_evidence_redacted')
            elif proposal.get('payload_digest') != expected:
                result.update(classification='conflict', reason='payload_digest_mismatch')
            else:
                result.update(classification='matched', reason='exact_persisted_submission_and_payload')
            return result
    except WriterLockError:
        result.update(classification='unavailable', reason='writer_lock_unavailable', authoritative_snapshot=False,
                      proposal_id=None, observed_canonical_status=None)
    except (GovernanceError, OSError, ValueError, TypeError, KeyError):
        # Never echo canonical/user data from parser errors.
        result.update(classification='unavailable', reason='canonical_state_invalid', authoritative_snapshot=False,
                      proposal_id=None, observed_canonical_status=None)
    return result


def main():
    def deny_network(event, args):
        if event in {'socket.connect', 'socket.getaddrinfo', 'socket.bind'}:
            raise RuntimeError('network_forbidden')
    sys.addaudithook(deny_network)
    try:
        raw = sys.stdin.buffer.read(32769)
        if len(raw) > 32768:
            raise ValueError('request_too_large')
        result = inspect(parse_closed_json(raw.decode('utf-8')))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({'error': 'canonical_observation_unavailable'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
