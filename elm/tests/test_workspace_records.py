"""Isolated stdlib contracts for durable workspace authored records.

Run with Python -I -S -B; this file inserts only the candidate package.
All fixtures are fictional and all writes stay in the assigned scratch root.
"""
from pathlib import Path
import json
import os
import sys
import tempfile
import subprocess
import time
from unittest.mock import patch
import unittest

CANDIDATE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CANDIDATE))
SCRATCH = Path(os.environ.get('ELM_TEST_SCRATCH_ROOT', tempfile.gettempdir())) / 'elm-record-tests'
SCRATCH.mkdir(parents=True, exist_ok=True)
for key in ('TMP', 'TEMP', 'TMPDIR', 'SQLITE_TMPDIR'):
    os.environ[key] = str(SCRATCH)
sys.dont_write_bytecode = True

try:
    from elm_plugin.workspace_records import RecordStore, RecordError
except ModuleNotFoundError as exc:
    if exc.name != 'elm_plugin.workspace_records':
        raise
    RecordStore = None
    RecordError = None


class RecordContracts(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(RecordStore, 'RecordStore contract is not implemented')
        self.temp = tempfile.TemporaryDirectory(prefix='fictional-', dir=SCRATCH)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'records'
        self.store = RecordStore(self.root)

    def refusal(self, code, operation, *args, **kwargs):
        with self.assertRaises(RecordError) as caught:
            operation(*args, **kwargs)
        self.assertEqual(code, caught.exception.code)

    def setup_scopes(self):
        self.store.initialize()
        for scope, kind in [('personal:fictional', 'personal'), ('workspace:alpha', 'workspace'),
                            ('workspace:beta', 'workspace'), ('chat:one', 'chat'), ('chat:two', 'chat')]:
            self.store.put_scope(scope, kind, scope)

    def record(self, scope='workspace:alpha', **changes):
        fields = dict(title='Fictional deployment fact', text='Use the amber staging lane.', domain='work',
                      kind='explicit_fact', basis='explicit_statement', sources=[{'ref': 'fictional:message:1', 'quote': 'amber',
                      'sha256': 'a' * 64, 'revision': 1}])
        fields.update(changes)
        return self.store.put_record(scope, **fields)

    def test_explicit_initialization_persistence_pending_and_scope_separation(self):
        self.assertEqual({'schema': 1, 'revision': 0, 'initialized': False}, self.store.status())
        self.assertFalse(self.root.exists(), 'status must not silently initialize')
        self.refusal('not_initialized', self.store.list_scopes)
        self.setup_scopes()
        self.assertTrue(all(s['private'] is True for s in self.store.list_scopes()))
        record = self.record()
        self.assertEqual('pending', record['state'])
        self.assertEqual([], self.store.visible_records('workspace:alpha'))
        self.assertEqual([], self.store.list_records('workspace:beta'))
        self.assertEqual([], self.store.visible_records('chat:one'))
        self.assertEqual(record, self.store.get(record['id']))
        self.assertEqual([record], self.store.list_records('workspace:alpha'))
        reopened = RecordStore(self.root)
        self.assertEqual(record, reopened.get(record['id']))
        self.assertEqual({'revision': self.store.status()['revision'], 'records': []}, reopened.snapshot('workspace:alpha'))
        self.refusal('scope_not_found', reopened.visible_records, 'workspace:unknown')
        self.refusal('invalid_id', self.store.put_scope, '../escape', 'workspace', 'bad')
        self.assertEqual(record['sources'], reopened.get(record['id'])['sources'])
        self.refusal('already_initialized', reopened.initialize)
        unrelated = self.base / 'unrelated'
        unrelated.mkdir()
        (unrelated / 'KEEP.txt').write_text('do not adopt', encoding='utf-8')
        self.refusal('unowned_root', RecordStore(unrelated).initialize)
        self.assertEqual('do not adopt', (unrelated / 'KEEP.txt').read_text(encoding='utf-8'))
        # Inspectable source JSON, not a private retrieval database.
        raw = json.loads((self.root / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(record, raw['records'][record['id']])

    def test_approval_optimistic_correction_and_transitive_invalidation(self):
        self.setup_scopes()
        source = self.record()
        self.assertTrue(callable(getattr(self.store, 'approve', None)), 'approval API is missing')
        source = self.store.approve(source['id'], source['revision'])
        self.assertEqual('approved', source['state'])
        self.assertGreater(source['revision'], 1)
        self.assertEqual([source], self.store.visible_records(source['scope_id']))
        self.refusal('revision_conflict', self.store.correct, source['id'], 1, {'text': 'lost update'})
        derived = self.record(kind='summary', basis='inference', sources=[{'ref': 'record:' + source['id'], 'revision': source['revision']}],
                              dependencies=[{'id': source['id'], 'revision': source['revision']}])
        derived = self.store.approve(derived['id'], derived['revision'])
        child = self.record(kind='interpretation', basis='inference', sources=[{'ref': 'record:' + derived['id']}],
                            dependencies=[{'id': derived['id'], 'revision': derived['revision']}])
        child = self.store.approve(child['id'], child['revision'])
        corrected = self.store.correct(source['id'], source['revision'], {'text': 'Use the violet staging lane.'})
        self.assertEqual('approved', corrected['state'])
        self.assertEqual('Use the violet staging lane.', RecordStore(self.root).get(source['id'])['text'])
        self.assertEqual('invalidated', self.store.get(derived['id'])['state'])
        self.assertEqual('invalidated', self.store.get(child['id'])['state'])
        self.assertEqual([corrected], self.store.visible_records(source['scope_id']))
        self.refusal('stale_dependency', self.store.approve, derived['id'], self.store.get(derived['id'])['revision'])
        self.refusal('invalid_changes', self.store.correct, source['id'], corrected['revision'], {'scope_id': 'workspace:beta'})
        self.refusal('revision_conflict', self.store.approve, source['id'], True)
        self.assertEqual([], self.store.visible_records('workspace:beta'))

    def test_dependency_sources_cannot_bypass_scope_revision_or_declared_provenance(self):
        self.setup_scopes()
        source = self.record(state='approved')
        args = dict(kind='summary', basis='inference', sources=[{'ref': 'record:' + source['id']}],
                    dependencies=[{'id': source['id'], 'revision': source['revision']}])
        self.refusal('dependency_not_visible', self.record, 'workspace:beta', **args)
        self.refusal('undeclared_dependency', self.record, sources=args['sources'])
        self.refusal('stale_dependency', self.record, **{**args, 'dependencies': [{'id': source['id'], 'revision': 88}]})
        self.refusal('invalid_dependencies', self.record, **{**args, 'sources': [{'ref': 'fictional:unrelated'}]})
        self.refusal('invalid_dependencies', self.record, **{**args, 'dependencies': [{'id': 'rec_absent', 'revision': 1}]})
        self.refusal('invalid_sources', self.record, sources=[])
        pending = self.record()
        self.refusal('dependency_not_visible', self.record, kind='summary', basis='inference',
                     sources=[{'ref': 'record:' + pending['id']}], dependencies=[{'id': pending['id'], 'revision': 1}])

    def test_labels_sensitive_metadata_and_procedures_are_never_executable(self):
        self.setup_scopes()
        for fields in [dict(kind='preference', basis='inference'), dict(kind='observation', basis='explicit_statement'),
                       dict(kind='interpretation', basis='direct_observation')]:
            self.refusal('invalid_evidence', self.record, **fields)
        self.refusal('sensitive_inference', self.record, domain='user', kind='interpretation', basis='inference', sensitive=True)
        # Deliberately contains a diagnosis word: refusal is metadata-only, not text guessing.
        explicit = self.record(domain='user', text='Fictional self-report: diagnosis mentioned by the user.', sensitive=True)
        self.assertTrue(explicit['sensitive'])
        self.assertEqual('explicit_statement', explicit['basis'])
        draft = self.record(kind='procedure', basis='source_document')
        self.assertTrue(callable(getattr(self.store, 'approve', None)), 'approval API is missing')
        approved = self.store.approve(draft['id'], draft['revision'])
        self.assertEqual('procedure', approved['kind'])
        self.assertFalse(approved.get('executable', False))
        self.refusal('invalid_changes', self.store.correct, approved['id'], approved['revision'], {'executable': True})
        self.assertEqual(explicit['sources'], self.store.get(explicit['id'])['sources'])

    def test_explicit_approved_communication_card_grants_revoke_and_wrong_scope(self):
        self.setup_scopes()
        card = self.record('personal:fictional', domain='user', kind='preference', topic='communication', text='Fictional preference: concise replies.')
        self.assertTrue(callable(getattr(self.store, 'grant', None)), 'record-level grant API is missing')
        self.refusal('sharing_denied', self.store.grant, card['scope_id'], 'chat:one', [card['id']])
        card = self.store.approve(card['id'], card['revision'])
        receipt = self.store.grant(card['scope_id'], 'chat:one', [card['id']])
        self.assertEqual([card['id']], receipt['record_ids'])
        self.assertEqual([card], RecordStore(self.root).visible_records('chat:one'))
        self.assertEqual([], self.store.visible_records('chat:two'))
        self.assertEqual([], self.store.visible_records('workspace:alpha'))
        self.refusal('sharing_denied', self.store.grant, 'workspace:alpha', 'chat:two', [card['id']])
        self.refusal('invalid_grant', self.store.grant, card['scope_id'], 'chat:one', ['*'])
        self.refusal('invalid_grant', self.store.grant, card['scope_id'], 'chat:one', [])
        # A granted pointer can be used only with a declared current dependency.
        derived = self.record('chat:one', kind='summary', basis='inference', state='approved',
                              sources=[{'ref': 'record:' + card['id']}], dependencies=[{'id': card['id'], 'revision': card['revision']}])
        self.store.revoke(card['scope_id'], 'chat:one', [card['id']])
        self.assertEqual([], self.store.visible_records('chat:one'))
        self.assertEqual('invalidated', self.store.get(derived['id'])['state'])
        self.refusal('dependency_not_visible', self.record, 'chat:two', kind='summary', basis='inference',
                     sources=[{'ref': 'record:' + card['id']}], dependencies=[{'id': card['id'], 'revision': card['revision']}])

    def test_private_sources_sensitive_cards_and_atomic_grant_batches_are_refused(self):
        self.setup_scopes()
        self.assertTrue(callable(getattr(self.store, 'grant', None)), 'record-level grant API is missing')
        for source_scope in ('workspace:alpha', 'chat:one'):
            record = self.record(source_scope, domain='user', kind='preference', topic='communication', state='approved')
            self.refusal('sharing_denied', self.store.grant, source_scope, 'chat:two', [record['id']])
        own_alpha = self.store.visible_records('workspace:alpha')
        safe = self.record('personal:fictional', domain='user', kind='preference', topic='communication', state='approved')
        for fields in [dict(sensitive=True), dict(topic='health'), dict(kind='explicit_fact'), dict(state='pending')]:
            card_fields = dict(domain='user', kind='preference', topic='communication', state='approved')
            card_fields.update(fields)
            unsafe = self.record('personal:fictional', **card_fields)
            self.refusal('sharing_denied', self.store.grant, safe['scope_id'], 'workspace:alpha', [safe['id'], unsafe['id']])
            self.assertEqual(own_alpha, self.store.visible_records('workspace:alpha'))
        self.store.put_scope('workspace:alpha', 'workspace', 'Fictional public boundary', private=False)
        work = self.record(state='approved')
        self.refusal('sharing_denied', self.store.grant, 'workspace:alpha', 'chat:two', [work['id']])
        self.store.put_scope('workspace:beta', 'workspace', 'Fictional public target', private=False)
        self.store.grant('workspace:alpha', 'workspace:beta', [work['id']])
        self.assertEqual([work], self.store.visible_records('workspace:beta'))
        self.store.put_scope('workspace:alpha', 'workspace', 'Private again', private=True)
        self.assertEqual([], self.store.visible_records('workspace:beta'))
        chat_record = self.record('chat:one')
        self.refusal('privacy_broadening_denied', self.store.put_scope, 'chat:one', 'chat', 'No widening', private=False)
        self.assertEqual('pending', chat_record['state'])

    def test_correction_does_not_silently_extend_a_previously_granted_body(self):
        self.setup_scopes()
        self.assertTrue(callable(getattr(self.store, 'grant', None)), 'record-level grant API is missing')
        card = self.record('personal:fictional', domain='user', kind='preference', topic='communication', state='approved')
        self.store.grant(card['scope_id'], 'chat:one', [card['id']])
        corrected = self.store.correct(card['id'], card['revision'], {'text': 'Fictional corrected preference.'})
        self.assertEqual('approved', corrected['state'])
        self.assertEqual([], self.store.visible_records('chat:one'))
        self.store.grant(card['scope_id'], 'chat:one', [card['id']])
        self.assertEqual([corrected], self.store.visible_records('chat:one'))

    def test_exact_delete_preview_cascades_purges_content_and_retains_only_tombstones(self):
        self.setup_scopes()
        source = self.record(state='approved', title='ERASE_SOURCE_TITLE', text='ERASE_SOURCE_BODY',
                             sources=[{'ref': 'fictional:erase-source', 'quote': 'ERASE_SOURCE_QUOTE'}])
        derived = self.record(kind='summary', basis='inference', state='approved', text='ERASE_DERIVED_BODY',
                              sources=[{'ref': 'record:' + source['id'], 'quote': 'ERASE_SOURCE_BODY'}],
                              dependencies=[{'id': source['id'], 'revision': source['revision']}])
        child = self.record(kind='procedure', basis='inference', text='ERASE_CHILD_BODY',
                            sources=[{'ref': 'record:' + derived['id']}], dependencies=[{'id': derived['id'], 'revision': derived['revision']}])
        keep = self.record(text='KEEP_UNRELATED_CONTENT')
        self.assertTrue(callable(getattr(self.store, 'delete_preview', None)), 'exact deletion preview API is missing')
        before = self.store.status()['revision']
        preview = self.store.delete_preview(source['id'])
        self.assertEqual(before, preview['revision'])
        self.assertEqual(source['id'], preview['record_id'])
        self.assertEqual(sorted([derived['id'], child['id']]), preview['dependent_ids'])
        self.assertEqual(before, self.store.status()['revision'], 'preview must be read-only')
        self.refusal('stale_preview', self.store.delete, keep['id'], preview['preview_token'])
        receipt = RecordStore(self.root).delete(source['id'], preview['preview_token'])
        self.assertEqual(sorted([source['id'], derived['id'], child['id']]), receipt['deleted_ids'])
        for record_id in receipt['deleted_ids']:
            self.refusal('record_not_found', self.store.get, record_id)
        self.assertEqual(keep, self.store.get(keep['id']))
        raw = json.loads((self.root / 'manifest.json').read_text(encoding='utf-8'))
        for record_id in receipt['deleted_ids']:
            self.assertEqual({'id', 'scope_id', 'revision', 'deleted_at'}, set(raw['tombstones'][record_id]))
        for path in self.root.iterdir():
            if path.is_file():
                self.assertNotIn(b'ERASE_', path.read_bytes())
        limits = receipt['outside_operation']
        for outside in ('host transcripts', 'unknown exports', 'backups'):
            self.assertIn(outside, limits)
        self.refusal('record_not_found', self.store.delete, source['id'], preview['preview_token'])

    def test_delete_preview_is_bound_to_current_manifest_and_store_without_retries(self):
        self.setup_scopes()
        record = self.record(state='approved')
        self.assertTrue(callable(getattr(self.store, 'delete_preview', None)), 'exact deletion preview API is missing')
        preview = self.store.delete_preview(record['id'])
        self.record('workspace:beta')
        self.refusal('stale_preview', self.store.delete, record['id'], preview['preview_token'])
        self.assertEqual(record, self.store.get(record['id']))
        preview = self.store.delete_preview(record['id'])
        self.refusal('stale_preview', self.store.delete, record['id'], 'not-a-preview')
        self.store.correct(record['id'], record['revision'], {'text': 'Changed after preview.'})
        self.refusal('stale_preview', self.store.delete, record['id'], preview['preview_token'])
        preview = self.store.delete_preview(record['id'])
        receipt = self.store.delete(record['id'], preview['preview_token'])
        self.assertEqual(preview['revision'] + 1, receipt['revision'])

    def child(self, action, *args):
        command = [sys.executable, '-I', '-S', '-B', str(Path(__file__).resolve()), '--worker',
                   action, str(self.root), *map(str, args)]
        child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                 env={k: v for k, v in os.environ.items()
                                      if not any(x in k.upper() for x in ('TOKEN', 'SECRET', 'PASSWORD', 'API_KEY', 'CREDENTIAL'))})
        def cleanup():
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=15)
        self.addCleanup(cleanup)
        return child

    def test_concurrent_process_mutation_has_no_lost_updates(self):
        self.setup_scopes()
        before = self.store.status()['revision']
        children = [self.child('append', i, 10) for i in range(4)]
        for child in children:
            stdout, stderr = child.communicate(timeout=45)
            self.assertEqual(0, child.returncode, stdout + stderr)
            self.assertEqual(10, json.loads(stdout)['created'])
        records = RecordStore(self.root).list_records('workspace:alpha')
        self.assertEqual(40, len(records))
        self.assertEqual(40, len({r['id'] for r in records}))
        self.assertEqual({f'worker-{w}-{i}' for w in range(4) for i in range(10)}, {r['title'] for r in records})
        self.assertEqual(before + 40, self.store.status()['revision'])

    def test_os_lock_is_released_when_owner_process_is_killed(self):
        self.setup_scopes()
        ready = self.base / 'holder-ready'
        child = self.child('hold', ready)
        deadline = time.monotonic() + 15
        while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(ready.exists(), 'lock holder never acquired lock')
        self.refusal('store_busy', self.record)
        child.kill()
        child.communicate(timeout=15)
        record = self.record(text='Fictional write after process exit.')
        self.assertEqual(record, RecordStore(self.root).get(record['id']))

    def test_failed_atomic_replace_preserves_previous_revision_and_releases_lock(self):
        self.setup_scopes()
        record = self.record()
        before = (self.root / 'manifest.json').read_bytes()
        with patch('elm_plugin.workspace_records.os.replace', side_effect=OSError('fictional storage failure')):
            self.refusal('storage_error', self.store.correct, record['id'], record['revision'], {'text': 'Never published.'})
        self.assertEqual(before, (self.root / 'manifest.json').read_bytes())
        self.assertFalse((self.root / '.manifest.next').exists())
        corrected = self.store.correct(record['id'], record['revision'], {'text': 'Actually published.'})
        self.assertEqual(corrected, RecordStore(self.root).get(record['id']))

    def test_process_exit_mid_commit_keeps_prior_manifest_and_next_delete_purges_stage(self):
        self.setup_scopes()
        record = self.record(text='CRASH_OLD_CONTENT')
        before = (self.root / 'manifest.json').read_bytes()
        child = self.child('crash_replace', record['id'], record['revision'])
        stdout, stderr = child.communicate(timeout=15)
        self.assertEqual(37, child.returncode, stdout + stderr)
        self.assertEqual(before, (self.root / 'manifest.json').read_bytes())
        self.assertTrue((self.root / '.manifest.next').exists())
        reopened = RecordStore(self.root)
        self.assertEqual(record, reopened.get(record['id']))
        preview = reopened.delete_preview(record['id'])
        reopened.delete(record['id'], preview['preview_token'])
        self.assertFalse((self.root / '.manifest.next').exists())
        self.assertNotIn(b'CRASH_', (self.root / 'manifest.json').read_bytes())

    def test_corrupt_manifest_is_a_declared_fail_closed_refusal(self):
        self.setup_scopes()
        record = self.record(state='approved')
        path = self.root / 'manifest.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        data['records'][record['id']]['state'] = 'undeclared-state'
        path.write_text(json.dumps(data), encoding='utf-8')
        self.refusal('corrupt_store', self.store.snapshot, 'workspace:alpha')
        self.refusal('corrupt_store', self.record)
        self.assertEqual('undeclared-state', json.loads(path.read_text(encoding='utf-8'))['records'][record['id']]['state'])

    def test_previously_populated_private_chat_cannot_be_reused_as_broader_scope(self):
        self.setup_scopes()
        record = self.record('chat:one')
        preview = self.store.delete_preview(record['id'])
        self.store.delete(record['id'], preview['preview_token'])
        self.refusal('privacy_broadening_denied', self.store.put_scope, 'chat:one', 'chat', 'Not a fresh chat', private=False)

    def test_malformed_json_values_are_declared_refusals_without_partial_writes(self):
        self.setup_scopes()
        before = (self.root / 'manifest.json').read_bytes()
        for fields in [dict(kind=[]), dict(kind={}), dict(domain=[]), dict(basis=[]),
                       dict(sensitive=1), dict(text=''), dict(title='x' * 513),
                       dict(text='unpaired-surrogate-\ud800'), dict(sources=[{'ref': 'fictional:x', 'revision': True}]),
                       dict(sources=[{'ref': 'fictional:x', 'sha256': 'not-a-hash'}]),
                       dict(dependencies=[{'id': 'rec_missing', 'revision': True}])]:
            with self.subTest(fields=repr(fields)):
                with self.assertRaises(RecordError):
                    self.record(**fields)
                self.assertEqual(before, (self.root / 'manifest.json').read_bytes())
        record = self.record()
        record['sources'][0]['quote'] = 'tampered returned copy'
        self.assertEqual('amber', self.store.get(record['id'])['sources'][0]['quote'])

    def test_unowned_manifest_cannot_create_a_lock_or_adopt_existing_content(self):
        self.root.mkdir()
        (self.root / 'manifest.json').write_text('{"owner":"some-other-application"}', encoding='utf-8')
        with self.assertRaises(RecordError):
            self.store.status()
        self.assertFalse((self.root / '.records.lock').exists(), 'reads must not write to an unowned store')

    def test_dependency_cycles_and_foreign_preview_tokens_are_refused(self):
        self.setup_scopes()
        source = self.record(state='approved')
        derived = self.record(kind='summary', basis='inference', state='approved',
                              sources=[{'ref': 'record:' + source['id']}], dependencies=[{'id': source['id'], 'revision': source['revision']}])
        self.refusal('dependency_cycle', self.store.correct, source['id'], source['revision'],
                     {'sources': [{'ref': 'record:' + derived['id']}],
                      'dependencies': [{'id': derived['id'], 'revision': derived['revision']}]})
        preview = self.store.delete_preview(source['id'])
        other = RecordStore(self.base / 'other-owned-store')
        other.initialize()
        for scope in self.store.list_scopes():
            other.put_scope(scope['id'], scope['kind'], scope['label'], scope['private'])
        own = other.put_record('workspace:alpha', title='Other fictional fact', text='Other body', domain='work',
                               kind='explicit_fact', basis='explicit_statement', sources=[{'ref': 'fictional:other'}])
        self.refusal('stale_preview', other.delete, own['id'], preview['preview_token'])
        self.assertEqual(own, other.get(own['id']))

    def test_deep_valid_dependency_history_reopens_without_recursive_failure(self):
        self.setup_scopes()
        template = self.record(kind='summary', basis='inference', state='approved')
        path = self.root / 'manifest.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        data['records'] = {}
        # Hand-built fictional persisted graph using the public record shape.
        # It avoids quadratic fsync fixture setup, not repository validation.
        for i in range(1050):
            record_id = f'rec_chain_{i}'
            previous = f'rec_chain_{i - 1}'
            data['records'][record_id] = {**template, 'id': record_id,
                'sources': [{'ref': 'record:' + previous}] if i else [{'ref': 'fictional:chain-origin'}],
                'dependencies': [{'id': previous, 'revision': 1}] if i else []}
        path.write_text(json.dumps(data), encoding='utf-8')
        snapshot = RecordStore(self.root).snapshot('workspace:alpha')
        self.assertEqual(1050, len(snapshot['records']))
        self.assertEqual('rec_chain_1049', snapshot['records'][-1]['id'])


def run_worker():
    action, root, *args = sys.argv[2:]
    store = RecordStore(Path(root))
    if action == 'hold':
        with store._locked():
            Path(args[0]).write_text('ready', encoding='utf-8')
            time.sleep(60)
    elif action == 'append':
        worker_id, count = args
        busy = 0
        for i in range(int(count)):
            deadline = time.monotonic() + 30
            while True:
                try:
                    store.put_record('workspace:alpha', title=f'worker-{worker_id}-{i}', text='Fictional concurrent fact.',
                                     domain='work', kind='explicit_fact', basis='explicit_statement', sources=[{'ref': 'fictional:worker'}])
                    break
                except RecordError as exc:
                    if exc.code != 'store_busy' or time.monotonic() >= deadline:
                        raise
                    busy += 1
                    time.sleep(0.005)
        print(json.dumps({'created': int(count), 'explicit_caller_busy_retries': busy}))
    elif action == 'crash_replace':
        def crash(*unused):
            os._exit(37)
        with patch('elm_plugin.workspace_records.os.replace', side_effect=crash):
            store.correct(args[0], int(args[1]), {'text': 'CRASH_UNPUBLISHED_CONTENT'})
    else:
        raise AssertionError('unknown worker action')


if __name__ == '__main__':
    if sys.argv[1:2] == ['--worker']:
        run_worker()
    else:
        unittest.main(verbosity=2)
