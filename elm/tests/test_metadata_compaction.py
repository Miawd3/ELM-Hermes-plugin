"""Frozen pure complete-wire boundary: no engine/provider/manager initialization."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN))
from elm_plugin.measured_context import pack, packing_modules, serialize_result
from elm_plugin.token_budget import TokenCounter

FIXTURE = PLUGIN/'tests/fixtures/metadata_compaction_boundary.json'


def canonical(value):
    # JSON-text comparison distinguishes missing/null, false/0 and nested types.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def load_fixture():
    fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
    records = [{**{key: value for key, value in record.items() if key != 'text'},
                'memory': copy.deepcopy(fixture['memory']), 'text': record['text']}
               for record in fixture['records']]
    candidates = []
    for record in records:
        candidates.append({'section_key': record['source'].removeprefix('elm://section/'),
                           'path': record['path'], 'heading_path': record['heading'],
                           'status': record['status'], 'authority': record['authority'],
                           'memory': copy.deepcopy(record['memory']), 'text': record['text'],
                           'token_estimate': max(1, (len(record['text'])+3)//4)})
    return fixture, records, candidates


def emit(name, payload):
    target = os.environ.get('ELM_COMPACTION_EVIDENCE')
    if target:
        path = Path(target)/name
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')


class FullWireBoundary(unittest.TestCase):
    def test_three_complete_records_fit_700_with_exact_decoded_semantics(self):
        fixture, expected, candidates = load_fixture()
        self.assertEqual(len(expected), 3)
        before = canonical(candidates)
        counter = TokenCounter('o200k_base', os.environ['ELM_TEST_VOCAB'])
        ctx, codec = packing_modules()
        # Direct render quantifies encoding capacity, not a selection heuristic.
        packet = codec.render(expected, fixture['header'], len(candidates))
        wire = serialize_result(packet, fixture['project'], fixture['budget'], counter.name)
        result = pack(candidates, fixture['warnings'], project=fixture['project'],
                      budget=fixture['budget'], counter=counter)
        decoded = codec.decode(result['packet'])
        details = {
            'phase': 'pure-codec-and-measured-pack-not-native',
            'fixture_sha256': hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
            'budget': fixture['budget'], 'counter': counter.name,
            'full_three_wire_tokens': counter.count(wire),
            'selected_wire_tokens': counter.count(result['wire']),
            'selected_record_count': len(decoded),
            'selected_representations': [r['representation'] for r in decoded],
            'selected_sources': [r['source'] for r in decoded],
            'full_three_semantics_equal': canonical(codec.decode(packet)) == canonical(expected),
            'selected_semantics_equal': canonical(decoded) == canonical(expected),
            'input_unchanged': canonical(candidates) == before,
            'normalization_preserves_frozen_order': [c['section_key'] for c in ctx._normalized_candidates(candidates)] == [c['section_key'] for c in candidates],
            'header_unchanged': result['packet'].split(codec.MARKER, 1)[0] == fixture['header'],
            'full_three_wire': wire,
            'selected_wire': result['wire'],
            'expected_records': expected,
            'actual_records': decoded,
        }
        emit('BOUNDARY.json', details)
        self.assertTrue(details['full_three_semantics_equal'])
        self.assertTrue(details['input_unchanged'])
        self.assertTrue(details['normalization_preserves_frozen_order'])
        self.assertTrue(details['header_unchanged'])
        self.assertLessEqual(counter.count(result['wire']), fixture['budget'])
        self.assertLessEqual(counter.count(wire), fixture['budget'],
                             'Encoding capacity: all three full typed records plus unchanged warnings and complete outer JSON must fit 700')
        self.assertEqual(canonical(decoded), canonical(expected))
        self.assertEqual(result['wire'], wire)
        self.assertEqual(result['source_count'], 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
