"""Bounded repair regressions: real service/store/serializer, fake facade only."""
import json
import tempfile
import unittest
from pathlib import Path

from agent.plugin_llm import PluginLlmCompleteResult, PluginLlmUsage
from elm_plugin.workspace_learning import WorkspaceLearning
from elm_plugin.workspace_records import RecordError
from elm_plugin.workspace_service import WorkspaceService


class Facade:
    def __init__(self, *, provider='offline-repair-facade', model='fictional-repair-model', callback=None):
        self.provider = provider
        self.model = model
        self.callback = callback
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        if self.callback:
            self.callback()
        return PluginLlmCompleteResult(
            text=json.dumps({'title': 'Fictional draft', 'text': 'Use fictional indigo banners.'}),
            provider=self.provider, model=self.model, agent_id='default',
            usage=PluginLlmUsage(input_tokens=1, output_tokens=1, total_tokens=2))


class WorkspaceLearningRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='learning-repairs-case-')
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.service = WorkspaceService(self.home)
        self.service.setup(confirm=True)
        self.scope = 'workspace:fictional-repairs'
        self.service.store.put_scope(self.scope, 'workspace', 'Fictional repairs', private=True)
        self.source = self.create()
        self.service.set_learning(True)

    def create(self, **changes):
        fields = dict(scope_id=self.scope, title='Fictional source', text='Use fictional indigo banners.',
                      domain='work', kind='explicit_fact', basis='explicit_statement',
                      sources=[{'ref': 'fictional:repair-source'}], state='approved')
        fields.update(changes)
        return self.service.create_record(fields)

    def draft(self, facade, source=None, kind='summary'):
        return WorkspaceLearning(self.service, facade).draft(self.scope, [(source or self.source)['id']], kind)

    def assert_committed(self, result, facade):
        reopened = WorkspaceService(self.home)
        saved = reopened.store.get(result['id'])
        for key, value in saved.items():
            self.assertEqual(result[key], value)
        self.assertEqual(saved['state'], 'pending')
        self.assertEqual(saved['basis'], 'inference')
        self.assertEqual(result['generation_receipt']['record_id'], saved['id'])
        self.assertEqual(result['generation_receipt']['record_revision'], saved['revision'])
        self.assertEqual(len(facade.calls), 1)
        self.assertEqual(len(reopened.store.list_records(self.scope)), 2)
        return saved

    def test_surrogate_attribution_is_absent_before_receipt_persistence(self):
        for field, malformed in (('provider', 'fictional-\ud800-provider'), ('model', 'fictional-\udfff-model')):
            with self.subTest(field=field):
                facade = Facade(**{field: malformed})
                result = self.draft(facade)
                saved = self.assert_committed(result, facade)
                self.assertTrue(result['receipt_persisted'])
                receipt = result['generation_receipt']
                self.assertIsNone(receipt[field], 'Malformed attribution is absent, never invented or repaired')
                other = 'model' if field == 'provider' else 'provider'
                self.assertEqual(receipt[other], getattr(facade, other))
                path = self.service.base / 'generation-receipts' / (saved['id'] + '.json')
                self.assertEqual(json.loads(path.read_text(encoding='utf-8')), receipt)
                # Each subcase must independently prove exactly one committed draft.
                preview = self.service.delete_preview(saved['id'])
                self.service.delete(saved['id'], preview['preview_token'])

    def test_real_receipt_serialization_error_preserves_committed_record_without_retry(self):
        class MisreportingEncoding(str):
            # Deliberately adversarial external result subtype: passes the
            # attribution preflight, but the REAL JSON writer sees its raw
            # surrogate and fails UTF-8 serialization. No serializer/store mock.
            def encode(self, encoding='utf-8', errors='strict'):
                return b'encoding-preflight-only'

        facade = Facade(model=MisreportingEncoding('fictional-\ud800-model'))
        result = self.draft(facade)
        saved = self.assert_committed(result, facade)
        self.assertFalse(result['receipt_persisted'])
        json.dumps(result, ensure_ascii=False).encode('utf-8')
        self.assertIsNone(result['generation_receipt']['model'])
        self.assertEqual(result['generation_receipt']['provider'], facade.provider)
        self.assertIn('Draft committed', result['warning'])
        self.assertIn('Do not repeat', result['warning'])
        receipt_path = self.service.base / 'generation-receipts' / (saved['id'] + '.json')
        self.assertFalse(receipt_path.exists())
        self.assertEqual(list(receipt_path.parent.iterdir()), [], 'Atomic serializer must clean its temporary file')
        self.assertEqual(saved['dependencies'], [{'id': self.source['id'], 'revision': self.source['revision']}])

    def derived(self, **changes):
        fields = dict(kind='summary', basis='inference', text='Fictional résumé: indigo 🟦, not certainty.',
                      sources=[{'ref': 'record:' + self.source['id'], 'quote': self.source['text']}],
                      dependencies=[{'id': self.source['id'], 'revision': self.source['revision']}])
        fields.update(changes)
        return self.create(**fields)

    def test_optional_source_revision_with_current_pin_drafts_without_changing_sources(self):
        derived = self.derived()
        self.service = WorkspaceService(self.home)
        before = self.service.store.get(derived['id'])
        self.assertIn(derived['id'], [r['id'] for r in self.service.store.visible_records(self.scope)])
        facade = Facade()
        result = self.draft(facade, derived)
        self.assertTrue(result['receipt_persisted'])
        self.assertEqual(result['state'], 'pending')
        self.assertEqual(result['domain'], derived['domain'])
        self.assertEqual(result['basis'], 'inference')
        self.assertEqual(result['dependencies'], [{'id': derived['id'], 'revision': derived['revision']}])
        self.assertEqual(result['sources'][0]['quote'], derived['text'])
        reopened = WorkspaceService(self.home)
        self.assertEqual(reopened.store.get(result['id'])['dependencies'], result['dependencies'])
        self.assertEqual(reopened.store.get(derived['id']), before)
        payload = json.loads(facade.calls[0]['messages'][1]['content'])
        self.assertEqual(json.dumps(payload['records'], sort_keys=True, ensure_ascii=False),
                         json.dumps([before], sort_keys=True, ensure_ascii=False))
        self.assertNotIn('revision', payload['records'][0]['sources'][0])
        self.assertEqual(len(facade.calls), 1)
        self.assertEqual(len(reopened.store.list_records(self.scope)), 3)

    def assert_preflight_refused(self, derived, code):
        facade = Facade()
        before = self.service.store.status()['revision']
        with self.assertRaises(RecordError) as refused:
            self.draft(facade, derived)
        self.assertEqual(refused.exception.code, code)
        self.assertEqual(facade.calls, [])
        self.assertEqual(self.service.store.status()['revision'], before)

    def test_optional_and_explicit_entries_in_transitive_reference_provenance_stay_exact(self):
        root = self.create(domain='reference', kind='reference', basis='source_document',
                           text='Fictional reference: 日本語 🟦')
        entries = [{'ref': 'record:' + root['id']},
                   {'ref': 'record:' + root['id'], 'revision': root['revision'], 'quote': root['text']}]
        middle = self.derived(domain='reference', sources=entries,
                              dependencies=[{'id': root['id'], 'revision': root['revision']}])
        selected = self.derived(domain='reference', kind='procedure',
                               sources=[{'ref': 'record:' + middle['id']}],
                               dependencies=[{'id': middle['id'], 'revision': middle['revision']}])
        originals = [self.service.store.get(r['id']) for r in (root, middle, selected)]
        facade = Facade()
        result = self.draft(facade, selected, kind='observation')
        self.assertEqual((result['domain'], result['kind'], result['basis'], result['state']),
                         ('reference', 'interpretation', 'inference', 'pending'))
        self.assertEqual(result['dependencies'], [{'id': selected['id'], 'revision': selected['revision']}])
        self.assertEqual(result['generation_receipt']['requested_kind'], 'observation')
        self.assertEqual(result['generation_receipt']['stored_kind'], 'interpretation')
        self.assertIn('not a direct observation', result['generation_receipt']['mapping'])
        for original in originals:
            self.assertEqual(self.service.store.get(original['id']), original)
        payload = json.loads(facade.calls[0]['messages'][1]['content'])
        self.assertEqual(payload['records'], [originals[-1]])
        self.assertEqual(len(facade.calls), 1)

    def test_real_store_rejects_missing_unversioned_or_stale_pins_before_egress(self):
        for dependencies, code in (([], 'undeclared_dependency'),
                                   ([self.source['id']], 'invalid_dependencies'),
                                   ([{'id': self.source['id'], 'revision': self.source['revision'] + 1}], 'stale_dependency')):
            with self.subTest(dependencies=dependencies):
                before = self.service.store.status()['revision']
                with self.assertRaises(RecordError) as refused:
                    self.derived(dependencies=dependencies)
                self.assertEqual(refused.exception.code, code)
                self.assertEqual(self.service.store.status()['revision'], before)
        self.assertEqual(len(self.service.store.list_records(self.scope)), 1)

    def test_every_present_explicit_revision_is_validated_even_after_optional_entry(self):
        for revision, code in ((None, 'invalid_sources'), (True, 'invalid_sources'),
                               ('1', 'invalid_sources'), (0, 'invalid_sources'),
                               (self.source['revision'] + 1, 'stale_dependency')):
            with self.subTest(revision=revision):
                entries = [{'ref': 'record:' + self.source['id']},
                           {'ref': 'record:' + self.source['id'], 'revision': self.source['revision']},
                           {'ref': 'record:' + self.source['id'], 'revision': revision}]
                before = self.service.store.status()['revision']
                with self.assertRaises(RecordError) as refused:
                    self.derived(sources=entries)
                self.assertEqual(refused.exception.code, code)
                self.assertEqual(self.service.store.status()['revision'], before)
        self.assertEqual(len(self.service.store.list_records(self.scope)), 1)

    def test_optional_revision_does_not_bypass_transitive_sensitive_or_domain_checks(self):
        for changes, code in (({'sensitive': True}, 'sensitive_selection'),
                              ({'domain': 'reference'}, 'mixed_domains')):
            with self.subTest(code=code):
                root = self.create(**changes)
                derived = self.derived(sources=[{'ref': 'record:' + root['id']}],
                                       dependencies=[{'id': root['id'], 'revision': root['revision']}])
                self.assert_preflight_refused(derived, code)

    def test_optional_revision_foreign_provenance_refuses_even_with_recall_grant(self):
        self.service.store.put_scope('personal', 'personal', 'Fictional personal', private=True)
        card = self.create(scope_id='personal', domain='user', kind='preference', topic='communication')
        self.service.grant('personal', self.scope, [card['id']])
        derived = self.derived(domain='user', sources=[{'ref': 'record:' + card['id']}],
                               dependencies=[{'id': card['id'], 'revision': card['revision']}])
        self.assert_preflight_refused(derived, 'foreign_dependency')

    def test_optional_revision_final_revalidation_discards_corrected_dependency(self):
        derived = self.derived()
        def correct():
            WorkspaceService(self.home).correct(self.source['id'], self.source['revision'], {'text': 'Copper instead.'})
        facade = Facade(callback=correct)
        with self.assertRaises(RecordError) as refused:
            self.draft(facade, derived)
        self.assertEqual(refused.exception.code, 'invalid_selection')
        self.assertEqual(len(facade.calls), 1)
        self.assertEqual(self.service.store.get(derived['id'])['state'], 'invalidated')
        self.assertEqual(len(self.service.store.list_records(self.scope)), 2)
        self.assertFalse((self.service.base / 'generation-receipts').exists())
        self.assert_preflight_refused(derived, 'invalid_selection')

    def test_bounded_unicode_attribution_is_preserved_without_replacement(self):
        facade = Facade(provider='供' * 256, model='fictional-🟦-modèle')
        result = self.draft(facade)
        self.assert_committed(result, facade)
        self.assertTrue(result['receipt_persisted'])
        for key in ('provider', 'model'):
            self.assertEqual(result['generation_receipt'][key], getattr(facade, key))
        receipt = self.service.base / 'generation-receipts' / (result['id'] + '.json')
        self.assertEqual(json.loads(receipt.read_text(encoding='utf-8')), result['generation_receipt'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
