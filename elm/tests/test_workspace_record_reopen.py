"""Persisted local-source revision contracts; fictional runner-owned stores only."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest

from elm_plugin.workspace_records import RecordError, RecordStore


class RecordReopenContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='records-reopen-', dir=os.environ['TMPDIR'])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'records'
        self.store = RecordStore(self.root)
        self.store.initialize()
        for scope in ('workspace:a', 'workspace:b'):
            self.store.put_scope(scope, 'workspace', scope)
        self.source = self.put(self.store)
        self.summary = self.put(self.store, kind='summary', basis='inference',
            sources=[{'ref': 'record:' + self.source['id'], 'revision': self.source['revision']}],
            dependencies=[{'id': self.source['id'], 'revision': self.source['revision']}])
        self.path = self.root / 'manifest.json'
        self.valid_bytes = self.path.read_bytes()

    def put(self, store, scope='workspace:a', **overrides):
        fields = dict(title='Fictional release', text='Use the amber lane.', domain='work',
                      kind='explicit_fact', basis='explicit_statement', state='approved',
                      sources=[{'ref': 'fictional:message', 'revision': 17}])
        fields.update(overrides)
        return store.put_record(scope, **fields)

    def refuse(self, code, operation, *args, **kwargs):
        with self.assertRaises(RecordError) as caught:
            operation(*args, **kwargs)
        self.assertEqual(code, caught.exception.code)

    def corrupt(self, revision, *, state='approved', duplicate=False):
        data = json.loads(self.valid_bytes)
        summary = data['records'][self.summary['id']]
        summary['state'] = state
        if duplicate:
            summary['sources'].append(deepcopy(summary['sources'][0]))
        summary['sources'][-1]['revision'] = revision
        self.path.write_text(json.dumps(data), encoding='utf-8')
        return self.path.read_bytes()

    def test_reopened_reads_refuse_mismatched_local_source_revision(self):
        for state in ('approved', 'pending', 'invalidated'):
            with self.subTest(state=state):
                before = self.corrupt(1000, state=state)
                reopened = RecordStore(self.root)
                for read, args in ((reopened.snapshot, ('workspace:a',)),
                                   (reopened.get, (self.summary['id'],)),
                                   (reopened.status, ())):
                    with self.subTest(read=read.__name__):
                        self.refuse('corrupt_store', read, *args)
                        self.assertEqual(before, self.path.read_bytes())

    def test_unrelated_writes_refuse_mismatch_without_repair_or_commit(self):
        before = self.corrupt(1000)
        # Both an already-open handle and a new handle must validate disk state.
        for store in (self.store, RecordStore(self.root)):
            with self.subTest(reopened=store is not self.store):
                self.refuse('corrupt_store', self.put, store, 'workspace:b')
                self.assertEqual(before, self.path.read_bytes())
                self.assertFalse((self.root / '.manifest.next').exists())

    def test_every_duplicate_local_pointer_revision_is_validated(self):
        before = self.corrupt(1000, duplicate=True)
        self.refuse('corrupt_store', RecordStore(self.root).snapshot, 'workspace:a')
        self.assertEqual(before, self.path.read_bytes())

    def test_malformed_explicit_revisions_refuse_read_and_write(self):
        for revision in (True, False, 0, -1, '1', 1.0, None, [], {}):
            with self.subTest(revision=repr(revision)):
                before = self.corrupt(revision)
                reopened = RecordStore(self.root)
                self.refuse('corrupt_store', reopened.snapshot, 'workspace:a')
                self.refuse('corrupt_store', self.put, reopened, 'workspace:b')
                self.assertEqual(before, self.path.read_bytes())

    def test_public_authoring_already_refuses_mismatch_atomically(self):
        self.refuse('stale_dependency', self.put, self.store, kind='summary', basis='inference',
            sources=[{'ref': 'record:' + self.source['id'], 'revision': 1000}],
            dependencies=self.summary['dependencies'])
        self.assertEqual(self.valid_bytes, self.path.read_bytes())

    def test_valid_corrected_and_invalidated_history_survives_reopen_and_write(self):
        # Missing optional local revision and opaque external revisions remain legal.
        unpinned = self.put(self.store, kind='summary', basis='inference',
            sources=[{'ref': 'record:' + self.source['id']}],
            dependencies=self.summary['dependencies'])
        child = self.put(self.store, kind='summary', basis='inference',
            sources=[{'ref': 'record:' + self.summary['id'], 'revision': self.summary['revision']}],
            dependencies=[{'id': self.summary['id'], 'revision': self.summary['revision']}])
        self.assertEqual(4, len(RecordStore(self.root).snapshot('workspace:a')['records']))
        corrected = self.store.correct(self.source['id'], self.source['revision'],
                                       {'text': 'Use the violet lane.'})
        reopened = RecordStore(self.root)
        self.assertEqual([corrected], reopened.snapshot('workspace:a')['records'])
        histories = {}
        for original in (self.summary, unpinned, child):
            actual = reopened.get(original['id'])
            self.assertEqual('invalidated', actual['state'])
            self.assertEqual(original['dependencies'], actual['dependencies'])
            self.assertEqual(original['sources'], actual['sources'])
            histories[actual['id']] = actual
        self.assertNotEqual(corrected['revision'], self.summary['dependencies'][0]['revision'])
        unrelated = self.put(reopened, 'workspace:b')
        final = RecordStore(self.root)
        self.assertEqual([unrelated], final.snapshot('workspace:b')['records'])
        self.assertEqual([corrected], final.snapshot('workspace:a')['records'])
        for record_id, history in histories.items():
            self.assertEqual(history, final.get(record_id))


if __name__ == '__main__':
    unittest.main(verbosity=2)
