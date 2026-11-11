"""Atomic trusted-human bulk-create contracts; synthetic, offline, owned roots."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
import unittest

from elm_plugin.workspace_records import RecordStore, RecordError


def fields(**changes):
    value = dict(title='Fictional amber lane', text='Amber source\r\n  exact text Ω\n',
                 domain='reference', kind='reference', basis='source_document',
                 sources=[dict(ref='fictional:one', quote='amber', sha256='a'*64, revision=1)],
                 state='approved')
    value.update(changes)
    return value


class BatchRecordContracts(unittest.TestCase):
    def setUp(self):
        # The prescribed runner supplies this fresh, credential-free scratch home.
        self.base = Path(os.environ['HERMES_HOME']) / 'batch-record-tests'
        self.base.mkdir(exist_ok=True)
        (self.base/'OWNER.json').write_text('{"owner":"bulk-record-tests","synthetic":true}\n', encoding='utf-8')
        self.temp = tempfile.TemporaryDirectory(prefix='bulk-', dir=self.base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'records'
        self.store = RecordStore(self.root)
        self.store.initialize()
        self.store.put_scope('chat:one', 'chat', 'Fictional private chat')
        self.store.put_scope('chat:other', 'chat', 'Other private chat')

    def refusal(self, code, operation, *args, **kwargs):
        with self.assertRaises(RecordError) as caught:
            operation(*args, **kwargs)
        self.assertEqual(code, caught.exception.code)

    def test_growing_manifest_import_has_one_authoritative_bulk_commit(self):
        # Reproduce cause on six synthetic turns, not the expensive old corpus.
        observed = []
        real_save = self.store._save
        def observe(data):
            real_save(data)
            observed.append((self.root/'manifest.json').stat().st_size)
        with patch.object(self.store, '_save', side_effect=observe):
            for n in range(6):
                self.store.put_record('chat:one', **fields(text='synthetic '+str(n)+' x'*200))
        self.assertEqual(len(observed), 6)
        self.assertGreater(sum(observed), observed[-1]*2)
        self.assertEqual(observed, sorted(observed))
        self.assertTrue(callable(getattr(self.store, 'create_many', None)),
                        'RecordStore.create_many absent: no authoritative one-commit bulk operation')
        before = self.store.status()['revision']
        payloads = [fields(text='batch '+str(n)+' y'*200) for n in range(6)]
        with patch.object(self.store, '_save', wraps=self.store._save) as commits:
            result = self.store.create_many('chat:one', payloads)
        self.assertEqual(commits.call_count, 1, 'a loop over put_record still rewrites the growing manifest')
        self.assertEqual(self.store.status()['revision'], before+1)
        self.assertEqual(len(result), len(payloads))
        self.assertEqual(len({r['id'] for r in result}), len(payloads))
        reopened = RecordStore(self.root)
        for record, payload in zip(result, payloads):
            self.assertEqual(record['revision'], 1)
            self.assertEqual(record['scope_id'], 'chat:one')
            self.assertEqual(record, reopened.get(record['id']))
            for key, value in payload.items():
                self.assertEqual(json.dumps(record[key], ensure_ascii=False, sort_keys=True),
                                 json.dumps(value, ensure_ascii=False, sort_keys=True))
        self.assertEqual(reopened.visible_records('chat:other'), [])

    def test_mixed_invalid_batch_rolls_back_exact_manifest_and_revision(self):
        cases = [
            ('invalid_value', fields(text='')),
            ('invalid_payload', {**fields(), 'id':'caller-owned'}),
            ('invalid_payload', {'title':'missing fields'}),
            ('invalid_payload', None),
            ('invalid_sources', fields(sources=[])),
            ('invalid_evidence', fields(kind='preference', basis='inference')),
            ('invalid_value', fields(sensitive=0)),
            ('sensitive_inference', fields(domain='user', kind='interpretation', basis='inference', sensitive=True)),
            ('undeclared_dependency', fields(sources=[{'ref':'record:rec_missing'}])),
            ('invalid_dependencies', fields(dependencies=[{'id':'rec_missing','revision':1}])),
        ]
        before = (self.root/'manifest.json').read_bytes()
        for code, bad in cases:
            with self.subTest(code=code, bad=bad):
                with patch.object(self.store, '_save', wraps=self.store._save) as commits:
                    self.refusal(code, self.store.create_many, 'chat:one', [fields(), bad])
                self.assertEqual(commits.call_count, 0)
                self.assertEqual((self.root/'manifest.json').read_bytes(), before)
        for bad in ([], (), None, [fields()]*10001):
            self.refusal('invalid_batch', self.store.create_many, 'chat:one', bad)
        self.refusal('scope_not_found', self.store.create_many, 'chat:absent', [fields()])
        self.assertEqual((self.root/'manifest.json').read_bytes(), before)

    def test_defaults_duplicates_deepcopy_and_approval_are_not_authority_changes(self):
        payload = fields()
        del payload['state']
        original = deepcopy(payload)
        result = self.store.create_many('chat:one', [payload, payload, fields(state='invalidated')])
        self.assertEqual(payload, original)
        self.assertEqual(len({r['id'] for r in result}), 3)
        self.assertEqual([r['state'] for r in result], ['pending','pending','invalidated'])
        self.assertEqual(self.store.visible_records('chat:one'), [])
        result[0]['sources'][0]['quote'] = 'caller mutation'
        self.assertEqual(self.store.get(result[0]['id'])['sources'], original['sources'])
        approved = self.store.approve(result[0]['id'], 1)
        self.assertEqual(approved['revision'], 2)
        self.refusal('revision_conflict', self.store.approve, result[0]['id'], 1)
        self.assertEqual(self.store.visible_records('chat:one'), [approved])

    def test_existing_dependencies_pins_and_correction_invalidate_bulk_children(self):
        source = self.store.put_record('chat:one', **fields())
        dependency = dict(sources=[{'ref':'record:'+source['id'], 'revision':1}],
                          dependencies=[{'id':source['id'], 'revision':1}])
        before = self.store.status()['revision']
        children = self.store.create_many('chat:one', [fields(**dependency), fields(**dependency)])
        self.assertEqual(self.store.status()['revision'], before+1)
        self.assertTrue(all(r['revision']==1 for r in children))
        for broken, code in [
            ({**dependency, 'dependencies':[{'id':source['id'],'revision':2}]}, 'stale_dependency'),
            ({**dependency, 'sources':[{'ref':'record:'+source['id'],'revision':2}]}, 'stale_dependency'),
            ({**dependency, 'dependencies':[{'id':source['id'],'revision':True}]}, 'invalid_dependencies'),
            ({**dependency, 'dependencies':dependency['dependencies']*2}, 'invalid_dependencies'),
        ]:
            snapshot = (self.root/'manifest.json').read_bytes()
            self.refusal(code, self.store.create_many, 'chat:one', [fields(), fields(**broken)])
            self.assertEqual((self.root/'manifest.json').read_bytes(), snapshot)
        self.store.correct(source['id'], 1, {'text':'Corrected synthetic source'})
        for child in children:
            current = self.store.get(child['id'])
            self.assertEqual((current['state'],current['revision']), ('invalidated',2))
        self.refusal('stale_dependency', self.store.create_many, 'chat:one', [fields(**dependency)])

    def test_pending_and_cross_scope_dependencies_do_not_gain_approval_or_visibility(self):
        source = self.store.put_record('chat:one', **fields())
        pending = self.store.put_record('chat:one', **fields(state='pending'))
        for record, target in [(source,'chat:other'), (pending,'chat:one')]:
            before = (self.root/'manifest.json').read_bytes()
            self.refusal('dependency_not_visible', self.store.create_many, target,
                         [fields(), fields(sources=[{'ref':'record:'+record['id']}],
                                           dependencies=[{'id':record['id'],'revision':1}])])
            self.assertEqual((self.root/'manifest.json').read_bytes(), before)
        self.store.put_scope('personal', 'personal', 'Fictional personal')
        shared = self.store.put_record('personal', **fields(domain='user', kind='preference',
                    basis='explicit_statement', topic='communication'))
        self.store.grant('personal','chat:one',[shared['id']])
        child = self.store.create_many('chat:one', [fields(sources=[{'ref':'record:'+shared['id']}],
                                      dependencies=[{'id':shared['id'],'revision':1}])])[0]
        self.store.revoke('personal','chat:one',[shared['id']])
        self.assertEqual(self.store.get(child['id'])['state'], 'invalidated')

    def test_identity_collision_in_batch_existing_or_tombstone_is_atomic(self):
        import types
        source = self.store.put_record('chat:one', **fields())
        for existing in (False, True):
            if existing:
                preview = self.store.delete_preview(source['id'])
                self.store.delete(source['id'], preview['preview_token'])
            before = (self.root/'manifest.json').read_bytes()
            with patch('elm_plugin.workspace_records.uuid.uuid4', return_value=types.SimpleNamespace(hex=source['id'][4:])):
                self.refusal('duplicate_record', self.store.create_many, 'chat:one', [fields()])
            self.assertEqual((self.root/'manifest.json').read_bytes(), before)
        with patch('elm_plugin.workspace_records.uuid.uuid4', return_value=types.SimpleNamespace(hex='b'*32)):
            self.refusal('duplicate_record', self.store.create_many, 'chat:one', [fields(),fields()])
        self.assertEqual((self.root/'manifest.json').read_bytes(), before)

    def test_replace_failure_rolls_back_and_releases_lock_without_retry(self):
        before = (self.root/'manifest.json').read_bytes()
        with patch('elm_plugin.workspace_records.os.replace', side_effect=OSError('synthetic pre-replace failure')) as replace:
            self.refusal('storage_error', self.store.create_many, 'chat:one', [fields(),fields()])
        self.assertEqual(replace.call_count, 1)
        self.assertEqual((self.root/'manifest.json').read_bytes(), before)
        self.assertFalse((self.root/'.manifest.next').exists())
        self.assertEqual(len(self.store.create_many('chat:one', [fields()])), 1)

    def test_real_os_lock_refuses_another_process_without_partial_commit(self):
        import subprocess
        import sys
        code = ('import sys,json;sys.path.insert(0,sys.argv[1]);'
                'from pathlib import Path;from elm_plugin.workspace_records import RecordStore,RecordError;'
                '\ns=RecordStore(Path(sys.argv[2]))\ntry:s.create_many("chat:one",json.loads(sys.argv[3]))'
                '\nexcept RecordError as e:print(e.code)\nelse:raise AssertionError("lock bypass")')
        before = (self.root/'manifest.json').read_bytes()
        with self.store._locked():
            child = subprocess.run([sys.executable,'-I','-S','-B','-c',code,
                        str(Path(__file__).resolve().parents[1]),str(self.root),json.dumps([fields()])],
                        capture_output=True,text=True,encoding='utf-8',timeout=15)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertEqual(child.stdout.strip(), 'store_busy')
        self.assertEqual((self.root/'manifest.json').read_bytes(), before)
        self.assertEqual(len(self.store.create_many('chat:one', [fields()])), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
