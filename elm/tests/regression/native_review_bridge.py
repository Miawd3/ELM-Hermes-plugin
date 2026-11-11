"""Fresh-process, stock-Hermes operator review qualification; synthetic only.

No model calls, network, real profiles, deployment, or acceptance. The existing
native harness installs a pinned plugin copy into disposable Hermes profiles.
"""
from contextlib import closing
import argparse
import importlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

import native_integrated_flow as existing

TEXT = 'I prefer synthetic cobalt tea; this statement remains unverified.'


def semantics(value='synthetic cobalt tea'):
    return dict(subject='synthetic_human', predicate='prefers', object=value,
                scope='project:orion', valid_from='2026-11-06T12:00:00Z',
                context='Synthetic operator review qualification only',
                attribution='Operator interpretation of a quoted user observation',
                uncertainty='Unverified; pending governance review, not accepted memory')


def pending_only(root, count):
    assert existing.counts(root) == [0, count], existing.counts(root)
    with closing(sqlite3.connect(root / '.elm/index.sqlite')) as con:
        columns = [r[1] for r in con.execute('PRAGMA table_info(governance_proposals)')]
        status = 'status' if 'status' in columns else 'state'
        assert {r[0] for r in con.execute(f'SELECT {status} FROM governance_proposals')} <= {'pending'}
        assert con.execute('SELECT count(*) FROM governance_proposals WHERE supersedes_claim_id IS NOT NULL').fetchone()[0] == 0


