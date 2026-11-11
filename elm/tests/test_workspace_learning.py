"""Offline draft consumer tests: real service/store, fake only ctx.llm boundary."""
import importlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from elm_plugin.workspace_service import WorkspaceService
from elm_plugin.workspace_records import RecordError


class Facade:
    def __init__(self, callback=None, text=None):
        self.calls = []
        self.callback = callback
        self.text = text or json.dumps({'title': 'Banner summary', 'text': 'The fictional brief requests indigo banners.'})

    def complete(self, *, messages, temperature, max_tokens, timeout, purpose):
        self.calls.append(dict(messages=messages, temperature=temperature, max_tokens=max_tokens,
                               timeout=timeout, purpose=purpose))
        if self.callback:
            self.callback()
        return SimpleNamespace(text=self.text, provider='offline-fixture', model='fictional-model',
            usage=SimpleNamespace(input_tokens=50, output_tokens=20, total_tokens=70,
                                  cache_read_tokens=0, cache_write_tokens=0, cost_usd=None),
            audit={'raw_thinking': 'NEVER SAVE', 'authorization': 'NEVER SAVE'})


class WorkspaceLearningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='workspace-learning-')
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.service = WorkspaceService(self.home)
        self.service.setup(confirm=True)
        self.scope = 'workspace:fictional-lantern'
        self.service.store.put_scope(self.scope, 'workspace', 'Fictional Lantern', private=True)
        self.source = self.source_record()
        self.service.set_learning(True)

    def source_record(self, **changes):
        fields = dict(scope_id=self.scope, title='Fictional brief', text='Use indigo banners.',
            domain='work', kind='explicit_fact', basis='explicit_statement',
            sources=[{'ref': 'fictional:brief', 'quote': 'Use indigo banners.'}], state='approved')
        fields.update(changes)
        return self.service.create_record(fields)

    def learning(self, facade=None):
        try:
            module = importlib.import_module('elm_plugin.workspace_learning')
        except ModuleNotFoundError as exc:
            if exc.name == 'elm_plugin.workspace_learning':
                self.fail('Source-backed pending draft pipeline is not implemented')
            raise
        return module.WorkspaceLearning(self.service, facade or Facade())

    def test_real_pending_record_reopens_with_exact_repository_provenance_and_receipt(self):
        facade = Facade()
        result = self.learning(facade).draft(self.scope, [self.source['id']], 'summary')
        record = self.service.store.get(result['id'])
        reopened = WorkspaceService(self.home).store.get(record['id'])
        self.assertEqual(record, reopened)
        self.assertEqual(record['state'], 'pending')
        self.assertEqual(record['domain'], 'work')
        self.assertEqual(record['kind'], 'summary')
        self.assertEqual(record['basis'], 'inference')
        self.assertEqual(record['scope_id'], self.scope)
        self.assertEqual(record['dependencies'], [{'id': self.source['id'], 'revision': self.source['revision']}])
        self.assertEqual(record['sources'][0]['ref'], 'record:' + self.source['id'])
        self.assertEqual(record['sources'][0]['revision'], self.source['revision'])
        self.assertEqual(record['sources'][0]['quote'], self.source['text'])
        self.assertEqual(self.service.store.visible_records(self.scope), [self.service.store.get(self.source['id'])])
        self.assertEqual(len(facade.calls), 1)
        call = facade.calls[0]
        self.assertEqual(call['timeout'], 45.0)
        self.assertEqual(call['max_tokens'], 1024)
        self.assertNotIn('provider', call)
        generation = result['generation_receipt']
        self.assertEqual(generation['provider'], 'offline-fixture')
        self.assertEqual(generation['usage']['total_tokens'], 70)
        self.assertGreaterEqual(generation['elapsed_seconds'], 0)
        receipt = self.service.base / 'generation-receipts' / (record['id'] + '.json')
        self.assertEqual(json.loads(receipt.read_text(encoding='utf-8')), generation)
        self.assertNotIn('NEVER SAVE', receipt.read_text(encoding='utf-8'))
        self.assertNotIn(self.source['text'], receipt.read_text(encoding='utf-8'))


    def test_sensitive_metadata_requires_separate_consent_and_never_calls_model(self):
        sensitive = self.source_record(sensitive=True)
        facade = Facade()
        with self.assertRaises(RecordError) as refused:
            self.learning(facade).draft(self.scope, [sensitive['id']], 'summary')
        self.assertEqual(refused.exception.code, 'sensitive_selection')
        self.assertEqual(facade.calls, [])
        self.assertEqual(len(self.service.store.list_records(self.scope)), 2)


    def assert_preflight_refused(self, ids, *, kind='summary', code=None, scope=None):
        facade = Facade()
        revision = self.service.store.status()['revision']
        before = self.service.store.list_records(self.scope)
        with self.assertRaises(RecordError) as refused:
            self.learning(facade).draft(scope or self.scope, ids, kind)
        if code:
            self.assertEqual(refused.exception.code, code)
        self.assertEqual(facade.calls, [], 'A refusal must precede source egress')
        self.assertEqual(self.service.store.status()['revision'], revision)
        self.assertEqual(self.service.store.list_records(self.scope), before)

    def test_mixed_domains_refuse_before_call_instead_of_relabeling_personal_material(self):
        personal = self.source_record(domain='user', text='Fictional personal preference.')
        self.assert_preflight_refused([self.source['id'], personal['id']], code='mixed_domains')

    def test_explicit_personal_health_topic_refuses_even_when_sensitive_flag_is_false(self):
        personal = self.source_record(domain='user', topic='personal-health', text='Invented self report.')
        self.assert_preflight_refused([personal['id']], code='sensitive_selection')

    def test_selection_shape_duplicates_and_oversize_are_not_silently_truncated(self):
        for ids in ([], [self.source['id']] * 2, [self.source['id']] * 9, 'all', [None], [{}]):
            with self.subTest(ids=ids):
                self.assert_preflight_refused(ids, code='invalid_selection')
        long_source = self.source_record(text='x' * 2001)
        self.assert_preflight_refused([long_source['id']], code='source_limit')

    def test_only_exact_selected_approved_same_scope_records_egress(self):
        self.source_record(text='UNSELECTED LOCAL SECRET')
        pending = self.source_record(state='pending', text='UNAPPROVED SECRET')
        self.service.store.put_scope('chat:foreign', 'chat', 'Foreign chat', private=True)
        foreign = self.source_record(scope_id='chat:foreign', text='FOREIGN PRIVATE SECRET')
        self.assert_preflight_refused([pending['id']], code='invalid_selection')
        self.assert_preflight_refused([foreign['id']], code='invalid_selection')
        self.service.set_learning(False)
        self.assert_preflight_refused([self.source['id']], code='learning_disabled')
        self.service.set_learning(True)
        facade = Facade()
        self.learning(facade).draft(self.scope, [self.source['id']], 'summary')
        prompt = json.dumps(facade.calls[0]['messages'])
        self.assertIn(self.source['text'], prompt)
        for forbidden in ('UNSELECTED LOCAL SECRET', 'UNAPPROVED SECRET', 'FOREIGN PRIVATE SECRET'):
            self.assertNotIn(forbidden, prompt)


    def test_output_bound_and_duplicate_keys_refuse_without_committing(self):
        responses = [
            json.dumps({'title': 'x' * 161, 'text': 'Fictional summary'}),
            json.dumps({'title': 'Fictional summary', 'text': 'x' * 4001}),
            '{"title":"First", "text":"Summary", "title":"Second"}',
            json.dumps({'title': 'Title', 'text': 'x' * 9000}),
        ]
        for response in responses:
            with self.subTest(response_length=len(response)):
                before = self.service.store.status()['revision']
                facade = Facade(text=response)
                with self.assertRaises(RecordError) as refused:
                    self.learning(facade).draft(self.scope, [self.source['id']], 'summary')
                self.assertEqual(refused.exception.code, 'invalid_generation')
                self.assertEqual(self.service.store.status()['revision'], before)
                self.assertEqual(len(facade.calls), 1)

    def test_model_authority_schema_injection_is_rejected_not_ignored(self):
        for field, value in (('state', 'approved'), ('scope_id', 'personal'), ('domain', 'user'),
                             ('dependencies', []), ('sources', []), ('operation', 'execute'),
                             ('basis', 'explicit_statement')):
            with self.subTest(field=field):
                before = self.service.store.status()['revision']
                response = json.dumps({'title': 'Draft', 'text': 'Proposal', field: value})
                facade = Facade(text=response)
                with self.assertRaises(RecordError) as refused:
                    self.learning(facade).draft(self.scope, [self.source['id']], 'procedure')
                self.assertEqual(refused.exception.code, 'invalid_generation')
                self.assertEqual(self.service.store.status()['revision'], before)

    def test_consent_can_be_revoked_during_model_wait_without_partial_draft(self):
        def revoke():
            # Uses a separate real service object and its OS operation lock.
            WorkspaceService(self.home).set_learning(False)
        facade = Facade(callback=revoke)
        with self.assertRaises(RecordError):
            self.learning(facade).draft(self.scope, [self.source['id']], 'summary')
        self.assertFalse(self.service.settings()['learning_enabled'])
        self.assertEqual([r['id'] for r in self.service.store.list_records(self.scope)], [self.source['id']])
        self.assertEqual(len(facade.calls), 1)
        self.assertFalse((self.service.base / 'generation-receipts').exists())

    def test_revoke_then_reenable_does_not_reauthorize_old_inflight_generation(self):
        def change_consent():
            other = WorkspaceService(self.home)
            other.set_learning(False)
            other.set_learning(True)
        facade = Facade(callback=change_consent)
        with self.assertRaises(RecordError) as refused:
            self.learning(facade).draft(self.scope, [self.source['id']], 'summary')
        self.assertEqual(refused.exception.code, 'draft_stale')
        self.assertEqual(len(self.service.store.list_records(self.scope)), 1)

    def test_correction_and_privacy_changes_during_wait_discard_stale_output(self):
        def correction():
            WorkspaceService(self.home).correct(self.source['id'], self.source['revision'], {'text': 'Use copper banners.'})
        with self.assertRaises(RecordError):
            self.learning(Facade(callback=correction)).draft(self.scope, [self.source['id']], 'summary')
        self.assertEqual(self.service.store.get(self.source['id'])['text'], 'Use copper banners.')
        def privacy():
            WorkspaceService(self.home).set_privacy(self.scope, False)
        with self.assertRaises(RecordError):
            self.learning(Facade(callback=privacy)).draft(self.scope, [self.source['id']], 'summary')
        self.assertFalse(self.service.store.get_scope(self.scope)['private'])
        self.assertEqual(len(self.service.store.list_records(self.scope)), 1)

    def test_model_failure_or_timeout_saves_nothing_and_never_retries(self):
        for exception in (TimeoutError('secret prompt'), RuntimeError('Authorization: secret')):
            def fail(exception=exception):
                raise exception
            facade = Facade(callback=fail)
            before = self.service.store.status()['revision']
            with self.assertRaises(RecordError) as refused:
                self.learning(facade).draft(self.scope, [self.source['id']], 'summary')
            self.assertEqual(refused.exception.code, 'generation_failed')
            self.assertNotIn('secret', str(refused.exception))
            self.assertIsNone(refused.exception.__cause__)
            self.assertEqual(len(facade.calls), 1)
            self.assertEqual(self.service.store.status()['revision'], before)
            self.assertFalse((self.service.base / 'generation-receipts').exists())


    def test_transitive_sensitive_dependency_cannot_be_laundered_by_nonsensitive_summary(self):
        sensitive = self.source_record(sensitive=True)
        derived = self.source_record(kind='summary', basis='inference', text='A fictional derived summary.',
            sources=[{'ref': 'record:' + sensitive['id'], 'revision': sensitive['revision']}],
            dependencies=[{'id': sensitive['id'], 'revision': sensitive['revision']}])
        self.assert_preflight_refused([derived['id']], code='sensitive_selection')

    def test_foreign_dependency_is_refused_despite_explicit_recall_grant(self):
        self.service.store.put_scope('personal', 'personal', 'Personal', private=True)
        card = self.source_record(scope_id='personal', domain='user', kind='preference',
            topic='communication', text='Use compact paragraphs.')
        self.service.grant('personal', self.scope, [card['id']])
        derived = self.source_record(domain='user', kind='summary', basis='inference',
            text='A fictional communication summary.',
            sources=[{'ref': 'record:' + card['id'], 'revision': card['revision']}],
            dependencies=[{'id': card['id'], 'revision': card['revision']}])
        self.assert_preflight_refused([card['id']], code='invalid_selection')
        self.assert_preflight_refused([derived['id']], code='foreign_dependency')

    def test_observation_mapping_preserves_inference_and_procedure_never_executes(self):
        observed = self.learning().draft(self.scope, [self.source['id']], 'observation')
        self.assertEqual(observed['kind'], 'interpretation')
        self.assertEqual(observed['basis'], 'inference')
        self.assertIn('not a direct observation', observed['generation_receipt']['mapping'])
        procedure = self.learning().draft(self.scope, [self.source['id']], 'procedure')
        self.assertEqual(procedure['kind'], 'procedure')
        self.assertEqual(procedure['basis'], 'inference')
        self.assertEqual(procedure['state'], 'pending')
        self.assertEqual(self.service.grants(), [])
        self.assertFalse((self.home / 'skills').exists())

    def test_source_correction_after_approval_invalidates_generated_record(self):
        drafted = self.learning().draft(self.scope, [self.source['id']], 'summary')
        self.service.approve(drafted['id'], drafted['revision'])
        self.service.correct(self.source['id'], self.source['revision'], {'text': 'Use copper banners.'})
        reopened = WorkspaceService(self.home).store.get(drafted['id'])
        self.assertEqual(reopened['state'], 'invalidated')
        self.assertNotIn(drafted['id'], [r['id'] for r in self.service.store.visible_records(self.scope)])

    def test_receipt_write_failure_is_reported_as_committed_not_a_failed_model_retry(self):
        (self.service.base / 'generation-receipts').write_text('owned obstruction', encoding='utf-8')
        facade = Facade()
        result = self.learning(facade).draft(self.scope, [self.source['id']], 'summary')
        self.assertFalse(result['receipt_persisted'])
        self.assertIn('Do not repeat', result['warning'])
        persisted = self.service.store.get(result['id'])
        for field, value in persisted.items():
            self.assertEqual(result[field], value)
        self.assertEqual(len(facade.calls), 1)


    def test_human_draft_wire_returns_full_record_at_top_level_with_generation_receipt(self):
        result = self.learning().draft(self.scope, [self.source['id']], 'summary')
        self.assertIn('id', result, 'The UI requires full record fields at result top level')
        reopened = self.service.store.get(result['id'])
        for field, value in reopened.items():
            self.assertEqual(result[field], value)
        self.assertEqual(result['generation_receipt']['record_id'], result['id'])
        self.assertEqual(result['generation_receipt']['stored_kind'], result['kind'])
        self.assertEqual([d['id'] for d in result['dependencies']], [self.source['id']])


    def test_missing_or_malformed_model_text_is_refused_without_write(self):
        for response in ('not JSON', '[]', 'null', '{}', '{"title": "Title", "text": null}',
                         '{"title": "", "text": "Summary"}', '```json\n{"title":"T","text":"S"}\n```'):
            with self.subTest(response=response):
                before = self.service.store.status()['revision']
                with self.assertRaises(RecordError) as refused:
                    self.learning(Facade(text=response)).draft(self.scope, [self.source['id']], 'summary')
                self.assertEqual(refused.exception.code, 'invalid_generation')
                self.assertEqual(self.service.store.status()['revision'], before)

    def test_source_count_total_text_and_utf8_packet_limits(self):
        many = [self.source] + [self.source_record() for _ in range(8)]
        self.assert_preflight_refused([r['id'] for r in many], code='invalid_selection')
        too_much = [self.source_record(text='x' * 1800) for _ in range(5)]
        self.assert_preflight_refused([r['id'] for r in too_much], code='source_limit')
        unicode_sources = [self.source_record(text='🟦' * 2000) for _ in range(4)]
        self.assert_preflight_refused([r['id'] for r in unicode_sources], code='source_limit')
        facade = Facade()
        result = self.learning(facade).draft(self.scope, [r['id'] for r in many[:8]], 'summary')
        self.assertEqual(len(result['dependencies']), 8)
        self.assertEqual(len(facade.calls), 1)

    def test_dependency_correction_and_source_delete_during_wait_store_no_draft(self):
        derived = self.source_record(kind='summary', basis='inference', text='A fictional source summary.',
            sources=[{'ref': 'record:' + self.source['id'], 'revision': self.source['revision']}],
            dependencies=[{'id': self.source['id'], 'revision': self.source['revision']}])
        def correct_dependency():
            WorkspaceService(self.home).correct(self.source['id'], self.source['revision'], {'text': 'Copper.'})
        with self.assertRaises(RecordError):
            self.learning(Facade(callback=correct_dependency)).draft(self.scope, [derived['id']], 'summary')
        self.assertEqual(self.service.store.get(derived['id'])['state'], 'invalidated')
        self.assertEqual(len(self.service.store.list_records(self.scope)), 2)
        def delete_source():
            other = WorkspaceService(self.home)
            preview = other.delete_preview(self.source['id'])
            other.delete(self.source['id'], preview['preview_token'])
        with self.assertRaises(RecordError):
            self.learning(Facade(callback=delete_source)).draft(self.scope, [self.source['id']], 'summary')
        self.assertEqual(self.service.store.list_records(self.scope), [])
        self.assertFalse((self.service.base / 'generation-receipts').exists())

    def test_reference_and_user_domains_are_inherited_not_model_selected(self):
        for domain in ('reference', 'user'):
            with self.subTest(domain=domain):
                source = self.source_record(domain=domain)
                result = self.learning().draft(self.scope, [source['id']], 'summary')
                self.assertEqual(result['domain'], domain)
                self.assertEqual(result['basis'], 'inference')

    def test_generation_receipt_ignores_unbounded_or_non_numeric_metadata(self):
        class MetadataFacade(Facade):
            def complete(inner_self, **kwargs):
                result = super().complete(**kwargs)
                result.provider = {'authorization': 'NEVER SAVE'}
                result.model = 'm' * 1000
                result.usage = {'input_tokens': 10 ** 1000, 'output_tokens': '20',
                                'cost_usd': float('nan'), 'raw_thinking': 'NEVER SAVE'}
                return result
        result = self.learning(MetadataFacade()).draft(self.scope, [self.source['id']], 'summary')
        receipt = result['generation_receipt']
        self.assertIsNone(receipt['provider'])
        self.assertIsNone(receipt['model'])
        self.assertEqual(receipt['usage'], {})
        self.assertNotIn('NEVER SAVE', json.dumps(receipt))


if __name__ == '__main__':
    unittest.main(verbosity=2)
