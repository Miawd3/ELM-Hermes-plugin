"""Fresh disposable stock-plugin discovery plus real manager capture/search/read."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile

AREA = Path(__file__).resolve().parent
PLUGIN = AREA.parents[1]
HOST = Path(os.environ.get("HERMES_STOCK_SOURCE", str(AREA.parent / "integration_elm_20261106/isolated_runtime/hermes-stock"))).resolve()
sys.path[:0] = [str(HOST), str(PLUGIN / 'tests')]
from test_provider import engine


def no_network(event, args):
    if event in {'socket.connect', 'socket.getaddrinfo', 'socket.bind'}:
        raise RuntimeError('No network in native episode test')
sys.addaudithook(no_network)


def digest(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and not p.name.endswith(('-shm', '-wal'))}


with tempfile.TemporaryDirectory(prefix='elm-native-episode-') as temp:
    base = Path(temp); home = base/'profile'; home.mkdir(); root=base/'canonical'
    os.environ.update(HOME=str(base), HERMES_HOME=str(home), HERMES_RUNTIME_DIR=str(base/'runtime'),
                      HERMES_ENABLE_PROJECT_PLUGINS='0', PYTHONDONTWRITEBYTECODE='1')
    (home/'config.yaml').write_text('memory:\n  provider: elm\nplugins:\n  isolation: in_process\n')
    installed = home/'plugins/elm'
    shutil.copytree(PLUGIN, installed, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git', 'tests'))
    engine(root, 'init', '--project', 'orion')
    from plugins.memory import load_memory_provider, find_provider_dir
    from agent.memory_manager import MemoryManager
    assert find_provider_dir('elm').resolve() == installed.resolve()
    provider = load_memory_provider('elm')
    provider.save_config({"budget_mode": "legacy-estimate", 'root':str(root), 'project':'orion', 'mode':'read-only', 'budget':700}, str(home))
    binding = json.loads((home/'elm.json').read_text())
    for name, extra in [('capture', {'explicit_proposals':True,'proposal_author_id':'native_human'}), ('recall', {'budget':1200})]:
        (home/f'elm_episode_{name}.json').write_text(json.dumps({'format_version':1, 'enabled':True,
            'root_id':binding['root_id'], 'project':'orion', **extra}))
    manager=MemoryManager(); manager.add_provider(provider)
    manager.initialize_all('native', hermes_home=str(home), platform='cli', agent_context='primary')
    assert all(manager.has_tool(n) for n in ('elm_episode_search', 'elm_episode_read'))
    before = digest(root)
    rows=[{'message_uid':'native_user', 'role':'user', 'content':'Remember: instrument = synthetic cobalt telescope',
           'speaker_id':'native_human', 'timestamp':'2026-11-06T10:00:00Z'},
          {'message_uid':'native_assistant', 'role':'assistant', 'content':'Unverified assistant echo.',
           'speaker_id':'native_model', 'timestamp':1793959201.25}]
    manager.sync_all(rows[0]['content'], rows[1]['content'], session_id='native', messages=rows,
                     turn_author={'id':'native_human', 'is_bot':False})
    assert manager.flush_pending(timeout=10)
    found=json.loads(manager.handle_tool_call('elm_episode_search', {'query':'COBALT telescope'}))
    assert found['matched_messages']==1, found
    loc=found['results'][0]['locator']
    output=manager.handle_tool_call('elm_episode_read', {'locator':loc})
    read=json.loads(output)
    assert read['source']['text']==rows[0]['content']
    assert read['source']['source_timestamp']==rows[0]['timestamp']
    assert read['source']['source_speaker_id']=='native_human'
    assert read['trust']=='untrusted_source_evidence' and not read['accepted_memory']
    assert 'authoritative reference data' not in output
    manager.queue_prefetch_all('cobalt telescope', session_id='native')
    assert manager.flush_pending(timeout=10)
    if provider._worker: provider._worker.join(timeout=10)
    context=manager.prefetch_all('cobalt telescope', session_id='native')
    assert 'cobalt telescope' not in context.lower() and 'ELM-EPISODE' not in context
    manager.on_session_end(rows)
    assert provider.episode_proposal_snapshot()['records'][0]['status']=='queued'
    manager.shutdown_all()
    assert before==digest(root)
    other=load_memory_provider('elm'); second=MemoryManager(); second.add_provider(other)
    second.initialize_all('native_fresh', hermes_home=str(home), platform='cli', agent_context='primary')
    restarted=json.loads(second.handle_tool_call('elm_episode_read', {'locator':loc}))
    assert restarted==read
    (home/'elm_episode_recall.json').write_text('{"enabled":false}')
    assert 'error' in json.loads(second.handle_tool_call('elm_episode_read', {'locator':loc}))
    (home/'elm_episode_capture.json').unlink()
    preview=other.episode_forget_preview(loc)
    assert preview['source_messages_to_remove']==2 and preview['local_proposal_copies']==1
    receipt=other.episode_forget(loc,preview['plan_sha256'])
    assert receipt['status']=='source_evidence_forgotten_locally'
    assert not receipt['limits']['secure_erasure']
    assert not receipt['external_outcome_review_required']
    assert not second.has_tool('elm_episode_forget')
    # Operator path stays available after opt-out; restart/replay cannot restore source.
    for name, extra in [('capture', {'explicit_proposals':True,'proposal_author_id':'native_human'}), ('recall', {'budget':1200})]:
        (home/f'elm_episode_{name}.json').write_text(json.dumps({'format_version':1,'enabled':True,
            'root_id':binding['root_id'],'project':'orion',**extra}))
    second.shutdown_all()
    third_provider=load_memory_provider('elm'); third=MemoryManager(); third.add_provider(third_provider)
    third.initialize_all('native_replay',hermes_home=str(home),platform='cli',agent_context='primary')
    third.sync_all(rows[0]['content'],rows[1]['content'],session_id='native_replay',messages=rows,
                   turn_author={'id':'native_human','is_bot':False})
    assert third.flush_pending(timeout=10)
    assert json.loads(third.handle_tool_call('elm_episode_search',{'query':'cobalt'}))['results']==[]
    assert 'error' in json.loads(third.handle_tool_call('elm_episode_read',{'locator':loc}))
    snapshot=third_provider.episode_proposal_snapshot()
    assert snapshot['records'][0]['status']=='revoked'
    assert snapshot['records'][0]['payload']=={} and snapshot['records'][0]['evidence']=={}
    third.shutdown_all()
    assert before==digest(root)
    print(json.dumps({'native_plugin_discovery':'PASS', 'native_manager_capture':'PASS',
        'explicit_search_and_read':'PASS','exact_metadata':'PASS','restart_same_locator':'PASS',
        'live_optout':'PASS','no_episode_prefetch':'PASS','canonical_unchanged':'PASS',
        'operator_forget_after_optout':'PASS','proposal_scrubbed':'PASS','restart_replay_denied':'PASS',
        'no_destructive_model_tool':'PASS','model_calls':0,'network_calls':0,'receipt':receipt}, indent=2))
