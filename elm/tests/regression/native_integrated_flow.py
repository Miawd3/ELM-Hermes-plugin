"""Fresh-process stock-Hermes lifecycle qualification using synthetic data only.

Run with a dependency-prepared Hermes interpreter. No host edits, model calls,
credentials, network, live profiles, or canonical deployment. Temporary stores
are deliberately created and mutated, then removed by TemporaryDirectory.
"""
from contextlib import closing
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
AREA = Path(__file__).resolve().parent
PLUGIN = AREA.parents[1]
HOST = Path(os.environ.get('HERMES_STOCK_SOURCE', str(
    AREA.parent / 'integration_elm_20261106/isolated_runtime/hermes-stock'))).resolve()
EXPECTED_HOST = 'b200f5bc60e31588ba2cb60e288029c4a54ba5fa'
TEXTS = ['Preference: answer_style = synthetic_concise',
         'Preference: answer_style = synthetic_detailed',
         'I prefer synthetic cobalt tea. This is an unverified observation.']


def no_network(event, args):
    if event in {'socket.connect', 'socket.getaddrinfo', 'socket.bind'}:
        raise RuntimeError('No network permitted in integrated synthetic qualification')


sys.addaudithook(no_network)


def digest(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def command(args, *, env=None):
    value = subprocess.run(args, capture_output=True, text=True, timeout=60, env=env)
    assert value.returncode == 0, (args, value.returncode, value.stdout, value.stderr)
    return json.loads(value.stdout)


def rows(number):
    return [{'message_uid': f'u{number}', 'role': 'user', 'content': TEXTS[number-1],
             'speaker_id': 'synthetic_human', 'timestamp': '2026-11-06T12:00:00Z'},
            {'message_uid': f'a{number}', 'role': 'assistant', 'content': f'Unverified reply {number}.'}]


def counts(root):
    with closing(sqlite3.connect(f"{(root / '.elm/index.sqlite').as_uri()}?mode=ro", uri=True)) as con:
        return [con.execute('SELECT count(*) FROM claims').fetchone()[0],
                con.execute('SELECT count(*) FROM governance_proposals').fetchone()[0]]


def settings(home, binding, name, **extra):
    (home/name).write_text(json.dumps({'format_version': 1, 'enabled': True,
        'root_id': binding['root_id'], 'project': binding['project'], **extra}))


def setup(base):
    home = base/'profile'; home.mkdir()
    root = base/'store'
    installed = home/'plugins/elm'
    shutil.copytree(PLUGIN, installed, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'tests', '.git'))
    (home/'config.yaml').write_text('memory:\n  provider: elm\nplugins:\n  isolation: in_process\n')
    binding = command([sys.executable, '-B', str(installed/'manage.py'), 'init', '--budget-mode', 'legacy-estimate',
        '--hermes-home', str(home), '--root', str(root), '--project', 'orion', '--mode', 'proposal-only'])
    settings(home, binding, 'elm_episode_capture.json', explicit_proposals=True,
             proposal_author_id='synthetic_human', retention_seconds=3600)
    settings(home, binding, 'elm_episode_recall.json', budget=1200)
    settings(home, binding, 'elm_batch_extraction.json', author_id='synthetic_human')
    return binding