def worker(name, base):
    home, root = base / 'profile', base / 'store'
    installed = home / 'plugins/elm'
    os.environ.update(HOME=str(base), HERMES_HOME=str(home), HERMES_RUNTIME_DIR=str(base / 'runtime'),
                      HERMES_ENABLE_PROJECT_PLUGINS='0', HERMES_DISABLE_LAZY_INSTALLS='1', PYTHONDONTWRITEBYTECODE='1')
    sys.path[:0] = [str(existing.HOST), str(installed)]
    from plugins.memory import load_memory_provider, find_provider_dir
    from agent.memory_manager import MemoryManager
    assert find_provider_dir('elm').resolve() == installed.resolve()
    manager = MemoryManager(); provider = load_memory_provider('elm'); manager.add_provider(provider)
    manager.initialize_all('review-lifecycle', hermes_home=str(home), platform='cli', agent_context='primary')
    family = provider.__class__.__module__.rsplit('.', 1)[0]
    inbox_module = importlib.import_module(family + '.candidate_inbox')
    review_module = importlib.import_module(family + '.operator_review')
    CaptureRefused = importlib.import_module(family + '.episode_capture').CaptureRefused
    inbox, reason = inbox_module.DurableCandidateInbox.from_recall(provider._episode_recall)
    assert reason == 'ready'
    bridge, reason = review_module.OperatorReviewBridge.from_inbox(inbox)
    assert reason == 'ready'
    assert not any(manager.has_tool(t) for t in ('elm_operator_review', 'elm_review_submit', 'elm_review_accept'))
    state_path = base / 'review-test-state.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    checks = []
    binding = json.loads((home / 'elm.json').read_text())
    cli = [sys.executable, '-B', str(installed / 'review_candidates.py'), '--hermes-home', str(home),
           '--root-id', binding['root_id'], '--project', binding['project']]
    def cli_call(arguments, *, data=None, expected=0):
        process = subprocess.run(cli + arguments, input=None if data is None else json.dumps(data),
                                 capture_output=True, text=True, timeout=60)
        assert process.returncode == expected, (arguments, process.returncode, process.stdout, process.stderr)
        if expected == 0:
            return json.loads(process.stdout)
        return process
    def save(): state_path.write_text(json.dumps(state))
    def refused(call):
        try: call()
        except CaptureRefused as exc: return str(exc)
        raise AssertionError('Expected fail-closed refusal')
    if name == 'capture_prepare_exit':
        pair = [{'message_uid': 'synthetic_u1', 'role': 'user', 'content': TEXT},
                {'message_uid': 'synthetic_a1', 'role': 'assistant', 'content': 'Unverified reply.'}]
        manager.sync_all(TEXT, pair[1]['content'], session_id='review-lifecycle', messages=pair,
                         turn_author={'id': 'synthetic_human', 'is_bot': False})
        assert manager.flush_pending(timeout=15)
        manager.on_session_end(pair)
        row = next(r for r in provider._episode_recall._rows() if r['role'] == 'user')
        locator = provider._episode_recall._source(row)['locator']
        request = inbox.prepare([locator], request_key='native-review-batch')
        result = inbox.validate(request['batch_id'], json.dumps({'format': 'ELM-BATCH-EXTRACTION/1',
            'batch_id': request['batch_id'], 'candidates': [{'source_id': 's0', 'start': 0,
            'end': len(TEXT), 'quote': TEXT, 'kind': 'preference', 'topic': 'tea', 'interpretation': 'assertion'}]}))
        assert result['candidates'][0]['truth'] == 'not_evaluated'
        state = dict(locator=locator, batch_id=request['batch_id'], candidate_id=result['candidates'][0]['candidate_id'])
        state['prepared'] = cli_call(['operator-prepare', '--batch-id', state['batch_id'],
            '--candidate-id', state['candidate_id'], '--request-key', 'native-review', '--include-source-text'], data=semantics())
        assert bridge.inspect(state['prepared']['review_id']) == state['prepared']
        assert state['prepared']['review_id'] and len(state['prepared']['plan_sha256']) == 64
        save(); pending_only(root, 0)
        print(json.dumps({'phase': name, 'checks': ['stock_Hermes_capture_and_seal', 'exact_span_quarantined',
            'operator_CLI_prepare_matches_API', 'operator_plan_durable_before_abrupt_exit', 'no_proposal_without_confirmation'], 'governance_counts': [0, 0]}), flush=True)
        os._exit(0)
    prepared = state['prepared']; rid, plan = prepared['review_id'], prepared['plan_sha256']
    try:
        if name == 'restart_inspect_submit':
            inspection = cli_call(['operator-inspect', '--review-id', rid, '--include-source-text'])
            assert inspection == bridge.inspect(rid) and inspection['plan_sha256'] == plan
            inventory = cli_call(['operator-list'])
            assert len(inventory['records']) == 1 and inventory['records'][0]['review_id'] == rid
            assert TEXT not in json.dumps(inventory)
            assert bridge.prepare(state['batch_id'], state['candidate_id'], semantics(), request_key='native-review') == prepared
            pending_only(root, 0)
            refused(lambda: bridge.submit(rid, '0' * 64, confirm=True))
            refused(lambda: bridge.submit(rid, plan, confirm=False))
            pending_only(root, 0)
            before_root, before_local = existing.digest(root), existing.digest(home / 'elm/episodes')
            cli_call(['operator-submit', '--review-id', rid, '--plan-sha256', plan], expected=2)
            assert existing.digest(root) == before_root and existing.digest(home / 'elm/episodes') == before_local
            state['submitted'] = cli_call(['operator-submit', '--review-id', rid, '--plan-sha256', plan,
                                          '--confirm-reviewed-meaning-scope-and-context'])
            pending_only(root, 1); save()
            checks = ['fresh_process_plan_stable', 'changed_plan_and_unconfirmed_submit_refused', 'explicit_submit_pending_only', 'CLI_inspect_list_submit', 'CLI_missing_confirmation_no_write']
        elif name == 'restart_replay_correct':
            before = existing.digest(root)
            assert bridge.submit(rid, plan, confirm=True) == state['submitted']
            assert cli_call(['operator-submit', '--review-id', rid, '--plan-sha256', plan,
                             '--confirm-reviewed-meaning-scope-and-context']) == state['submitted']
            assert existing.digest(root) == before
            before_local = existing.digest(home / 'elm/episodes')
            cli_call(['operator-revoke', '--review-id', rid], expected=2)
            assert existing.digest(home / 'elm/episodes') == before_local and existing.digest(root) == before
            revoked = cli_call(['operator-revoke', '--review-id', rid, '--confirm-revoke'])
            assert revoked['status'] == 'revoked'
            refused(lambda: bridge.submit(rid, plan, confirm=True))
            correction = bridge.prepare(state['batch_id'], state['candidate_id'], semantics('synthetic amber tea'),
                                        request_key='native-correction')
            assert correction['review_id'] != rid and correction['plan_sha256'] != plan
            pending_only(root, 1)
            state['correction'] = correction
            state['corrected_submission'] = bridge.submit(correction['review_id'], correction['plan_sha256'], confirm=True)
            pending_only(root, 2); save()
            checks = ['submitted_replay_no_duplicate', 'CLI_replay_revoke', 'CLI_missing_revoke_confirmation_no_write', 'correction_requires_new_review_and_confirmation',
                      'correction_separate_pending_proposal_no_accepted_supersession']
        elif name == 'forget':
            pending_only(root, 2); before = existing.digest(root)
            preview = provider.episode_forget_preview(state['locator'])
            forgotten = provider.episode_forget(state['locator'], preview['plan_sha256'])
            assert existing.digest(root) == before
            assert all(r['state'] == 'revoked' for r in inbox.list_batches()['records'])
            checks = ['source_forget_revokes_inbox', 'canonical_pending_proposals_retained', 'forget_does_not_accept_or_supersede']
        elif name == 'restart_revoked':
            pending_only(root, 2); before = existing.digest(root)
            refused(lambda: bridge.inspect(rid))
            refused(lambda: bridge.submit(rid, plan, confirm=True))
            refused(lambda: bridge.submit(state['correction']['review_id'], state['correction']['plan_sha256'], confirm=True))
            assert existing.digest(root) == before
            checks = ['forgotten_review_revoked_after_restart', 'stale_submission_blocked', 'canonical_proposals_not_erased']
        elif name == 'submit_commit_crash':
            # Wrap the actual local engine call and terminate after it returns,
            # before bridge result persistence. Engine commit is real.
            original = review_module.run_engine
            def crash_after_engine(*args, **kwargs):
                result = original(*args, **kwargs)
                pending_only(root, 1)
                print(json.dumps({'phase': name, 'checks': ['engine_committed_before_os_exit_29'],
                                  'governance_counts': [0, 1]}), flush=True)
                os._exit(29)
            review_module.run_engine = crash_after_engine
            bridge.submit(rid, plan, confirm=True)
            raise AssertionError('Expected crash after engine commit')
        elif name == 'restart_unknown_no_retry':
            pending_only(root, 1); before = existing.digest(root)
            inspection = bridge.inspect(rid)
            assert inspection.get('state', inspection.get('status')) in {'submitting', 'unknown'}
            error = refused(lambda: bridge.submit(rid, plan, confirm=True))
            assert existing.digest(root) == before
            pending_only(root, 1)
            review_module.ReviewBridgeControl(home, provider._episode_capture.binding).revoke(rid)
            refused(lambda: bridge.submit(rid, plan, confirm=True))
            assert existing.digest(root) == before
            checks = ['interrupted_result_unknown_after_restart', 'no_automatic_or_explicit_blind_retry',
                      'explicit_revocation_does_not_erase_canonical_proposal']
        else: raise AssertionError(name)
    finally:
        manager.shutdown_all()
    return {'phase': name, 'checks': checks, 'governance_counts': existing.counts(root)}


