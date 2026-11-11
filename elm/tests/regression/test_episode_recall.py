"""Deterministic retrieval contracts through the pinned real Hermes manager."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

import test_episode_capture as capture_tests
from test_episode_capture import config, pair, PLUGIN, HOST
from elm_plugin.provider import ElmMemoryProvider
from elm_plugin.storage import load_binding, CONFIG
from elm_plugin.episode_recall import CONFIG_NAME, encoded, estimate
from elm_plugin.episode_capture import CaptureRefused
from agent.memory_manager import MemoryManager


def hashes(path):
    return {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob('*') if p.is_file() and not p.name.endswith(('-shm', '-wal'))}


class RecallBehavior(unittest.TestCase):
    setUp = capture_tests.RealProviderHooks.setUp

    def start(self, recall=True, context='primary', budget=1200, capture=True, mode='read-only'):
        p = ElmMemoryProvider()
        p.save_config({"budget_mode": "legacy-estimate", 'root': str(self.root), 'project': 'orion', 'mode': mode, 'budget': 700}, str(self.home))
        binding = load_binding(self.home)
        if capture:
            config(self.home, binding, retention_seconds=60)
        if recall:
            (self.home / CONFIG_NAME).write_text(json.dumps({'format_version': 1, 'enabled': True,
                'root_id': binding.root_id, 'project': binding.project, 'budget': budget}))
        m = MemoryManager()
        m.add_provider(p)
        m.initialize_all('session1', hermes_home=str(self.home), platform='cli', agent_context=context)
        self.addCleanup(m.shutdown_all)
        if p._episode_capture:
            p._episode_capture.clock = lambda: 1000.0
        return p, m

    def ingest(self, p, m, rows=None):
        rows = rows or pair(user='Orion uses emerald launch.', assistant='Noted emerald launch.')
        m.sync_all(rows[0]['content'], rows[-1]['content'], session_id='session1', messages=rows,
                   turn_author={'id': 'user1', 'is_bot': False})
        self.assertTrue(m.flush_pending(timeout=10))
        return rows

    def call(self, m, name='elm_episode_search', **args):
        return json.loads(m.handle_tool_call(name, args or {'query': 'emerald'}))

    def test_separate_opt_in_and_fixed_surface(self):
        p, m = self.start(recall=False)
        self.ingest(p, m)
        self.assertTrue(m.has_tool('elm_episode_search'))
        self.assertTrue(m.has_tool('elm_episode_read'))
        self.assertEqual(self.call(m)['error'], 'episode_recall_unavailable')
        self.assertFalse(p.episode_capture_status()['retrieval_enabled'])
        self.assertIsNone(p._episode_recall)

    def test_no_capture_or_non_primary_has_no_retrieval(self):
        for kwargs in ({'capture': False}, {'context': 'subagent'}):
            with self.subTest(**kwargs):
                p, m = self.start(**kwargs)
                self.assertEqual(self.call(m)['error'], 'episode_recall_unavailable')
                m.shutdown_all()

    def test_exact_metadata_and_untrusted_complete_read(self):
        p, m = self.start()
        rows = pair(user='Emerald café requires rollback.', assistant='Assistant observation only.')
        rows[0].update(speaker_id='user1', timestamp='2026-11-06T07:12:01.123400+02:30')
        rows[1].update(speaker_id='assistantA', timestamp=1234.5)
        self.ingest(p, m, rows)
        result = self.call(m, query='CAFÉ emerald')
        self.assertEqual(result['matched_messages'], 1)
        self.assertEqual(result['trust'], 'untrusted_source_evidence')
        self.assertFalse(result['accepted_memory'])
        self.assertFalse(result['source_identity_verified'])
        source = result['results'][0]
        self.assertEqual(source['source_speaker_id'], 'user1')
        self.assertEqual(source['source_author_id'], 'user1')
        self.assertEqual(source['source_timestamp'], rows[0]['timestamp'])
        read = self.call(m, 'elm_episode_read', locator=source['locator'])
        self.assertEqual(read['source']['text'], rows[0]['content'])
        self.assertTrue(read['complete_stored_text'])
        assistant = self.call(m, query='observation')['results'][0]
        self.assertEqual(assistant['source_speaker_id'], 'assistantA')
        self.assertIsNone(assistant['source_author_id'])
        self.assertEqual(assistant['source_timestamp'], 1234.5)

    def test_deterministic_literal_matching_limits_and_order(self):
        p, m = self.start()
        self.ingest(p, m)
        p._episode_capture.clock = lambda: 1001.0
        self.ingest(p, m, pair(2, user='EMERALD launch second.', assistant='No mention.'))
        result = self.call(m, query='emerald launch', limit=1)
        self.assertEqual(result, self.call(m, query='LAUNCH emerald', limit=1))
        self.assertEqual(result['results'][0]['message_uid'], 'u2')
        self.assertEqual(result['matched_messages'], 3)
        self.assertEqual(result['omitted_messages'], 2)
        self.assertEqual(self.call(m, query='" OR 1=1 --')['results'], [])
        self.assertEqual(self.call(m, query='emerald %')['results'], [])

    def test_expiry_read_search_and_restart_do_not_resurrect(self):
        p, m = self.start()
        self.ingest(p, m)
        locator = self.call(m)['results'][0]['locator']
        p._episode_capture.clock = lambda: 1060.0
        self.assertEqual(self.call(m)['results'], [])
        self.assertEqual(self.call(m, 'elm_episode_read', locator=locator)['error'], 'episode_source_unavailable')
        m.shutdown_all()
        p2, m2 = self.start()
        p2._episode_capture.clock = lambda: 1061.0
        self.assertEqual(self.call(m2)['results'], [])
        self.ingest(p2, m2)
        self.assertEqual(self.call(m2)['results'], [])

    def test_restart_preserves_locator_and_source(self):
        p, m = self.start()
        self.ingest(p, m)
        before = self.call(m)
        m.shutdown_all()
        p2, m2 = self.start()
        self.assertEqual(before, self.call(m2))
        self.assertIn('text', self.call(m2, 'elm_episode_read', locator=before['results'][0]['locator'])['source'])

    def test_cross_scope_and_wrong_episode_locators_are_refused(self):
        p, m = self.start()
        self.ingest(p, m)
        locator = self.call(m)['results'][0]['locator']
        for wrong in (locator.replace(p._episode_capture.scope, 'f'*64),
                      locator.replace('episode_', 'episode_00000000-0000-0000-0000-000000000000/') ,
                      locator.rsplit('/', 1)[0]+'/missing'):
            result = self.call(m, 'elm_episode_read', locator=wrong)
            self.assertIn('error', result)
            self.assertNotIn('emerald', encoded(result))
        other = self.base/'other'; other.mkdir()
        self.assertEqual(json.loads(p.handle_tool_call('elm_episode_search', {'query': 'emerald'}, hermes_home=str(other)))['error'], 'profile_mismatch')

    def test_live_binding_and_each_optout_fail_closed(self):
        p, m = self.start()
        self.ingest(p, m)
        for path in (self.home / CONFIG_NAME, self.home / 'elm_episode_capture.json', self.home / CONFIG):
            original = path.read_bytes()
            value = json.loads(original)
            if path.name == CONFIG: value['mode'] = 'proposal-only'
            else: value['enabled'] = False
            path.write_text(json.dumps(value))
            self.assertIn('error', self.call(m))
            self.assertNotIn('emerald', encoded(self.call(m)))
            path.write_bytes(original)
        self.assertTrue(self.call(m)['results'])
        m.shutdown_all()
        self.assertIn('error', self.call(m))

    def test_enabled_after_initialize_requires_restart(self):
        p, m = self.start(recall=False)
        self.ingest(p, m)
        b = load_binding(self.home)
        (self.home / CONFIG_NAME).write_text(json.dumps({'format_version': 1, 'enabled': True,
            'root_id': b.root_id, 'project': b.project, 'budget': 1200}))
        self.assertEqual(self.call(m)['error'], 'episode_recall_unavailable')

    def test_unknown_fields_bad_queries_and_bool_limits_rejected(self):
        p, m = self.start()
        for args in ({'query':'emerald','project':'other'}, {'query':'emerald','authority':'accepted'},
                     {'query':'emerald','limit':True}, {'query':'emerald','limit':9}, {'query':' '},
                     {'query':' '.join('term'+str(i) for i in range(18))}, {'query':'x'*257}):
            self.assertIn('error', json.loads(m.handle_tool_call('elm_episode_search', args)))

    def test_whole_response_budget_and_oversized_read(self):
        p, m = self.start(budget=600)
        rows = pair(user='emerald ' + 'é'*3000, assistant='reply')
        self.ingest(p, m, rows)
        result = self.call(m)
        raw = encoded(result)
        self.assertEqual(result['serialized_bytes'], len(raw.encode('utf-8')))
        self.assertEqual(result['estimated_tokens'], estimate(result))
        self.assertLessEqual(result['estimated_tokens'], 600)
        self.assertTrue(result['results'][0]['excerpt_truncated'])
        read = self.call(m, 'elm_episode_read', locator=result['results'][0]['locator'])
        self.assertEqual(read['error'], 'episode_result_exceeds_budget')
        self.assertNotIn('text', read)

    def test_minimum_budget_reports_omissions_not_truncation(self):
        p, m = self.start(budget=256)
        self.ingest(p, m)
        result = self.call(m)
        self.assertLessEqual(estimate(result), 256)
        self.assertEqual(result['matched_messages'], 2)
        self.assertEqual(result['omitted_messages'], 2)
        self.assertEqual(result['results'], [])

    def test_read_only_search_and_no_canonical_promotions(self):
        p, m = self.start()
        self.ingest(p, m)
        before_root, before_capture = hashes(self.root), p._episode_capture.path.read_bytes()
        result = self.call(m)
        self.call(m, 'elm_episode_read', locator=result['results'][0]['locator'])
        self.assertEqual(before_root, hashes(self.root))
        self.assertEqual(before_capture, p._episode_capture.path.read_bytes())
        with closing(sqlite3.connect(p._episode_capture.path)) as con:
            self.assertEqual(con.execute('SELECT count(*) FROM episode_proposals').fetchone()[0], 0)

    def test_episode_never_in_canonical_context_or_prefetch(self):
        p, m = self.start()
        self.ingest(p, m)
        canonical = self.call(m, 'elm_context', query='emerald')
        self.assertNotIn('emerald', encoded(canonical).lower())
        # Explicitly prime existing canonical recall and consume through actual manager.
        p.queue_prefetch('emerald', session_id='session1')
        if p._worker: p._worker.join(timeout=10)
        wrapped = m.prefetch_all('emerald', session_id='session1')
        self.assertNotIn('emerald', wrapped.lower())
        self.assertNotIn('ELM-EPISODE', wrapped)
        self.assertIn('elm_episode_read', p.system_prompt_block())

    def test_store_missing_corrupt_locked_or_scope_changed_fails_without_source(self):
        p, m = self.start()
        self.ingest(p, m)
        path = p._episode_capture.path
        original = path.read_bytes()
        path.unlink()
        self.assertIn('error', self.call(m))
        self.assertFalse(path.exists())
        path.write_bytes(b'not a database')
        self.assertIn('error', self.call(m))
        path.write_bytes(original)
        with closing(sqlite3.connect(path)) as con:
            con.execute('BEGIN EXCLUSIVE')
            self.assertIn('error', self.call(m))
            con.rollback()
        with closing(sqlite3.connect(path)) as con, con:
            con.execute("UPDATE meta SET value='other' WHERE key='project'")
        result = self.call(m)
        self.assertIn('error', result)
        self.assertNotIn('emerald', encoded(result))

    def test_text_and_metadata_corruption_fail_closed(self):
        p, m = self.start()
        self.ingest(p, m)
        path = p._episode_capture.path
        original = path.read_bytes()
        for sql in ("UPDATE messages SET text='TAMPERED'", "UPDATE messages SET source_speaker_id='forged'"):
            with closing(sqlite3.connect(path)) as con, con: con.execute(sql)
            self.assertIn('error', self.call(m))
            path.write_bytes(original)

    def test_restricted_capture_produces_no_searchable_evidence(self):
        p, m = self.start()
        rows = pair(user='RESTRICTED_EMERALD', assistant='RESTRICTED_EMERALD copied.')
        rows[0]['data_use'] = ['restricted']
        self.ingest(p, m, rows)
        self.assertEqual(self.call(m, query='RESTRICTED_EMERALD')['results'], [])

    def test_withdrawal_during_read_is_checked_before_disclosure(self):
        p, m = self.start()
        self.ingest(p, m)
        reader = p._episode_recall
        original = reader._source
        def withdraw(row):
            (self.home / CONFIG_NAME).write_text('{"enabled":false}')
            return original(row)
        with patch.object(reader, '_source', withdraw):
            self.assertIn('error', self.call(m))


if __name__ == '__main__':
    unittest.main(verbosity=2)
