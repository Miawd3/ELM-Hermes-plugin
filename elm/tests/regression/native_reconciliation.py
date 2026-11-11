"""Synthetic fresh-process reconciliation/crash qualification; no live data.

Only this harness injects abrupt exits. Installed candidate source is unchanged.
Uses stock Hermes discovery, real engine proposal commits and isolated read-only
canonical reconciliation workers. No claim acceptance is performed.
"""
import argparse
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import native_review_bridge as prior
existing = prior.existing


def canonical_digest(root):
    # SQLite WAL/SHM are disposable read-side coordination, not canonical data.
    return {k: v for k, v in existing.digest(root).items()
            if Path(k).as_posix() not in {'.elm/index.sqlite-wal', '.elm/index.sqlite-shm'}}


def worker(name, base):
    if name == 'capture_prepare_exit':
        return prior.worker(name, base)
    home, root = base / 'profile', base / 'store'
    installed = home / 'plugins/elm'
    os.environ.update(HOME=str(base), HERMES_HOME=str(home), HERMES_RUNTIME_DIR=str(base / 'runtime'),
                      HERMES_ENABLE_PROJECT_PLUGINS='0', HERMES_DISABLE_LAZY_INSTALLS='1', PYTHONDONTWRITEBYTECODE='1')
    sys.path[:0] = [str(existing.HOST), str(installed)]
    from plugins.memory import load_memory_provider, find_provider_dir
    from agent.memory_manager import MemoryManager
    assert find_provider_dir('elm').resolve() == installed.resolve()
    manager = MemoryManager()
    provider = load_memory_provider('elm')
    manager.add_provider(provider)
    manager.initialize_all('review-lifecycle', hermes_home=str(home), platform='cli', agent_context='primary')
    family = provider.__class__.__module__.rsplit('.', 1)[0]
    im = importlib.import_module(family + '.candidate_inbox')
    rm = importlib.import_module(family + '.operator_review')
    CaptureRefused = importlib.import_module(family + '.episode_capture').CaptureRefused
    inbox, reason = im.DurableCandidateInbox.from_recall(provider._episode_recall)
    assert reason == 'ready'
    bridge, reason = rm.OperatorReviewBridge.from_inbox(inbox)
    assert reason == 'ready'
    assert not any(manager.has_tool(t) for t in ('elm_operator_review', 'elm_review_submit', 'elm_review_accept', 'elm_operator_reconcile'))
    state = json.loads((base / 'review-test-state.json').read_text())
    rid, digest = state['prepared']['review_id'], state['prepared']['plan_sha256']
    result = {'phase': name, 'checks': []}
    def record_crash(code, check):
        print(json.dumps(dict(result, checks=[check], expected_exit=code, governance_counts=existing.counts(root))), flush=True)
        os._exit(code)
    def assert_uncertain():
        assert bridge.inspect(rid)['state'] in {'submitting', 'unknown'}
    def no_send(*a, **kw):
        raise AssertionError('Reconciliation/replay must not dispatch submission')
    def refusal():
        try:
            bridge.submit(rid, digest, confirm=True)
        except CaptureRefused as e:
            assert str(e) == 'unresolved_previous_operator_submission', str(e)
        else:
            raise AssertionError('Uncertain submission retry was allowed')
    try:
        if name == 'commit_then_crash':
            original = rm.run_engine
            def crash(*a, **kw):
                original(*a, **kw)
                prior.pending_only(root, 1)
                record_crash(31, 'actual_engine_commit_before_local_receipt_persistence')
            rm.run_engine = crash
            bridge.submit(rid, digest, confirm=True)
            raise AssertionError('Expected abrupt crash')
        elif name == 'predispatch_crash':
            def crash(*a, **kw):
                prior.pending_only(root, 0)
                record_crash(32, 'durable_submitting_before_engine_dispatch')
            rm.run_engine = crash
            bridge.submit(rid, digest, confirm=True)
            raise AssertionError('Expected abrupt crash')
        elif name == 'reconcile_then_crash':
            assert_uncertain()
            original = rm.store.save
            def crash(con, row, *a, **kw):
                assert row['state'] == 'submitted'
                prior.pending_only(root, 1)
                record_crash(33, 'matched_observation_before_local_receipt_persistence')
            rm.store.save = crash
            rm.run_engine = no_send
            bridge.reconcile(rid, digest)
            raise AssertionError('Expected abrupt crash')
        elif name in {'reconcile_match', 'reconcile_absent'}:
            assert_uncertain()
            before = canonical_digest(root)
            rm.run_engine = no_send
            expected = 'matched' if name == 'reconcile_match' else 'absent_uncertain'
            receipt = bridge.reconcile(rid, digest)
            assert receipt['reconciliation']['classification'] == expected, receipt
            for field in ('accepted_memory', 'acceptance_performed', 'submission_performed', 'retry_permitted'):
                assert receipt[field] is False
            assert receipt['reconciliation']['canonical_write'] is False
            assert receipt['acceptance_observed_in_governance'] is False
            assert canonical_digest(root) == before, {'changed': [k for k in set(before) | set(canonical_digest(root)) if before.get(k) != canonical_digest(root).get(k)]}
            if expected == 'matched':
                assert receipt['state'] == 'submitted'
                prior.pending_only(root, 1)
            else:
                assert_uncertain()
                refusal()
                prior.pending_only(root, 0)
            result.update(receipt=receipt, checks=['fresh_process_' + expected, 'canonical_bytes_unchanged', 'no_dispatch_or_acceptance'])
        elif name in {'restart_replay', 'restart_absent_cli'}:
            before = canonical_digest(root)
            binding = json.loads((home / 'elm.json').read_text())
            cli = [sys.executable, '-B', str(installed / 'review_candidates.py'), '--hermes-home', str(home),
                   '--root-id', binding['root_id'], '--project', binding['project']]
            receipt = existing.command(cli + ['operator-reconcile', '--review-id', rid, '--plan-sha256', digest])
            rm.run_engine = no_send
            if name == 'restart_replay':
                assert receipt['reconciliation']['classification'] == 'matched'
                replay = bridge.submit(rid, digest, confirm=True)
                assert replay['state'] == 'submitted'
                assert replay['accepted_memory'] is False and replay['acceptance_performed'] is False
                replay_cli = existing.command(cli + ['operator-submit', '--review-id', rid, '--plan-sha256', digest,
                                                     '--confirm-reviewed-meaning-scope-and-context'])
                assert replay_cli == replay
                prior.pending_only(root, 1)
                result['checks'] = ['CLI_reconciliation_matched', 'fresh_process_API_and_CLI_replay_no_duplicate']
            else:
                assert receipt['reconciliation']['classification'] == 'absent_uncertain'
                assert_uncertain()
                refusal()
                blocked = subprocess.run(cli + ['operator-submit', '--review-id', rid, '--plan-sha256', digest,
                                                '--confirm-reviewed-meaning-scope-and-context'], capture_output=True, text=True, timeout=60)
                assert blocked.returncode == 2, (blocked.stdout, blocked.stderr)
                prior.pending_only(root, 0)
                result['checks'] = ['CLI_reconciliation_absent_uncertain', 'fresh_process_API_and_CLI_resend_refused']
            assert canonical_digest(root) == before, {'changed': [k for k in set(before) | set(canonical_digest(root)) if before.get(k) != canonical_digest(root).get(k)]}
            result['receipt'] = receipt
        else:
            raise AssertionError(name)
    finally:
        manager.shutdown_all()
    result['governance_counts'] = existing.counts(root)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase')
    parser.add_argument('--base', type=Path)
    args = parser.parse_args()
    if args.phase:
        print(json.dumps(worker(args.phase, args.base)))
        return
    pin = subprocess.check_output(['git', '-C', str(existing.HOST), 'rev-parse', 'HEAD'], text=True).strip()
    assert pin == existing.EXPECTED_HOST
    before = subprocess.check_output(['git', '-C', str(existing.HOST), 'status', '--porcelain'], text=True)
    assert before == ''
    source_before = existing.digest(existing.PLUGIN)
    phases = []
    with tempfile.TemporaryDirectory(prefix='elm-reconciliation-synthetic-') as tmp:
        for scenario, names in [('committed', [('capture_prepare_exit', 0), ('commit_then_crash', 31),
                ('reconcile_then_crash', 33), ('reconcile_match', 0), ('restart_replay', 0)]),
                ('absent', [('capture_prepare_exit', 0), ('predispatch_crash', 32),
                ('reconcile_absent', 0), ('restart_absent_cli', 0)])]:
            base = Path(tmp) / scenario
            base.mkdir()
            prior.setup(base)
            for phase, expected in names:
                proc = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '--base', str(base), '--phase', phase],
                                      capture_output=True, text=True, timeout=90)
                assert proc.returncode == expected, (scenario, phase, proc.returncode, proc.stdout, proc.stderr)
                row = json.loads(proc.stdout)
                row.update(scenario=scenario, process_exit=proc.returncode)
                phases.append(row)
    assert source_before == existing.digest(existing.PLUGIN)
    assert before == subprocess.check_output(['git', '-C', str(existing.HOST), 'status', '--porcelain'], text=True)
    print(json.dumps({'status': 'PASS', 'host_commit': pin, 'host_clean': True, 'candidate_source_unchanged': True,
        'fresh_worker_processes': len(phases), 'additional_operator_cli_processes': 6,
        'expected_abrupt_nonzero_exits': [31, 33, 32], 'phases': phases,
        'governance_proposals_submitted': 1, 'canonical_claims_accepted': 0,
        'model_calls': 0, 'live_user_data_operations': 0, 'deployment_performed': False,
        'network': 'socket operations blocked by inherited harness audit hook and canonical worker audit hook',
        'limitations': ['Synthetic fixtures only; no truth or model-quality claims.',
                       'Acceptance observation is not synthesized or tested by this harness.',
                       'Canonical-byte checks exclude disposable SQLite WAL/SHM coordination files.',
                       'Absence never authorizes retry.']}, indent=2))


if __name__ == '__main__':
    main()