def phase(name, base):
    home, root = base/'profile', base/'store'
    installed = home/'plugins/elm'
    os.environ.update(HOME=str(base), HERMES_HOME=str(home), HERMES_RUNTIME_DIR=str(base/'runtime'),
        HERMES_ENABLE_PROJECT_PLUGINS='0', HERMES_DISABLE_LAZY_INSTALLS='1', PYTHONDONTWRITEBYTECODE='1')
    sys.path[:0] = [str(HOST), str(installed)]
    from plugins.memory import load_memory_provider, find_provider_dir
    from agent.memory_manager import MemoryManager
    binding = json.loads((home/'elm.json').read_text())
    assert find_provider_dir('elm').resolve() == installed.resolve()
    p = load_memory_provider('elm'); m = MemoryManager(); m.add_provider(p)
    # Stock discovery namespaces plugin imports. Resolve its actual module
    # family rather than mixing two nominally identical exception classes.
    family = p.__class__.__module__.rsplit('.', 1)[0]
    batch_module = importlib.import_module(family+'.batch_extraction')
    BatchExtraction, FORMAT = batch_module.BatchExtraction, batch_module.FORMAT
    CaptureRefused = importlib.import_module(family+'.episode_capture').CaptureRefused
    EpisodeInspection = importlib.import_module(family+'.episode_inspect').EpisodeInspection
    m.initialize_all('lifecycle', hermes_home=str(home), platform='cli', agent_context='primary')
    assert m.get_provider('elm') is p and p._episode_capture is not None
    assert all(m.has_tool(t) for t in ('elm_episode_search', 'elm_episode_read', 'elm_context'))
    assert not m.has_tool('elm_episode_forget')
    inspector = lambda: EpisodeInspection(home, root_id=binding['root_id'], project='orion')
    call = lambda tool, **args: json.loads(m.handle_tool_call(tool, args))
    def refused(fn, contains):
        try: fn()
        except CaptureRefused as exc: assert contains in str(exc), str(exc)
        else: raise AssertionError('Expected refusal: '+contains)
    def capture(number):
        pair = rows(number)
        m.sync_all(pair[0]['content'], pair[1]['content'], session_id='lifecycle', messages=pair,
                   turn_author={'id': 'synthetic_human', 'is_bot': False})
        assert m.flush_pending(timeout=15)
        return pair
    def batch(locator):
        extractor, ready = BatchExtraction.from_recall(p._episode_recall)
        assert ready == 'ready'
        request = extractor.prepare([locator]); text = request['sources'][0]['text']
        result = extractor.validate(request['batch_id'], json.dumps({'format': FORMAT,
            'batch_id': request['batch_id'], 'candidates': [{'source_id': 's0', 'start': 0,
            'end': len(text), 'quote': text, 'kind': 'preference', 'topic': 'drink',
            'interpretation': 'assertion'}]}))
        assert result['candidates'][0]['status'] == 'quarantined_candidate'
        assert not result['accepted_memory'] and not result['canonical_write']
        return extractor, request['batch_id']
    state_file = base/'state.json'
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    checks = []
    if name == 'interrupt_before_seal':
        capture(3)
        assert p._episode_capture.status()['active_messages'] == 2
        assert inspector().candidates()['records'] == [] and counts(root) == [0, 0]
        print(json.dumps({'phase': name, 'checks': ['durable_capture_before_abrupt_exit'],
                          'governance_counts': counts(root)}), flush=True)
        os._exit(0)  # Deliberately bypass manager.shutdown_all and its seal hook.
    if name == 'interrupt_after_claim':
        capture(1)
        p._episode_capture.seal('lifecycle', 'session_end')
        p._episode_capture.prepare_batches()
        item = p._episode_capture.next_proposal()
        assert item and not item.get('blocked') and counts(root) == [0, 0]
        assert inspector().candidates()['records'][0]['local_queue_state'] == 'submitting'
        print(json.dumps({'phase': name, 'checks': ['durable_dispatch_claim_before_abrupt_exit'],
                          'governance_counts': counts(root)}), flush=True)
        os._exit(0)  # No external dispatch; next process must still treat outcome as uncertain.
    try:
        if name == 'capture_and_seal':
            assert counts(root) == [0, 0]
            assert p._episode_capture.status()['active_messages'] == 2
            for number in (1, 2, 3): latest = capture(number)
            assert inspector().candidates()['records'] == []
            assert p._episode_capture.status()['active_messages'] == 6
            m.on_session_end(latest)
            assert counts(root) == [0, 2]
            records = p.episode_proposal_snapshot()['records']
            assert len(records) == 2
            assert all(r['status'] == 'submitted' and r['result']['status'] == 'pending' for r in records)
            # Regression: the old inspector returned zero here, despite two pending proposals.
            visible = inspector().candidates()['records']
            assert len(visible) == 2, {'missing_submitted_review_candidates': visible, 'governance_counts': counts(root)}
            assert all(r['conflict_hint_unverified'] and not r['accepted_memory'] for r in visible)
            state['ids'] = sorted(r['candidate_id'] for r in visible)
            state['locators'] = {str(n): call('elm_episode_search', query=TEXTS[n-1])['results'][0]['locator']
                                 for n in (1, 2, 3)}
            before_root, before_evidence = digest(root), digest(home/'elm/episodes')
            for n in (1, 2, 3):
                loc = state['locators'][str(n)]
                assert call('elm_episode_read', locator=loc)['source']['text'] == TEXTS[n-1]
                assert 'text' not in inspector().evidence(loc)['source']
            cli = command([sys.executable, '-B', str(installed/'inspect_episodes.py'), '--hermes-home',
                str(home), '--root-id', binding['root_id'], '--project', 'orion', 'evidence',
                '--locator', state['locators']['1'], '--include-source-text'])
            assert cli['source']['text'] == TEXTS[0]
            extractor, state['lost_batch_id'] = batch(state['locators']['3'])
            assert len(extractor.review(state['lost_batch_id'])['candidates']) == 1
            assert inspector().status()['batch_candidates'] == 'not_persisted_process_local_only'
            assert before_root == digest(root) and before_evidence == digest(home/'elm/episodes')
            context = call('elm_context', query='synthetic_concise synthetic_detailed cobalt tea')['packet']
            assert not any(s in context for s in ('synthetic_concise', 'synthetic_detailed', 'cobalt tea'))
            checks += ['native_discovery', 'unsealed_restart_and_dedup', 'async_capture', 'sealed_marker_proposals', 'conflicts_not_truth',
                       'submitted_candidates_visible', 'exact_recall', 'operator_explicit_text',
                       'inspection_and_batch_readonly', 'pending_excluded_from_canonical_context']
        elif name == 'restart_and_forget':
            assert counts(root) == [0, 2]
            visible = inspector().candidates()['records']
            assert sorted(r['candidate_id'] for r in visible) == state['ids']
            assert p.flush_episode_proposals()['submitted'] == 0
            extractor, ready = BatchExtraction.from_recall(p._episode_recall)
            refused(lambda: extractor.review(state['lost_batch_id']), 'unknown_batch_id')
            loc = state['locators']['1']
            assert call('elm_episode_read', locator=loc)['source']['text'] == TEXTS[0]
            before_root = digest(root)
            preview = p.episode_forget_preview(loc)
            assert preview['external_outcome_review_required'] and preview['source_messages_to_remove'] == 2
            before_evidence = digest(home/'elm/episodes')
            refused(lambda: p.episode_forget(loc, '0'*64), 'forget_plan_changed')
            assert before_evidence == digest(home/'elm/episodes')
            result = p.episode_forget(loc, preview['plan_sha256'])
            assert result['local_proposal_payloads_scrubbed'] == 1
            assert 'error' in call('elm_episode_read', locator=loc)
            refused(lambda: inspector().evidence(loc, include_source_text=True), 'source_unavailable')
            records = inspector().candidates()['records']
            assert len(records) == 1 and not records[0]['conflict_hint_unverified']
            all_records = inspector().candidates(include_resolved=True)['records']
            assert len(all_records) == 2 and any(r['local_queue_state'] == 'revoked_submitted' for r in all_records)
            assert counts(root) == [0, 2] and before_root == digest(root)
            assert call('elm_episode_read', locator=state['locators']['2'])['source']['text'] == TEXTS[1]
            checks += ['fresh_process_restart', 'durable_ids', 'no_duplicate_submission',
                       'batch_restart_loss_explicit', 'invalid_forget_confirmation_refused',
                       'scoped_pair_forget', 'unrelated_source_preserved', 'governance_retention_disclosed']
        elif name == 'replay_and_optout':
            before_root = digest(root)
            capture(1)
            assert p._episode_capture.status()['active_messages'] == 4
            assert call('elm_episode_search', query='synthetic_concise')['results'] == []
            assert call('elm_episode_read', locator=state['locators']['2'])['source']['text'] == TEXTS[1]
            extractor, batch_id = batch(state['locators']['3'])
            loc = state['locators']['3']
            p.episode_forget(loc, p.episode_forget_preview(loc)['plan_sha256'])
            refused(lambda: extractor.review(batch_id), 'batch_revoked')
            (home/'elm_episode_recall.json').write_text('{"enabled":false}')
            assert 'error' in call('elm_episode_read', locator=state['locators']['2'])
            assert inspector().candidates()['records'][0]['citation_status'] == 'not_checked_recall_disabled'
            (home/'elm_episode_capture.json').write_text('{"enabled":false}')
            assert inspector().status()['store'] == 'not_read_capture_disabled'
            # Forgetting remains usable after opt-out without silently enabling either setting.
            args = ['--hermes-home', str(home), '--locator', state['locators']['2']]
            preview = command([sys.executable, '-B', str(installed/'manage.py'), 'episode-forget-preview', *args])
            result = command([sys.executable, '-B', str(installed/'manage.py'), 'episode-forget', *args,
                              '--confirm-plan', preview['plan_sha256']])
            assert result['external_outcome_review_required']
            assert json.loads((home/'elm_episode_capture.json').read_text())['enabled'] is False
            assert before_root == digest(root) and counts(root) == [0, 2]
            checks += ['restart_replay_barrier', 'batch_revoked_after_forget', 'recall_optout',
                       'capture_optout', 'forget_cli_after_optout', 'canonical_not_erased']
        elif name == 'restart_blocks_dispatch':
            before_root = digest(root)
            record = inspector().candidates()['records'][0]
            assert record['local_queue_state'] == 'submitting'
            assert p.flush_episode_proposals()['status'] == 'unresolved_previous_submission'
            latest = capture(2); m.on_session_end(latest)
            assert p._proposal_last['status'] == 'unresolved_previous_submission'
            assert {r['local_queue_state'] for r in inspector().candidates()['records']} == {'submitting', 'queued'}
            loc = record['source_locator']
            preview = p.episode_forget_preview(loc)
            assert preview['external_outcome_review_required']
            p.episode_forget(loc, preview['plan_sha256'])
            assert p.flush_episode_proposals()['status'] == 'unresolved_previous_submission'
            assert {r['local_queue_state'] for r in inspector().candidates()['records']} == {'revoked_unknown', 'queued'}
            assert before_root == digest(root) and counts(root) == [0, 0]
            checks += ['interrupted_submission_no_automatic_retry', 'later_queue_remains_blocked',
                       'forget_does_not_hide_unknown_outcome', 'unknown_requires_operator_reconciliation']
        else: raise AssertionError('Unknown phase')
        state_file.write_text(json.dumps(state))
    finally:
        m.shutdown_all()
    return {'phase': name, 'checks': checks, 'governance_counts': counts(root)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase'); parser.add_argument('--base', type=Path)
    args = parser.parse_args()
    if args.phase:
        print(json.dumps(phase(args.phase, args.base))); return
    pin = subprocess.check_output(['git', '-C', str(HOST), 'rev-parse', 'HEAD'], text=True).strip()
    assert pin == EXPECTED_HOST, {'wrong_host_pin': pin}
    before_host = subprocess.check_output(['git', '-C', str(HOST), 'status', '--porcelain'], text=True)
    assert not before_host, 'Host must be clean before qualification'
    with tempfile.TemporaryDirectory(prefix='elm-integrated-synthetic-') as temporary:
        base = Path(temporary); setup(base)
        phases = [command([sys.executable, '-B', str(Path(__file__).resolve()), '--phase', name, '--base', str(base)])
                  for name in ('interrupt_before_seal', 'capture_and_seal', 'restart_and_forget', 'replay_and_optout')]
        uncertain = base/'uncertain_scenario'; uncertain.mkdir(); setup(uncertain)
        phases += [command([sys.executable, '-B', str(Path(__file__).resolve()), '--phase', name, '--base', str(uncertain)])
                   for name in ('interrupt_after_claim', 'restart_blocks_dispatch')]
    assert subprocess.check_output(['git', '-C', str(HOST), 'status', '--porcelain'], text=True) == before_host
    print(json.dumps({'status': 'PASS', 'host_commit': pin, 'host_clean': True,
        'fresh_worker_processes': len(phases), 'phases': phases,
        'model_calls': 0, 'live_user_data_operations': 0, 'deployment_performed': False,
        'network': 'socket operations blocked in test workers',
        'limitations': ['Batch candidates are not persisted or submitted.',
                        'Governance proposals survive scoped evidence forgetting; no claims accepted.',
                        'Synthetic lifecycle tests do not establish model quality or production readiness.']}, indent=2))


if __name__ == '__main__': main()
