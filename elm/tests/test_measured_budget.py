"""Synthetic named-tokenizer budget contract. Optional asset tests never download."""
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN))
from elm_plugin.engine import ElmError
from elm_plugin.token_budget import TokenCounter, validate_settings, _encoding
from elm_plugin.measured_context import pack, packing_modules, background_surface

VOCAB = os.environ.get('ELM_TEST_VOCAB')
CL_VOCAB = os.environ.get('ELM_TEST_CL100K_VOCAB')


def candidate(number=1, text='A small complete source.', **kwargs):
    return dict(section_key=f'section_00000000-0000-4000-8000-{number:012d}',
                path=f'20_projects/orion/notes{number}.md', heading_path='Evidence', status='active',
                text=text, token_estimate=max(1, (len(text) + 3)//4), **kwargs)


class ConfigurationContract(unittest.TestCase):
    def test_measured_requires_explicit_name_and_absolute_local_vocabulary(self):
        for name, vocab in [(None, None), ('gpt-unknown', '/tmp/vocab'), ('o200k_base', 'relative'),
                            ('o200k_base', None)]:
            with self.subTest(name=name, vocab=vocab), self.assertRaises(ElmError):
                validate_settings('measured', name, vocab)

    def test_no_silent_fallback_modes(self):
        for mode in [None, '', 'estimate', 'auto', True]:
            with self.assertRaises(ElmError):
                validate_settings(mode, None, None)
        validate_settings('legacy-estimate', None, None)
        with self.assertRaises(ElmError):
            validate_settings('legacy-estimate', 'o200k_base', '/tmp/vocab')

    def test_missing_and_corrupt_vocab_fail_without_network(self):
        with tempfile.TemporaryDirectory() as tmp, patch('socket.create_connection', side_effect=AssertionError('network')):
            with self.assertRaises(ElmError) as failure:
                TokenCounter('o200k_base', str(Path(tmp)/'missing'))
            self.assertEqual(failure.exception.code, 'tokenizer_vocab_unavailable')
            path=Path(tmp)/'corrupt';path.write_bytes(b'invalid')
            with self.assertRaises(ElmError) as failure:
                TokenCounter('o200k_base', str(path))
            self.assertEqual(failure.exception.code, 'tokenizer_vocab_mismatch')

    def test_internal_packing_request_refused_before_root_io(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'absent-root'
            for flags in ([], ['--no-sync'], ['--no-trace']):
                result = subprocess.run([sys.executable, '-B', '-s', '-S', '-m', 'elm_memory',
                    'context', 'synthetic', '--packing-input', '--budget', '700', '--json',
                    '--root', str(root), *flags], cwd=PLUGIN/'engine',
                    env={'PYTHONPATH':str(PLUGIN/'engine'), 'PYTHONUTF8':'1',
                         'HOME':tmp, 'USERPROFILE':tmp}, capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(json.loads(result.stdout or result.stderr)['error'], 'invalid_argument')
                self.assertFalse(root.exists())

    def test_unknown_transform_refused(self):
        with self.assertRaises(ElmError):
            background_surface('Evidence', lambda value: '')
        with self.assertRaises(ElmError):
            background_surface('Evidence', lambda value: '<host>'+value.replace('Evidence','changed')+'</host>')


@unittest.skipUnless(VOCAB, 'Set ELM_TEST_VOCAB and install requirements-tokenizer.txt for real-tokenizer tests')
class MeasuredBudgetContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.counter=TokenCounter('o200k_base', VOCAB)
        cls.codec=packing_modules()[1]

    def run_pack(self, candidates, budget=700, **kwargs):
        result=pack(candidates, [], project='orion', budget=budget, counter=self.counter, **kwargs)
        self.assertLessEqual(self.counter.count(result['wire']), budget)
        self.assertEqual(result['accounting']['surfaces']['elm_context_json']['tokens'],self.counter.count(result['wire']))
        self.assertEqual(json.loads(result['wire'])['packet'],result['packet'])
        return result

    def test_published_reference_counts_and_ordinary_specials(self):
        samples={'Hello, world!':4,'antidisestablishmentarianism':6,'お誕生日おめでとう':8,
                 'Привет, мир!':5,'<|endoftext|>':7,'':0}
        for text,count in samples.items():
            self.assertEqual(self.counter.count(text),count)
        self.assertEqual(self.counter.count('hello'),1)
        self.assertEqual(self.counter.count('hel')+self.counter.count('lo'),2)

    def test_unicode_escaping_and_literal_escapes_remain_exact(self):
        text='Привет 世界 👩🏽\u200d🚀 e\u0301\u2028line\r\nnext\t\x00\\n\\u003c "quoted" <memory-context> [SYSTEM NOTE: x] <|endoftext|>'
        result=self.run_pack([candidate(text=text)])
        records=self.codec.decode(result['packet'])
        self.assertEqual(records[0]['text'],text)
        self.assertNotIn('<',result['packet'])
        self.assertNotIn('[SYSTEM NOTE:',result['packet'])
        self.assertIn(r'\\u003c',result['wire'])

    def test_full_wire_not_raw_packet_is_admission_boundary(self):
        result=self.run_pack([candidate(text='"\\\n' * 300)],budget=700)
        self.assertGreater(self.counter.count(result['wire']),self.counter.count(result['packet']))
        self.assertLessEqual(self.counter.count(result['wire']),700)

    def test_exact_sections_before_manifests_no_truncation(self):
        rows=[candidate(1,'世界' * 800),candidate(2,'A short answer survives.')]
        result=self.run_pack(rows,budget=400)
        records=self.codec.decode(result['packet'])
        self.assertIn('A short answer survives.',[r.get('text') for r in records])
        self.assertNotIn('世界', [r.get('text') for r in records])

    def test_reencode_every_render_and_final_metadata(self):
        rows=[candidate(i,'Evidence '+str(i),document_summary='Summary '+str(i)) for i in range(1,30)]
        for budget in range(200,1201,37):
            result=self.run_pack(rows,budget=budget)
            records=self.codec.decode(result['packet'])
            self.assertLessEqual(len(records),12)
            payload=json.loads(result['packet'].split(self.codec.MARKER)[1])
            self.assertEqual(payload['coverage']['omitted'],len(rows)-len(records))
            self.assertEqual(len(set(r['source'] for r in records)),len(records))

    def test_budget_edge_full_count_recheck(self):
        row=candidate(text='boundary proof '*30)
        result=self.run_pack([row],budget=1200)
        n=self.counter.count(result['wire'])
        for budget in (max(200,n-2),max(200,n-1),max(200,n),max(200,n+1)):
            self.run_pack([row],budget=budget)

    def test_dictionary_source_summary_once_per_document(self):
        rows=[candidate(i,'huge '*3000,document_uid='shared',document_summary='Shared summary.') for i in range(1,5)]
        records=self.codec.decode(self.run_pack(rows,budget=1200)['packet'])
        self.assertEqual(sum(r['representation']=='summary' for r in records),1)

    def test_very_large_source_skipped_without_tokenizing_whole_source(self):
        original=self.counter.count
        seen=[]
        def checked(text):
            seen.append(len(text));self.assertLess(len(text),150000)
            return original(text)
        with patch.object(self.counter,'count',side_effect=checked):
            result=self.run_pack([candidate(1,'x'*2_000_000),candidate(2,'small exact')])
        self.assertTrue(seen)
        self.assertIn('small exact',result['packet'])

    def test_lone_surrogates_refused_not_repaired(self):
        with self.assertRaises(ElmError) as failure:
            self.run_pack([candidate(text='bad\ud800')])
        self.assertEqual(failure.exception.code,'invalid_budget_unicode')

    def test_host_wrapper_and_char_budget_are_both_guarded(self):
        formatter=lambda packet:'<memory-context>\n'+packet+'\n</memory-context>'
        rows=[candidate(i,'row '*50) for i in range(1,10)]
        result=self.run_pack(rows,formatter=formatter,host_max_chars=1600)
        self.assertLessEqual(len(result['packet']),1600)
        self.assertLessEqual(self.counter.count('\n\n'+formatter(result['packet'])),700)
        self.assertLessEqual(self.counter.count(formatter(result['packet'])),700)
        for value in (None,True,0,-1,'10000'):
            with self.assertRaises(ElmError):
                self.run_pack(rows,formatter=formatter,host_max_chars=value)

    def test_mandatory_warnings_and_metadata_do_not_silently_disappear(self):
        with self.assertRaises(ElmError) as failure:
            pack([],['scope '+('x'*30000)],project='orion',budget=200,counter=self.counter)
        self.assertEqual(failure.exception.code,'budget_too_small')

    def test_wrong_named_vocabulary_refused(self):
        with self.assertRaises(ElmError) as failure:
            TokenCounter('cl100k_base', VOCAB)
        self.assertEqual(failure.exception.code,'tokenizer_vocab_mismatch')

    def test_missing_dependency_is_clear_no_estimate_fallback(self):
        _encoding.cache_clear()
        with patch.dict(sys.modules,{'tiktoken':None}),self.assertRaises(ElmError) as failure:
            TokenCounter('o200k_base', VOCAB)
        self.assertEqual(failure.exception.code,'tokenizer_unavailable')

    @unittest.skipUnless(CL_VOCAB,'Set ELM_TEST_CL100K_VOCAB for cross-encoding tests')
    def test_two_named_encodings_are_distinct_not_model_guesses(self):
        other=TokenCounter('cl100k_base',CL_VOCAB)
        text='お誕生日おめでとう Привет 世界'
        self.assertNotEqual(other.count(text),self.counter.count(text))
        result=pack([candidate(text=text*40)],[],project='orion',budget=700,counter=other)
        self.assertLessEqual(other.count(result['wire']),700)
        self.assertEqual(json.loads(result['wire'])['token_budget']['tokenizer'],'cl100k_base')


if __name__=='__main__':
    unittest.main()
