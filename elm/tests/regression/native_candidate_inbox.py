"""Fresh-process stock-host + operator-CLI inbox qualification, synthetic only."""
from concurrent.futures import ThreadPoolExecutor
import argparse
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import native_integrated_flow as existing

TEXT = 'I do not prefer red. Someone else said "prefer red" as a hypothetical.'


def worker(name, base):
    home, root = base / 'profile', base / 'store'
    installed = home / 'plugins/elm'
    os.environ.update(HOME=str(base), HERMES_HOME=str(home), HERMES_RUNTIME_DIR=str(base / 'runtime'),
                      HERMES_ENABLE_PROJECT_PLUGINS='0', HERMES_DISABLE_LAZY_INSTALLS='1', PYTHONDONTWRITEBYTECODE='1')
    sys.path[:0] = [str(existing.HOST), str(installed)]
    from plugins.memory import load_memory_provider
    from agent.memory_manager import MemoryManager
    manager = MemoryManager(); provider = load_memory_provider('elm'); manager.add_provider(provider)
    manager.initialize_all('inbox-lifecycle', hermes_home=str(home), platform='cli', agent_context='primary')
    family = provider.__class__.__module__.rsplit('.', 1)[0]
    module = importlib.import_module(family + '.candidate_inbox')
    store = importlib.import_module(family + '.candidate_inbox_store')
    CaptureRefused = importlib.import_module(family + '.episode_capture').CaptureRefused
    binding = json.loads((home / 'elm.json').read_text())
    state_path = base / 'inbox-test-state.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    assert not any(manager.has_tool(t) for t in ('elm_candidate_inbox', 'elm_inbox_accept', 'elm_inbox_submit'))
    before = existing.digest(root)
    inbox, reason = module.DurableCandidateInbox.from_recall(provider._episode_recall)
    assert reason == 'ready'
    cli = [sys.executable, '-B', str(installed / 'review_candidates.py'), '--hermes-home', str(home),
           '--root-id', binding['root_id'], '--project', binding['project']]
    checks = []
    if name == 'capture_prepare_and_crash':
        pair = [{'message_uid': 'synthetic_u1', 'role': 'user', 'content': TEXT},
                {'message_uid': 'synthetic_a1', 'role': 'assistant', 'content': 'Unverified reply.'}]
        manager.sync_all(TEXT, pair[1]['content'], session_id='inbox-lifecycle', messages=pair,
                         turn_author={'id': 'synthetic_human', 'is_bot': False})
        assert manager.flush_pending(timeout=15)
        manager.on_session_end(pair)
        row = next(r for r in provider._episode_recall._rows() if r['role'] == 'user')
        locator = provider._episode_recall._source(row)['locator']
        request = inbox.prepare([locator], request_key='restart-fixture')
        quote = 'prefer red'; start = TEXT.index(quote)
        state = {'locator': locator, 'request': request, 'raw': json.dumps({'format': 'ELM-BATCH-EXTRACTION/1',
            'batch_id': request['batch_id'], 'candidates': [{'source_id': 's0', 'start': start,
            'end': start + len(quote), 'quote': quote, 'kind': 'preference', 'topic': 'color',
            'interpretation': 'assertion'}]})}
        state_path.write_text(json.dumps(state))
        assert existing.counts(root) == [0, 0] and before == existing.digest(root)
        print(json.dumps({'phase': name, 'checks': ['stock_capture_seal', 'durable_pending_before_abrupt_exit',
              'no_governance_submission'], 'governance_counts': [0, 0]}), flush=True)
        os._exit(0)
    batch_id = state['request']['batch_id']
    if name == 'crash_before_validation_commit':
        original = store.save
        def crash(con, row, **kwargs):
            original(con, row, **kwargs)
            if row['state'] == 'validated':
                os._exit(23)
        store.save = crash
        inbox.validate(batch_id, state['raw'])
        raise AssertionError('Should have exited during uncommitted validation')
    if name == 'validate_and_crash':
        assert inbox.list_batches()['records'][0]['state'] == 'pending'
        assert inbox.list_batches()['records'][0]['attempts'] == 0
        assert inbox.prepare([state['locator']], request_key='restart-fixture') == state['request']
        result = inbox.validate(batch_id, state['raw'])
        state['result'] = result; state_path.write_text(json.dumps(state))
        assert existing.counts(root) == [0, 0] and before == existing.digest(root)
        print(json.dumps({'phase': name, 'checks': ['uncommitted_validation_rolled_back',
            'retry_same_batch', 'durable_validated_before_abrupt_exit'], 'governance_counts': [0, 0]}), flush=True)
        os._exit(0)
    try:
        if name == 'review_cli_forget_restart':
            result = inbox.review(batch_id); assert result == state['result']
            assert result['candidates'][0]['truth'] == 'not_evaluated'
            assert result['candidates'][0]['selection']['quote'] == 'prefer red'
            assert 'do not prefer' in result['sources'][0]['text']
            assert not result['accepted_memory'] and not result['canonical_write']
            assert existing.command(cli + ['review', '--batch-id', batch_id, '--include-source-text']) == result
            assert existing.command(cli + ['list'])['records'][0]['state'] == 'validated'
            # Independent processes race the same prepare key; exactly one row.
            def replay(_):
                return existing.command(cli + ['prepare', '--locator', state['locator'], '--request-key',
                                                'concurrent-process-fixture', '--include-source-text'])
            with ThreadPoolExecutor(max_workers=4) as pool:
                requests = list(pool.map(replay, range(8)))
            assert all(r == requests[0] for r in requests)
            assert len(inbox.list_batches()['records']) == 2
            # A CLI validation/review pair also succeeds through its non-creating adapter.
            raw = json.loads(state['raw']); raw['batch_id'] = requests[0]['batch_id']; raw = json.dumps(raw)
            completed = subprocess.run(cli + ['validate', '--batch-id', requests[0]['batch_id'], '--include-source-text'],
                                       input=raw, text=True, capture_output=True)
            assert completed.returncode == 0, completed.stdout + completed.stderr
            assert json.loads(completed.stdout)['status'] == 'quarantined_candidates'
            preview = provider.episode_forget_preview(state['locator'])
            assert preview['local_span_inbox_batches'] == 2
            forgotten = provider.episode_forget(state['locator'], preview['plan_sha256'])
            assert forgotten['local_span_inbox_batches_scrubbed'] == 2
            assert all(row['state'] == 'revoked' for row in existing.command(cli + ['list'])['records'])
            denied = subprocess.run(cli + ['review', '--batch-id', batch_id, '--include-source-text'], text=True, capture_output=True)
            assert denied.returncode == 2 and 'quote' not in denied.stdout
            checks = ['stable_restart_candidate_ids', 'CLI_list_review_validate', 'separate_process_concurrent_prepare',
                      'exact_span_not_semantic_truth', 'atomic_forget_scrubs_both_batches', 'no_source_copy_fallback']
        elif name == 'revocation_survives_restart':
            assert all(r['state'] == 'revoked' for r in inbox.list_batches()['records'])
            try: inbox.validate(batch_id, state['raw'])
            except CaptureRefused: pass
            else: raise AssertionError('Forgotten batch replayed')
            for filename in ('elm_episode_capture.json', 'elm_episode_recall.json', 'elm_batch_extraction.json', 'elm_candidate_inbox.json'):
                (home / filename).write_text('{"enabled":false}')
            result = existing.command(cli + ['revoke-all', '--confirm-revoke'])
            assert result['status'] == 'revoked'
            checks = ['forgotten_replay_blocked_after_restart', 'explicit_revoke_after_all_optouts']
        else: raise AssertionError(name)
        assert existing.counts(root) == [0, 0] and before == existing.digest(root)
    finally:
        manager.shutdown_all()
    return {'phase': name, 'checks': checks + ['canonical_root_unchanged'], 'governance_counts': existing.counts(root)}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--phase'); parser.add_argument('--base', type=Path)
    args = parser.parse_args()
    if args.phase:
        print(json.dumps(worker(args.phase, args.base))); return
    pin = subprocess.check_output(['git', '-C', str(existing.HOST), 'rev-parse', 'HEAD'], text=True).strip()
    assert pin == existing.EXPECTED_HOST
    before = subprocess.check_output(['git', '-C', str(existing.HOST), 'status', '--porcelain'], text=True)
    assert before == ''
    with tempfile.TemporaryDirectory(prefix='elm-inbox-lifecycle-synthetic-') as temporary:
        base = Path(temporary); binding = existing.setup(base)
        existing.settings(base / 'profile', binding, 'elm_candidate_inbox.json', author_id='synthetic_human')
        cmd = [sys.executable, '-B', str(Path(__file__).resolve()), '--base', str(base), '--phase']
        phases = [existing.command(cmd + ['capture_prepare_and_crash'])]
        crash = subprocess.run(cmd + ['crash_before_validation_commit'], capture_output=True, text=True)
        assert crash.returncode == 23, (crash.returncode, crash.stdout, crash.stderr)
        phases.append({'phase': 'crash_before_validation_commit', 'checks': ['forced_os_exit_23_in_transaction']})
        for name in ('validate_and_crash', 'review_cli_forget_restart', 'revocation_survives_restart'):
            phases.append(existing.command(cmd + [name]))
    assert before == subprocess.check_output(['git', '-C', str(existing.HOST), 'status', '--porcelain'], text=True)
    print(json.dumps({'status': 'PASS', 'host_commit': pin, 'host_clean': True, 'fresh_worker_processes': 5,
        'additional_concurrent_cli_processes': 8, 'phases': phases,
        'model_calls': 0, 'live_user_data_operations': 0, 'canonical_claims_accepted': 0,
        'governance_proposals_submitted': 0, 'deployment_performed': False,
        'limitations': ['Exact source spans are not verified facts.', 'Logical deletion is not secure erasure.',
                        'No model transport or human approval-to-governance bridge is implemented.']}, indent=2))


if __name__ == '__main__': main()
