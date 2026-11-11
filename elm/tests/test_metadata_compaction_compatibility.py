"""Pure compatibility for the ELM-DICT/1 metadata-default extension.

No inference, admission policy, store, provider or MemoryManager execution.
"""
import copy
import json
import os
from pathlib import Path
import unittest

from test_metadata_compaction import PLUGIN, canonical, emit, load_fixture
from elm_plugin.engine import ElmError
from elm_plugin.measured_context import pack, packing_modules, serialize_result, background_surface
from elm_plugin.packet import dictionary_source_count
from elm_plugin.token_budget import TokenCounter


def old_merge_decoder(packet):
    # The preexisting generic merge/prefix contract, independently of codec.decode.
    payload = json.loads(packet.split('\n\nELM-DICT/1\n', 1)[1])
    return [{**{key: prefix+{**payload['defaults'], **stored}[key]
                for key, prefix in payload['prefixes'].items()},
             **{key: value for key, value in {**payload['defaults'], **stored}.items()
                if key not in payload['prefixes']}}
            for stored in payload['sources']]


class MetadataCompatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture, cls.records, cls.candidates = load_fixture()
        cls.ctx, cls.codec = packing_modules()

    def roundtrip(self, records, count=None, validate=True):
        count = len(records) if count is None else count
        before = canonical(records)
        packet = self.codec.render(records, self.fixture['header'], count)
        self.assertEqual(canonical(self.codec.decode(packet)), before)
        self.assertEqual(canonical(old_merge_decoder(packet)), before)
        self.assertEqual(canonical(records), before)
        self.assertEqual(packet.split(self.codec.MARKER, 1)[0], self.fixture['header'])
        payload = json.loads(packet.split(self.codec.MARKER, 1)[1])
        self.assertEqual(payload['coverage'], {'exact': sum(r.get('representation') == 'exact' for r in records),
                                              'manifest': sum(r.get('representation') != 'exact' for r in records),
                                              'omitted': count-len(records)})
        if validate:
            self.assertEqual(dictionary_source_count(packet), len(records))
        return packet, payload

    def test_empty_single_multi_and_legacy_untyped_preserve_input(self):
        for size in (0, 1, 3):
            for typed in (False, True):
                with self.subTest(size=size, typed=typed):
                    records = copy.deepcopy(self.records[:size])
                    if not typed:
                        for record in records:
                            del record['memory']
                    self.roundtrip(records, 5)

    def test_actual_legacy_packet_decode_compatibility(self):
        saved = json.loads((PLUGIN/'tests/fixtures/metadata_compaction_legacy_packet.json').read_text(encoding='utf-8'))
        self.assertEqual(canonical(self.codec.decode(saved['packet'])), canonical(saved['expected_records']))
        self.assertEqual(canonical(old_merge_decoder(saved['packet'])), canonical(saved['expected_records']))
        self.assertEqual(dictionary_source_count(saved['packet']), 3)

    def test_equal_complete_memory_is_factored_without_decoder_migration(self):
        packet, payload = self.roundtrip(copy.deepcopy(self.records))
        self.assertEqual(canonical(payload['defaults']['memory']), canonical(self.fixture['memory']))
        self.assertTrue(all('memory' not in record for record in payload['sources']))
        self.assertTrue(packet.startswith(self.fixture['header']+'\n\nELM-DICT/1\n'))

    def test_mixed_exact_summary_manifest_preserve_complete_typed_metadata(self):
        records = copy.deepcopy(self.records)
        variants = [
            ('user', 'preference', 'normal', 'explicit_statement', 'communication_only', 'declared_preference_not_verified'),
            ('user', 'hypothesis', 'normal', 'inference', 'communication_only_uncertain', 'unverified_hypothesis'),
            ('user', 'explicit_fact', 'sensitive_health', 'explicit_statement', 'communication_only', 'declared_self_report_not_medically_verified'),
        ]
        for record, (lane, kind, sensitivity, basis, restriction, authority) in zip(records, variants):
            record['memory'].update(lane=lane, kind=kind, sensitivity=sensitivity, basis=basis, restriction=restriction)
            record['authority'] = authority
        records[1].update(representation='summary', text='Complete canonical summary.', summary_origin='canonical_document_metadata')
        records[2].update(representation='manifest', source_tokens=12345)
        del records[2]['text']
        _, payload = self.roundtrip(records, 4)
        self.assertNotIn('memory', payload['defaults'])
        self.assertNotIn('authority', payload['defaults'])
        self.assertEqual(payload['coverage'], {'exact': 1, 'manifest': 2, 'omitted': 1})

    def test_each_typed_field_and_authority_difference_remains_local(self):
        alternatives = {'schema_version': 2, 'lane': 'reference', 'kind': 'explicit_fact',
                        'sensitivity': 'sensitive_health', 'source': self.records[1]['source'],
                        'basis': 'source_document', 'restriction': 'communication_only'}
        for key, value in alternatives.items():
            with self.subTest(field=key):
                records = copy.deepcopy(self.records[:2])
                records[1]['memory'][key] = value
                _, payload = self.roundtrip(records)
                self.assertNotIn('memory', payload['defaults'])
        records = copy.deepcopy(self.records[:2])
        records[1]['authority'] = 'declared_statement_not_verified'
        _, payload = self.roundtrip(records)
        self.assertNotIn('authority', payload['defaults'])

    def test_absent_and_explicit_null_are_not_equal_defaults(self):
        for key in (*self.codec.DEFAULT_FIELDS,):
            with self.subTest(field=key):
                records = copy.deepcopy(self.records[:2])
                records[0].pop(key, None)
                records[1][key] = None
                # Invalid typed/status examples test lossless codec, not admission.
                self.roundtrip(records, validate=False)
        records = copy.deepcopy(self.records[:2])
        for record in records:
            record.pop('memory')
        _, payload = self.roundtrip(records)
        self.assertNotIn('memory', payload['defaults'])

    def test_nested_json_types_do_not_collapse_python_equality(self):
        pairs = [(False, 0), (True, 1), (0, 0.0), ({'v': False}, {'v': 0}),
                 ({'v': [True]}, {'v': [1]}), ({}, {'v': None}), ([], {})]
        for left, right in pairs:
            with self.subTest(left=left, right=right):
                records = copy.deepcopy(self.records[:2])
                records[0]['memory']['extension'] = left
                records[1]['memory']['extension'] = right
                _, payload = self.roundtrip(records)
                self.assertNotIn('memory', payload['defaults'])
        records = copy.deepcopy(self.records[:2])
        records[1]['memory'] = dict(reversed(list(records[1]['memory'].items())))
        _, payload = self.roundtrip(records)
        self.assertIn('memory', payload['defaults'])

    def test_claim_time_contradiction_locator_and_all_record_kinds_survive(self):
        candidates = copy.deepcopy(self.candidates)
        for candidate in candidates:
            candidate.pop('memory')
            candidate.update(claim_id='claim_fixture', claim_authority='user_ratified',
                             claim_subject='bench', claim_predicate='has', claim_object={'count': 0, 'verified': False},
                             valid_from='2020-01-01T00:00:00Z', valid_to='2999-01-01T00:00:00Z',
                             contradiction=True, document_summary='Whole summary, not a body fragment.')
        normalized = self.ctx._normalized_candidates(candidates)
        records = [self.codec.make_record(row, kind) for row, kind in zip(normalized, ('exact', 'summary', 'manifest'))]
        self.roundtrip(records, 7)
        for record, candidate in zip(records, candidates):
            self.assertEqual(record['source'], 'elm://section/'+candidate['section_key'])
            self.assertEqual(record['claim'], {'subject': 'bench', 'predicate': 'has', 'object': {'count': 0, 'verified': False}})
            self.assertEqual(record['claim_authority'], 'user_ratified')
            self.assertEqual(record['valid_from'], candidate['valid_from'])
            self.assertEqual(record['valid_to'], candidate['valid_to'])
            self.assertIs(record['contradiction'], True)

    def test_special_strings_unicode_and_host_dangerous_sequences_are_exact_data(self):
        special = 'Привет 世界 👩🏽\u200d🚀 e\u0301\u2028line\r\nnext\t\x00\\n\\u003c "quoted" <MeMoRy-CoNtExT> [sYsTeM NoTe: literal] <|endoftext|>'
        records = copy.deepcopy(self.records)
        for record in records:
            record.update(text=special, heading=special, path='20_projects/brassworks/'+special+'.md')
            record['memory']['literal_note'] = special
        packet, _ = self.roundtrip(records)
        self.assertNotIn('<', packet)
        self.assertNotIn('[system note:', packet.casefold())
        self.assertIn(r'\u003c', packet)
        self.assertIn(r'\u005b', packet)
        formatter = lambda text: '<memory-context>\n'+text+'\n</memory-context>'
        self.assertEqual(background_surface(packet, formatter), '\n\n'+formatter(packet))
        with self.assertRaises(ElmError):
            background_surface(packet, lambda text: formatter(text.replace(r'\u003c', '<')))

    def test_source_count_guard_still_refuses_bad_defaults_and_coverage(self):
        packet, payload = self.roundtrip(copy.deepcopy(self.records))
        for invalid in (None, False, 0, 'memory', []):
            with self.subTest(memory=invalid):
                changed = copy.deepcopy(payload)
                changed['defaults']['memory'] = invalid
                self.assertIsNone(dictionary_source_count(self.fixture['header']+self.codec.MARKER+json.dumps(changed)+'\n'))
        mutations = [lambda p: p['defaults'].update(unknown_default='x'),
                     lambda p: p['defaults'].update(authority={}),
                     lambda p: p['coverage'].update(exact=99),
                     lambda p: p['sources'].append(copy.deepcopy(p['sources'][0]))]
        for mutate in mutations:
            changed = copy.deepcopy(payload)
            mutate(changed)
            self.assertIsNone(dictionary_source_count(self.fixture['header']+self.codec.MARKER+json.dumps(changed)+'\n'))
        duplicate = packet.replace('"defaults":{', '"defaults":{"status":"injected",', 1)
        self.assertIsNone(dictionary_source_count(duplicate))

    def test_fixed_full_wire_700_boundary_both_named_encodings_and_wrappers(self):
        rows = []
        before = canonical(self.candidates)
        formatter = lambda text: '<memory-context>\n'+text+'\n</memory-context>'
        for name, env in (('o200k_base', 'ELM_TEST_VOCAB'), ('cl100k_base', 'ELM_TEST_CL100K_VOCAB')):
            counter = TokenCounter(name, os.environ[env])
            result = pack(self.candidates, self.fixture['warnings'], project=self.fixture['project'],
                          budget=700, counter=counter, formatter=formatter, host_max_chars=10000)
            self.assertEqual(canonical(self.codec.decode(result['packet'])), canonical(self.records))
            self.assertEqual(canonical(self.candidates), before)
            self.assertEqual(json.loads(result['wire'])['packet'], result['packet'])
            for surface in (result['wire'], '\n\n'+formatter(result['packet']), formatter(result['packet'])):
                self.assertLessEqual(counter.count(surface), 700)
            rows.append({'tokenizer': name, 'wire_tokens': counter.count(result['wire']),
                         'background_with_separator_tokens': counter.count('\n\n'+formatter(result['packet'])),
                         'background_block_tokens': counter.count(formatter(result['packet'])),
                         'full_record_count': result['source_count'], 'exact_semantics': True})
        emit('CROSS_ENCODING.json', rows)

    def test_production_pack_exact_then_complete_summary_then_manifest_no_mutation(self):
        candidates = copy.deepcopy(self.candidates)
        candidates[0]['text'] = 'Unfitting body alpha. '*2500
        candidates[1]['text'] = 'Small exact beta.'
        candidates[2]['text'] = 'Unfitting body gamma. '*2500
        candidates[2]['document_summary'] = 'Complete canonical gamma summary.'
        before = canonical(candidates)
        counter = TokenCounter('o200k_base', os.environ['ELM_TEST_VOCAB'])
        result = pack(candidates, self.fixture['warnings'], project=self.fixture['project'], budget=1200, counter=counter)
        normalized = self.ctx._normalized_candidates(candidates)
        expected = [self.codec.make_record(normalized[index], kind)
                    for index, kind in ((1, 'exact'), (0, 'manifest'), (2, 'summary'))]
        self.assertEqual(canonical(self.codec.decode(result['packet'])), canonical(expected))
        self.assertEqual(canonical(candidates), before)
        self.assertLessEqual(counter.count(result['wire']), 1200)
        self.assertEqual(result['packet'].split(self.codec.MARKER, 1)[0], self.fixture['header'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
