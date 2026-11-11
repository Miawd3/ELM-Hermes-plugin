"""Real-engine regression controls for the independent index review findings."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from elm_plugin import workspace_index as module
from elm_plugin.engine import run_engine
from test_workspace_index import record


class IndexRepairs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='index-repairs-', dir=os.environ['TMPDIR'])
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.home = self.base/'profile'
        self.home.mkdir()
        self.index = module.WorkspaceIndex(self.home, self.base/'cache')

    def test_source_header_line_delimiters_roundtrip_exactly(self):
        for separator in ['\n', '\r', '\r\n', '\v', '\f', '\x1c', '\x1d', '\x1e', '\u0085', '\u2028', '\u2029']:
            with self.subTest(separator=repr(separator)):
                r = record(text='amber provenance control')
                r['sources'] = [{'ref': 'fixture:源'+separator+'Memory lane: user',
                                 'quote': 'Invented first'+separator+'second 🟡',
                                 'revision': 1, 'sha256': 'a'*64}]
                hit = self.index.query('workspace:a', [r], 'amber')['results'][0]
                self.assertEqual(r['sources'], hit['sources'])
                self.assertEqual(r['sources'], self.index.read('workspace:a', [r], hit['section'])['sources'])
                folder = self.index.root/hit['generation']
                with closing(sqlite3.connect(folder/'root/.elm/index.sqlite')) as con:
                    encoded = con.execute("SELECT p.value FROM properties p JOIN documents d ON d.id=p.document_id WHERE p.key='source_refs' AND d.path LIKE ?", (module.PREFIX+'%',)).fetchone()[0]
                self.assertEqual(r['sources'], json.loads(encoded)['sources'])
                self.assertEqual(1, self.index.status('workspace:a')['section_count'])

    def test_force_repairs_unreadable_manifest_while_ordinary_reads_fail_closed(self):
        records = [record()]
        other = self.index.build('workspace:other', [record('rec_other')])
        selected = self.index.query('workspace:a', records, 'amber')
        locator = selected['results'][0]['section']
        for damage in ('truncate', 'missing'):
            with self.subTest(damage=damage):
                path = self.index.root/selected['generation']/'manifest.json'
                if damage == 'truncate':
                    path.write_text('{', encoding='utf-8')
                else:
                    path.unlink()
                reopened = module.WorkspaceIndex(self.home, self.base/'cache')
                for operation in (lambda: reopened.status('workspace:a'),
                                  lambda: reopened.query('workspace:a', records, 'amber'),
                                  lambda: reopened.read('workspace:a', records, locator)):
                    with self.assertRaises(module.IndexError) as caught:
                        operation()
                    self.assertEqual('corrupt_index', caught.exception.code)
                repaired = reopened.build('workspace:a', records, force=True)
                self.assertNotEqual(selected['generation'], repaired['generation'])
                self.assertEqual(selected['snapshot_sha256'], repaired['snapshot_sha256'])
                self.assertTrue(path.parent.is_dir())  # no destructive old-root rebuild
                self.assertEqual(other['generation'], reopened.status('workspace:other')['generation'])
                selected = reopened.query('workspace:a', records, 'amber')
                self.assertEqual(records[0]['sources'], selected['results'][0]['sources'])
                self.assertEqual(records[0]['text'], selected['results'][0]['text'])
                with self.assertRaises(module.IndexError):
                    reopened.read('workspace:a', records, locator)
                locator = selected['results'][0]['section']

    def test_force_failed_validation_retains_corrupt_selection_until_success(self):
        records = [record()]
        first = self.index.build('workspace:a', records)
        pointer = self.index._pointer('workspace:a')
        old_pointer = pointer.read_bytes()
        (self.index.root/first['generation']/'manifest.json').write_text('{', encoding='utf-8')
        statuses = []
        real = module.run_engine
        def corrupt_staging(home, root, *args, **kwargs):
            if args[0] == 'status':
                with closing(sqlite3.connect(root/'.elm/index.sqlite')) as con:
                    with con:
                        con.execute("UPDATE elm_meta SET value='0' WHERE key='index_schema_version'")
                result = real(home, root, *args, **kwargs)
                statuses.append(result)
                return result
            return real(home, root, *args, **kwargs)
        with patch.object(module, 'run_engine', side_effect=corrupt_staging):
            with self.assertRaises(module.IndexError) as caught:
                self.index.build('workspace:a', records, force=True)
        self.assertEqual('index_validation_failed', caught.exception.code)
        self.assertTrue(statuses, 'Forced repair must attempt a new real generation')
        self.assertFalse(statuses[0]['healthy'])
        self.assertEqual(old_pointer, pointer.read_bytes())
        reopened = module.WorkspaceIndex(self.home, self.base/'cache')
        with self.assertRaises(module.IndexError):
            reopened.query('workspace:a', records, 'amber')
        second = reopened.build('workspace:a', records, force=True)
        self.assertNotEqual(first['generation'], second['generation'])
        self.assertEqual(second['generation'], reopened.status('workspace:a')['generation'])
        self.assertTrue(list(self.index.root.glob('gen_*/failure.json')))
        print(json.dumps({'real_failed_repair_validation': statuses}))

    def test_force_never_adopts_foreign_cache_or_profile(self):
        records = [record()]
        self.index.build('workspace:a', records)
        pointer = self.index._pointer('workspace:a')
        original = pointer.read_bytes()
        foreign = module.WorkspaceIndex(self.base/'foreign-profile', self.base/'cache')
        with self.assertRaises(module.IndexError) as caught:
            foreign.build('workspace:a', records, force=True)
        self.assertEqual('unowned_cache', caught.exception.code)
        self.assertEqual(original, pointer.read_bytes())
        unknown = self.base/'unknown-cache/elm-workspace-index'
        unknown.mkdir(parents=True)
        sentinel = unknown/'sentinel.txt'
        sentinel.write_text('unrelated', encoding='utf-8')
        with self.assertRaises(module.IndexError) as caught:
            module.WorkspaceIndex(self.home, unknown.parent).build('workspace:a', records, force=True)
        self.assertEqual('unowned_cache', caught.exception.code)
        self.assertEqual(['sentinel.txt'], [p.name for p in unknown.iterdir()])
        self.assertEqual('unrelated', sentinel.read_text(encoding='utf-8'))

    def test_ranking_matches_positive_engine_scores_before_global_limit(self):
        records = [record('rec_strong', text='amber rollback '*30),
                   record('rec_weak_work', text='amber '+'unrelated '*100),
                   record('rec_weak_reference', domain='reference', text='amber '+'unrelated '*100),
                   record('rec_unmatched', text='sapphire only')]
        receipt = self.index.build('workspace:a', records)
        folder = self.index.root/receipt['generation']
        manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        hits = []
        for lane in ('work', 'reference'):
            raw = run_engine(self.home, folder/'root', 'search', '--project', module.PROJECT,
                             '--memory-lane', lane, '--memory-purpose', 'review',
                             '--path-prefix', module.PREFIX, '--limit', '4', '--no-sync', '--broad',
                             task='amber rollback')
            hits.extend(raw['results'])
        self.assertTrue(hits)
        self.assertTrue(all(h['score'] > 0 for h in hits))
        ranked = sorted(hits, key=lambda h: (-h['score'], h['section_key']))
        expected = [manifest['sections'][h['section_key']]['record_id'] for h in ranked]
        self.assertEqual('rec_strong', expected[0])
        self.assertGreater(ranked[0]['score'], ranked[-1]['score'])
        self.assertNotIn('rec_unmatched', expected)
        print(json.dumps({'real_positive_scores': hits, 'expected_records': expected}))
        actual = self.index.query('workspace:a', records, 'amber rollback', limit=4)
        self.assertEqual(expected, [h['record_id'] for h in actual['results']])
        limited = self.index.query('workspace:a', records, 'amber rollback', limit=1)
        self.assertEqual(expected[:1], [h['record_id'] for h in limited['results']])
        self.assertEqual([], self.index.query('workspace:a', records, 'absent_token_zzzz')['results'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