def setup(base):
    binding = existing.setup(base)
    existing.settings(base / 'profile', binding, 'elm_candidate_inbox.json', author_id='synthetic_human')
    existing.settings(base / 'profile', binding, 'elm_operator_review.json', operator_id='synthetic_operator')


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--phase'); parser.add_argument('--base', type=Path)
    args = parser.parse_args()
    if args.phase:
        print(json.dumps(worker(args.phase, args.base))); return
    pin = subprocess.check_output(['git', '-C', str(existing.HOST), 'rev-parse', 'HEAD'], text=True).strip()
    assert pin == existing.EXPECTED_HOST
    before = subprocess.check_output(['git', '-C', str(existing.HOST), 'status', '--porcelain'], text=True)
    assert before == ''
    with tempfile.TemporaryDirectory(prefix='elm-review-lifecycle-synthetic-') as temporary:
        base = Path(temporary); setup(base)
        command = lambda b, phase: [sys.executable, '-B', str(Path(__file__).resolve()), '--base', str(b), '--phase', phase]
        phases = [existing.command(command(base, name)) for name in ('capture_prepare_exit', 'restart_inspect_submit',
                  'restart_replay_correct', 'forget', 'restart_revoked')]
        uncertain = base / 'uncertain'; uncertain.mkdir(); setup(uncertain)
        phases.append(existing.command(command(uncertain, 'capture_prepare_exit')))
        crash = subprocess.run(command(uncertain, 'submit_commit_crash'), capture_output=True, text=True)
        assert crash.returncode == 29, (crash.returncode, crash.stdout, crash.stderr)
        phases.append(json.loads(crash.stdout))
        phases.append(existing.command(command(uncertain, 'restart_unknown_no_retry')))
    assert before == subprocess.check_output(['git', '-C', str(existing.HOST), 'status', '--porcelain'], text=True)
    print(json.dumps({'status': 'PASS', 'host_commit': pin, 'host_clean': True, 'fresh_worker_processes': len(phases),
        'additional_operator_cli_processes': 9, 'phases': phases, 'model_calls': 0, 'live_user_data_operations': 0, 'canonical_claims_accepted': 0,
        'governance_proposals_submitted': 3, 'deployment_performed': False,
        'network': 'socket operations blocked by native harness audit hook',
        'limitations': ['Synthetic operator semantics do not establish truth or model quality.',
                        'Pending governance proposals survive local forgetting.',
                        'Interrupted submission requires operator reconciliation; no automatic resend.',
                        'Logical deletion is not secure erasure.']}, indent=2))


if __name__ == '__main__': main()
