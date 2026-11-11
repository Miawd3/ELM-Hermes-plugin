"""Ordinary sync refreshes validated equal-content stats, not content identity."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_provider import note, ElmMemoryProvider
from test_typed_memory import typed_note
from elm_plugin.engine import run_engine


def engine(root, *args):
    # Exercise the same -B -s -S, scrubbed source-only boundary as the provider.
    return run_engine(root.parent, root, *args)


def section_key(root, relative, heading='Deployment'):
    return next(s['section_key'] for s in projection(root, relative)['sections'] if s['heading'] == heading)


UID = 'doc_11111111-1111-4111-8111-111111111111'


def projection(root, relative):
    """Closed, read-only fixture inspection, including internal and public IDs."""
    uri = (root/'.elm/index.sqlite').resolve().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True)) as con:
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA query_only=ON')
        doc = dict(con.execute('SELECT * FROM documents WHERE path=?', (relative,)).fetchone())
        doc_id = doc['id']
        result = {'document': doc}
        for table, field in [('sections', 'document_id'), ('properties', 'document_id'),
                             ('document_tags', 'document_id'), ('links', 'source_document_id'),
                             ('sections_fts', 'document_id')]:
            result[table] = [dict(r) for r in con.execute(f'SELECT * FROM {table} WHERE {field}=? ORDER BY rowid', (doc_id,))]
        result['schema'] = con.execute("SELECT value FROM elm_meta WHERE key='index_schema_version'").fetchone()[0]
        return result


class EqualContentStatRefresh(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='elm-stat-', dir=os.environ['TMPDIR'])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'s'
        self.home = Path(self.temp.name)/'p'; self.home.mkdir()
        engine(self.root, 'init', '--project', 'orion')
        self.source = 'elm://section/' + section_key(self.root, '20_projects/orion/ACTIVE_CONTEXT.md', 'Current state')

    def add(self, typed=False):
        relative = '20_projects/orion/TARGET.md'
        body = 'statproof amber canary prefers numbered concise steps.'
        text = typed_note('orion', body, source=self.source) if typed else note('orion', body)
        if typed:
            text = 'ELM ID: ' + UID + '\n' + text
        path = self.root/relative
        path.write_text(text, encoding='utf-8')
        self.assertEqual([], engine(self.root, 'sync')['errors'])
        return path, relative

    def provider(self):
        provider = ElmMemoryProvider()
        provider.save_config({'root': str(self.root), 'project': 'orion', 'mode': 'read-only',
                              'recall_mode': 'explicit-only', 'budget_mode': 'legacy-estimate', 'budget': 1200}, str(self.home))
        provider.initialize('stat-test', hermes_home=str(self.home))
        self.addCleanup(provider.shutdown)
        return provider

    def stat_roundtrip(self, typed):
        path, relative = self.add(typed)
        provider = self.provider()
        intent = {'lane': 'user', 'purpose': 'communication'} if typed else {}
        key = section_key(self.root, relative)
        call = lambda: json.loads(provider.handle_tool_call('elm_read', {'section': key, **intent}))
        direct_before = call(); self.assertIn('statproof amber', direct_before['text'])
        before = projection(self.root, relative)
        raw = path.read_bytes(); old_stat = path.stat()
        os.utime(path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns + 7_000_000_000))
        self.assertEqual(raw, path.read_bytes())
        self.assertEqual(before['document']['content_hash'], hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(old_stat.st_mtime_ns, path.stat().st_mtime_ns)
        self.assertFalse(engine(self.root, 'status', '--readiness-only')['healthy'])
        self.assertIn('error', call(), 'Guarded reads must refuse changed stats before explicit sync')
        synced = engine(self.root, 'sync')
        self.assertEqual([], synced['errors']); self.assertEqual(0, synced['changed'])
        ready = engine(self.root, 'status', '--readiness-only')
        # This is the exact old-v8 RED: ordinary sync reports no errors but stays stale.
        self.assertTrue(ready['healthy'], {'sync': synced, 'ready': ready})
        self.assertFalse(ready['sync_required'])
        after = projection(self.root, relative)
        expected = json.loads(json.dumps(before))
        expected['document'].update(mtime_ns=path.stat().st_mtime_ns, size_bytes=len(raw))
        self.assertEqual(expected, after, 'Only derived mtime/size may change; IDs, content and labels must survive')
        self.assertEqual(direct_before, call())
        stable = engine(self.root, 'sync')
        self.assertEqual([], stable['errors']); self.assertEqual(0, stable['changed'])
        self.assertEqual(after, projection(self.root, relative))
        self.assertEqual(raw, path.read_bytes())

    def test_legacy_equal_bytes_changed_mtime_ordinary_sync_recovers(self):
        self.stat_roundtrip(False)

    def test_typed_uid_equal_bytes_changed_mtime_ordinary_sync_recovers(self):
        self.stat_roundtrip(True)

    def test_content_change_with_same_size_and_mtime_is_reindexed(self):
        for typed in (False, True):
            with self.subTest(typed=typed):
                path, relative = self.add(typed)
                original = projection(self.root, relative)
                raw = path.read_bytes(); st = path.stat()
                changed = raw.replace(b'amber', b'ochre')
                self.assertNotEqual(raw, changed); self.assertEqual(len(raw), len(changed))
                path.write_bytes(changed)
                os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
                self.assertEqual(st.st_mtime_ns, path.stat().st_mtime_ns)
                self.assertFalse(engine(self.root, 'status', '--readiness-only')['healthy'])
                synced = engine(self.root, 'sync')
                self.assertEqual([], synced['errors']); self.assertEqual(1, synced['changed'])
                self.assertTrue(engine(self.root, 'status', '--readiness-only')['healthy'])
                current = projection(self.root, relative)
                self.assertEqual(original['document']['id'], current['document']['id'])
                self.assertEqual(original['document']['document_uid'], current['document']['document_uid'])
                self.assertNotEqual(original['document']['content_hash'], current['document']['content_hash'])
                self.assertTrue(any('statproof ochre' in s['text'] for s in current['sections']))
                self.assertFalse(any('statproof amber' in s['text'] for s in current['sections']))
                self.assertEqual([s['section_key'] for s in original['sections']], [s['section_key'] for s in current['sections']])

    def test_malformed_typed_header_stays_stale_then_exact_restoration_recovers(self):
        path, relative = self.add(True)
        provider = self.provider()
        key = section_key(self.root, relative)
        raw = path.read_bytes(); before = projection(self.root, relative)
        path.write_bytes(raw.replace(b'Memory kind: preference', b'Memory kind: diagnosis'))
        for delta in (7_000_000_000, 14_000_000_000):
            st = path.stat(); os.utime(path, ns=(st.st_atime_ns, before['document']['mtime_ns'] + delta))
            synced = engine(self.root, 'sync')
            self.assertTrue(synced['errors'])
            self.assertFalse(engine(self.root, 'status', '--readiness-only')['healthy'])
            self.assertIn('error', json.loads(provider.handle_tool_call('elm_read',
                          {'section': key, 'lane': 'user', 'purpose': 'communication'})))
            self.assertEqual(before, projection(self.root, relative), 'Rejected bytes must not refresh a cached projection')
        path.write_bytes(raw)
        st = path.stat(); os.utime(path, ns=(st.st_atime_ns, before['document']['mtime_ns'] + 21_000_000_000))
        self.assertEqual([], engine(self.root, 'sync')['errors'])
        self.assertTrue(engine(self.root, 'status', '--readiness-only')['healthy'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
