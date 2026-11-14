"""Compaction rotation, chat deletion, schema setup and automatic-recall relevance."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from elm_plugin.stock_store import Store, session_key, SCHEMA_VERSION
from elm_plugin.stock_runtime import Runtime, content_terms


class Ctx:
    surface = 'desktop'
    llm = None
    def session_surface(self): return self.surface


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'db'
        self.opened = []
        def connect():
            db = sqlite3.connect(self.path)
            self.opened.append(db)
            return db
        self.store = Store(connect)
        self.ctx = Ctx()
        self.rt = Runtime(self.ctx, self.store)
    def tearDown(self):
        for db in self.opened:
            db.close()
        self.tmp.cleanup()
    def cmd(self, text, sid='a', platform='desktop'):
        return self.rt.command(text, session_id=sid, platform=platform)
    def search(self, query, sid='a'):
        return json.loads(self.rt.tool({'action': 'search', 'query': query}, session_id=sid))
    def raw(self, sql, *args):
        with closing_db(self.path) as db:
            return db.execute(sql, args).fetchall()


class closing_db:
    def __init__(self, path): self.db = sqlite3.connect(path)
    def __enter__(self): return self.db
    def __exit__(self, *exc): self.db.close()


class SchemaTests(Base):
    def test_schema_set_up_once_and_reads_take_no_write_lock(self):
        self.cmd('on')
        self.assertEqual(self.raw('PRAGMA user_version')[0][0], SCHEMA_VERSION)
        blocker = sqlite3.connect(self.path, timeout=0)
        blocker.execute('BEGIN IMMEDIATE')  # another writer holds the lock
        try:
            self.store.connection = lambda: sqlite3.connect(self.path, timeout=0.05)
            # Reads must not need the write lock any more.
            sid = session_key('a', 'desktop')
            self.assertEqual(self.store.records(sid), [])
            self.assertEqual(self.store.read_stamp(sid)['enabled'], 1)
            self.assertEqual(self.store.resolve('a', 'desktop'), sid)
        finally:
            blocker.rollback(); blocker.close()

    def test_old_unversioned_database_is_upgraded_in_place(self):
        with closing_db(self.path) as db:
            db.execute('CREATE TABLE stock_sessions (session TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0, project TEXT, user_scope INTEGER NOT NULL DEFAULT 0, capture INTEGER NOT NULL DEFAULT 0, agent INTEGER NOT NULL DEFAULT 0)')
            db.execute('CREATE TABLE stock_records (id TEXT PRIMARY KEY, scope TEXT NOT NULL, kind TEXT NOT NULL, content TEXT NOT NULL, tags TEXT NOT NULL, status TEXT NOT NULL, source_session TEXT NOT NULL, source_id TEXT, created REAL NOT NULL, updated REAL NOT NULL)')
            sid = session_key('a', 'desktop')
            db.execute('INSERT INTO stock_sessions(session,enabled) VALUES(?,1)', (sid,))
            db.execute("INSERT INTO stock_records VALUES('r1',?,'reference','Door code','[]','approved',?,NULL,1,1)", ('chat:' + sid, sid))
            db.commit()
        self.assertEqual(len(self.search('door')['results']), 1)
        self.assertEqual(self.raw('PRAGMA user_version')[0][0], SCHEMA_VERSION)


class RotationTests(Base):
    def test_compaction_rotation_keeps_chat_memory_and_settings(self):
        self.cmd('on'); self.cmd('save reference the door code is 4411')
        self.rt.after_compaction(session_id='a2', old_session_id='a')
        self.assertEqual(len(self.search('door', sid='a2')['results']), 1)
        self.rt.after_compaction(session_id='a3', old_session_id='a2')
        self.assertEqual(len(self.search('door', sid='a3')['results']), 1)
        self.cmd('save reference window is green', sid='a3')
        self.assertEqual(len(self.search('window', sid='a')['results']), 1)  # one chat, one memory

    def test_rotation_of_unused_chat_stores_nothing(self):
        self.rt.after_compaction(session_id='x2', old_session_id='x')
        self.assertEqual(self.raw('SELECT COUNT(*) FROM stock_session_alias')[0][0], 0)

    def test_in_place_compaction_is_noop(self):
        self.cmd('on'); self.rt.after_compaction(session_id='a', old_session_id='')
        self.assertNotIn('error', self.cmd('status'))

    def test_local_grant_follows_rotation(self):
        self.store.grant_local('u')
        self.ctx.surface = 'local'
        self.assertNotIn('error', self.cmd('save reference door blue', sid='u', platform='local'))
        self.rt.after_compaction(session_id='u2', old_session_id='u')
        self.assertEqual(len(self.search('door', sid='u2')['results']), 1)
        self.store.revoke_local('u2')  # revoking the new ID revokes the chat
        self.assertIn('error', self.search('door', sid='u'))

    def test_other_chats_still_isolated_after_rotation(self):
        self.cmd('on'); self.cmd('save reference door secret')
        self.rt.after_compaction(session_id='a2', old_session_id='a')
        self.cmd('on', sid='b')
        self.assertEqual(self.search('door', sid='b')['results'], [])


class DeleteTests(Base):
    def test_delete_purges_chat_only_data_and_keeps_shared(self):
        self.cmd('on'); self.cmd('capture on'); self.cmd('project Door'); self.cmd('user on')
        self.cmd('save reference private chat note door')
        self.cmd('save project shared project door note')
        self.cmd('save user user likes doors')
        self.rt.after_turn(session_id='a', user_message='hi door', assistant_response='hello')
        self.rt.session_deleted(session_id='a', reason='delete')
        self.assertEqual(self.raw("SELECT COUNT(*) FROM stock_records WHERE scope LIKE 'chat:%'")[0][0], 0)
        self.assertEqual(self.raw('SELECT COUNT(*) FROM stock_sources')[0][0], 0)
        self.assertEqual(self.raw('SELECT COUNT(*) FROM stock_sessions')[0][0], 0)
        self.assertEqual(self.raw("SELECT COUNT(*) FROM stock_records WHERE scope NOT LIKE 'chat:%'")[0][0], 2)
        self.cmd('on', sid='b'); self.cmd('project Door', sid='b')
        self.assertEqual(len(self.search('door', sid='b')['results']), 1)

    def test_archive_keeps_everything(self):
        self.cmd('on'); self.cmd('save reference door')
        self.rt.session_deleted(session_id='a', reason='archive')
        self.assertEqual(len(self.search('door')['results']), 1)

    def test_deleting_whole_rotated_chain_purges(self):
        self.cmd('on'); self.cmd('save reference door')
        self.rt.after_compaction(session_id='a2', old_session_id='a')
        self.rt.session_deleted(session_id='a2', reason='delete', deleted_ids=['a', 'a2'])
        self.assertEqual(self.raw('SELECT COUNT(*) FROM stock_records')[0][0], 0)
        self.assertEqual(self.raw('SELECT COUNT(*) FROM stock_session_alias')[0][0], 0)

    def test_pruning_old_segment_keeps_live_chat(self):
        self.cmd('on'); self.cmd('save reference door')
        self.rt.after_compaction(session_id='a2', old_session_id='a')
        self.rt.session_deleted(session_id='a', reason='prune')
        self.assertEqual(len(self.search('door', sid='a2')['results']), 1)

    def test_other_chat_untouched(self):
        self.cmd('on'); self.cmd('on', sid='b'); self.cmd('save reference door', sid='b')
        self.rt.session_deleted(session_id='a', reason='delete')
        self.assertEqual(len(self.search('door', sid='b')['results']), 1)


class HintTests(Base):
    def test_local_denial_explains_next_step(self):
        out = json.loads(self.cmd('status', sid='abc-123', platform='local'))
        self.assertEqual(out['error'], 'exact_session_cli_grant_required')
        self.assertIn('hermes elm grant abc-123', out['hint'])

    def test_hint_never_echoes_unsafe_id(self):
        out = json.loads(self.cmd('status', sid='x; rm -rf ~', platform='local'))
        self.assertNotIn('rm -rf', out['hint'])

    def test_classic_cli_hint(self):
        out = json.loads(self.cmd('search door', sid='z', platform='cli'))
        self.assertIn('/elm on', out['hint'])


class RecallTests(Base):
    def setUp(self):
        super().setUp()
        self.cmd('on')
        self.cmd('save reference the deploy script lives in tools/ship.ps1')
        self.cmd('save reference my favourite colour is teal')
        self.cmd('save reference the cat is named Miso')

    def recall(self, message, history=None, sid='a'):
        result = self.rt.before_turn(session_id=sid, user_message=message, conversation_history=history or [])
        return [] if result is None else [r['text'] for r in json.loads(result['context'].split('\n', 1)[1])]

    def test_stopwords_alone_inject_nothing(self):
        self.assertEqual(self.recall('what is the plan for my day?'), [])

    def test_trivial_and_slash_messages_skip(self):
        for message in ('ok', 'thanks!', '/elm status', ''):
            self.assertEqual(self.recall(message), [])

    def test_relevant_note_injected_once(self):
        self.assertEqual(self.recall('where is the deploy script?'), ['the deploy script lives in tools/ship.ps1'])
        self.assertEqual(self.recall('run the deploy script again'), [])

    def test_compaction_allows_reinjection(self):
        self.recall('where is the deploy script?')
        self.rt.after_compaction(session_id='a', old_session_id='')
        self.assertEqual(self.recall('where is the deploy script?'), ['the deploy script lives in tools/ship.ps1'])

    def test_id_already_in_history_not_repeated(self):
        first = self.rt.before_turn(session_id='a', user_message='deploy script', conversation_history=[])
        fresh = Runtime(self.ctx, self.store)  # e.g. after a restart: memory of injections is gone
        history = [{'role': 'user', 'content': 'deploy script\n\n' + first['context']}]
        self.assertIsNone(fresh.before_turn(session_id='a', user_message='deploy script', conversation_history=history))

    def test_long_query_needs_several_matches(self):
        self.assertEqual(self.recall('please summarize colour theory history quickly for students today'), [])
        self.assertEqual(self.recall('what colour did I say is my favourite, teal or blue?'), ['my favourite colour is teal'])

    def test_multimodal_message(self):
        message = [{'type': 'text', 'text': 'what is the cat called'}, {'type': 'image_url', 'image_url': {'url': 'x'}}]
        self.assertEqual(self.recall(message), ['the cat is named Miso'])

    def test_explicit_search_unchanged_by_stopword_filter(self):
        # Explicit searches still match any word; only automatic recall filters stopwords.
        self.assertEqual(len(self.search('the')['results']), 2)

    def test_multimodal_turn_is_captured(self):
        self.cmd('capture on')
        self.rt.after_turn(session_id='a', user_message=[{'type': 'text', 'text': 'look at this door'}, {'type': 'image_url'}],
                           assistant_response='It is a red door.')
        self.assertEqual(self.raw('SELECT user_text FROM stock_sources')[0][0], 'look at this door')

    def test_content_terms(self):
        self.assertEqual(content_terms('What is THE deploy script for 2 apps?'), ['deploy', 'script', '2', 'apps'])


if __name__ == '__main__':
    unittest.main()
