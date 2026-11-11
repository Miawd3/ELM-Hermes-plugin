"""Typed-source separation through the actual isolated engine/provider."""
from pathlib import Path
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_provider import PLUGIN, engine, note, ElmMemoryProvider

USER_MARKER = 'TYPED_USER_PRIVATE_8c96'


def typed_note(project, text, lane='user', kind='preference', sensitivity='normal', source=None, basis=None):
    # Existing native document header convention, not YAML or arbitrary tags.
    source = source or 'elm://section/section_11111111-1111-4111-8111-111111111111'
    basis = basis or {'explicit_fact':'explicit_statement', 'preference':'explicit_statement',
                      'observation':'direct_observation', 'hypothesis':'inference'}[kind]
    return note(project, text).replace('\n\n#',
        f'\nMemory lane: {lane}\nMemory kind: {kind}\nMemory sensitivity: {sensitivity}\nMemory source: {source}\nMemory basis: {basis}\n\n#', 1)


def decode(packet):
    payload = json.loads(packet.split('\n\nELM-DICT/1\n', 1)[1])
    result = []
    for stored in payload['sources']:
        record = {**payload['defaults'], **stored}
        for key, prefix in payload['prefixes'].items():
            record[key] = prefix + record[key]
        result.append(record)
    return result


def section_key(root, path, heading='Deployment'):
    import sqlite3
    from contextlib import closing
    with closing(sqlite3.connect(root/'.elm/index.sqlite')) as con:
        return con.execute('SELECT s.section_key FROM sections s JOIN documents d ON d.id=s.document_id WHERE d.path=? AND s.heading=?',
                           (path, heading)).fetchone()[0]


class TypedMemoryBoundary(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='elm-typed-', dir=os.environ['TMPDIR'])
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root, self.home = self.base/'store', self.base/'profile'
        self.home.mkdir()
        engine(self.root, 'init', '--project', 'orion')
        self.source = 'elm://section/' + section_key(self.root, '20_projects/orion/ACTIVE_CONTEXT.md', 'Current state')
        (self.root/'20_projects/orion/USER.md').write_text(
            typed_note('orion', USER_MARKER+' amber canary prefers concise answers.', source=self.source), encoding='utf-8')
        engine(self.root, 'sync')
        self.provider = ElmMemoryProvider()
        self.provider.save_config({'root':str(self.root), 'project':'orion', 'mode':'read-only',
                                   'budget_mode':'legacy-estimate', 'budget':1200}, str(self.home))
        self.provider.initialize('typed-unit', hermes_home=str(self.home))
        self.addCleanup(self.provider.shutdown)

    def typed(self, text, **kwargs):
        return typed_note('orion', text, source=kwargs.pop('source', self.source), **kwargs)

    def test_explicit_user_work_reference_intent_and_exact_read_metadata(self):
        for lane in ('work', 'reference'):
            (self.root/f'20_projects/orion/{lane}.md').write_text(
                self.typed(f'TYPED_{lane.upper()} amber canary concise source.', lane=lane,
                           kind='explicit_fact'), encoding='utf-8')
        engine(self.root, 'sync')
        for lane, purpose, marker in (('user','communication',USER_MARKER), ('work','task','TYPED_WORK'),
                                       ('reference','task','TYPED_REFERENCE')):
            with self.subTest(lane=lane):
                intent = {'lane':lane, 'purpose':purpose}
                result = json.loads(self.provider.handle_tool_call('elm_context', {'query':'amber canary concise', **intent}))
                self.assertIn('packet', result, result)
                records = decode(result['packet'])
                selected = next(r for r in records if marker in r.get('text',''))
                self.assertEqual(lane, selected['memory']['lane'])
                self.assertEqual('explicit_statement', selected['memory']['basis'])
                self.assertNotEqual('project_document', selected['authority'])
                for other in (USER_MARKER, 'TYPED_WORK', 'TYPED_REFERENCE'):
                    if other != marker:
                        self.assertNotIn(other, result['packet'])
                direct = json.loads(self.provider.handle_tool_call('elm_read', {'section':selected['source'], **intent}))
                self.assertEqual(selected['text'], direct['text'])
                self.assertEqual(selected['memory'], direct['memory'])
                self.assertEqual(selected['authority'], direct['authority'])
                # Direct expansion is stateless: the preceding user query is no grant.
                if lane != 'work':
                    refused = json.loads(self.provider.handle_tool_call('elm_read', {'section':selected['source']}))
                    self.assertIn('error', refused)

    def test_default_work_packet_and_direct_read_exclude_typed_user(self):
        packet = json.loads(self.provider.handle_tool_call('elm_context', {'query':'amber canary concise'}))
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(self.root/'.elm/index.sqlite')) as con:
            section = con.execute("SELECT s.section_key FROM sections s JOIN documents d ON d.id=s.document_id WHERE d.path='20_projects/orion/USER.md' AND s.heading='Deployment'").fetchone()[0]
        direct = json.loads(self.provider.handle_tool_call('elm_read', {'section':section}))
        evidence = {'packet':packet, 'direct':direct}
        print(json.dumps({'boundary_probe':evidence}, ensure_ascii=False))
        # Each seam is checked, even if the other failed. No last-query state.
        with self.subTest(boundary='work_packet'):
            self.assertNotIn(USER_MARKER, json.dumps(packet))
        with self.subTest(boundary='direct_read'):
            self.assertIn('error', direct)
            self.assertNotIn(USER_MARKER, json.dumps(direct))

    def test_hypothesis_is_uncertain_communication_only_and_cannot_be_redeclared_fact(self):
        path = self.root/'20_projects/orion/HYPOTHESIS.md'
        path.write_text(self.typed('HYPOTHESIS_FIXTURE amber canary may benefit from numbered steps.',
                                   kind='hypothesis').replace('Status: active', 'Status: accepted'), encoding='utf-8')
        engine(self.root, 'sync')
        intent = {'lane':'user', 'purpose':'communication'}
        outline = engine(self.root, 'outline', '20_projects/orion/HYPOTHESIS.md', '--project', 'orion',
                         '--memory-lane', 'user', '--memory-purpose', 'communication', '--no-sync')
        source = next(s['section_key'] for s in outline['sections'] if s['heading']=='Deployment')
        direct = json.loads(self.provider.handle_tool_call('elm_read', {'section':source, **intent}))
        self.assertEqual('unverified_hypothesis', direct['authority'], direct)
        result = json.loads(self.provider.handle_tool_call('elm_context', {'query':'HYPOTHESIS_FIXTURE', **intent}))
        self.assertIn('packet', result, result)
        record = next(r for r in decode(result['packet']) if 'HYPOTHESIS_FIXTURE' in r.get('text',''))
        direct = json.loads(self.provider.handle_tool_call('elm_read', {'section':record['source'], **intent}))
        for value in (record, direct):
            with self.subTest(surface='packet' if value is record else 'direct'):
                self.assertEqual('unverified_hypothesis', value['authority'])
                self.assertEqual('communication_only_uncertain', value['memory']['restriction'])
                self.assertEqual('inference', value['memory']['basis'])
                self.assertEqual('hypothesis', value['memory']['kind'])

    def test_inferred_basis_cannot_be_encoded_as_an_explicit_fact(self):
        path = self.root/'20_projects/orion/MISLEADING.md'
        path.write_text(self.typed('MISLEADING_FACT amber canary', kind='explicit_fact', basis='inference'), encoding='utf-8')
        synced = engine(self.root, 'sync')
        self.assertTrue(synced['errors'], 'Inference mislabeled explicit_fact must fail ingestion')
        refused = json.loads(self.provider.handle_tool_call('elm_context', {'query':'MISLEADING_FACT','lane':'user','purpose':'communication'}))
        self.assertIn('error', refused)

    def test_declared_sensitive_inference_is_withheld_but_self_report_is_not_medical_verification(self):
        for filename, kind, text in (
            ('INFERRED_HEALTH', 'hypothesis', 'INFERRED_HEALTH amber canary fictional diagnosis inferred by AI.'),
            ('SELF_REPORT', 'explicit_fact', 'SELF_REPORT amber canary fictional user reports a health condition.')):
            (self.root/f'20_projects/orion/{filename}.md').write_text(
                self.typed(text, kind=kind, sensitivity='sensitive_health'), encoding='utf-8')
        engine(self.root, 'sync')
        intent = {'lane':'user', 'purpose':'communication'}
        packet = json.loads(self.provider.handle_tool_call('elm_context', {'query':'amber canary fictional', **intent}))
        self.assertIn('packet', packet, packet)
        with self.subTest(boundary='context'):
            self.assertNotIn('INFERRED_HEALTH', packet['packet'])
        guessed = section_key(self.root, '20_projects/orion/INFERRED_HEALTH.md')
        direct = json.loads(self.provider.handle_tool_call('elm_read', {'section':guessed, **intent}))
        with self.subTest(boundary='direct'):
            self.assertIn('error', direct)
        record = next(r for r in decode(packet['packet']) if 'SELF_REPORT' in r.get('text',''))
        self.assertEqual('declared_self_report_not_medically_verified', record['authority'])
        self.assertEqual('explicit_statement', record['memory']['basis'])

    def test_typed_metadata_survives_legacy_fallback_summary_and_manifest(self):
        from elm_plugin.measured_context import packing_modules
        context, _ = packing_modules()
        for summary, expected in (('Small declared source summary.', 'source_summary'), ('', 'relevant_source_manifest')):
            with self.subTest(representation=expected):
                text = self.typed('FALLBACK amber ' * 4000, kind='hypothesis')
                text = text.replace('Summary: Deployment choices for orion.', 'Summary: '+summary)
                (self.root/'20_projects/orion/FALLBACK.md').write_text(text, encoding='utf-8')
                engine(self.root, 'sync')
                raw = engine(self.root, 'context', 'FALLBACK', '--project','orion', '--memory-lane','user',
                             '--memory-purpose','communication', '--budget','700','--no-sync','--no-trace','--packing-input')
                baseline = context.build_context_packet('FALLBACK', raw['candidates'], 700, scope=raw['scope'])
                record = next(s for s in baseline['sources'] if s['path'].endswith('FALLBACK.md'))
                self.assertEqual(expected, record['representation_class'])
                self.assertIn('memory', record, record)
                self.assertEqual('inference', record['memory']['basis'])
                self.assertIn('communication_only_uncertain', baseline['packet'])
                self.assertIn('"basis": "inference"', baseline['packet'])

    def test_missing_or_foreign_declared_evidence_is_not_delivered(self):
        path = self.root/'20_projects/orion/UNLINKED.md'
        path.write_text(self.typed('UNLINKEDPROOF invented source', kind='hypothesis',
                                   source='elm://section/section_11111111-1111-4111-8111-111111111111'), encoding='utf-8')
        engine(self.root, 'sync')
        intent = {'lane':'user','purpose':'communication'}
        packet = json.loads(self.provider.handle_tool_call('elm_context', {'query':'UNLINKEDPROOF', **intent}))
        self.assertIn('packet', packet)
        self.assertNotIn('UNLINKEDPROOF', packet['packet'])
        direct = json.loads(self.provider.handle_tool_call('elm_read',
                            {'section':section_key(self.root, '20_projects/orion/UNLINKED.md'), **intent}))
        self.assertIn('error', direct)
        foreign=self.root/'20_projects/lighthouse';foreign.mkdir()
        (foreign/'SOURCE.md').write_text(note('lighthouse','Concrete unrelated-project evidence.'),encoding='utf-8')
        engine(self.root,'sync')
        foreign_source='elm://section/'+section_key(self.root,'20_projects/lighthouse/SOURCE.md')
        path.write_text(self.typed('UNLINKEDPROOF foreign evidence',kind='hypothesis',source=foreign_source),encoding='utf-8')
        engine(self.root,'sync')
        packet=json.loads(self.provider.handle_tool_call('elm_context',{'query':'UNLINKEDPROOF',**intent}))
        self.assertNotIn('UNLINKEDPROOF',packet['packet'])
        self.assertIn('error',json.loads(self.provider.handle_tool_call('elm_read',
                        {'section':section_key(self.root,'20_projects/orion/UNLINKED.md'),**intent})))


class TypedMetadataValidation(unittest.TestCase):
    def test_invalid_reserved_declarations_never_fall_back_to_legacy(self):
        with tempfile.TemporaryDirectory(prefix='elm-typed-invalid-',dir=os.environ['TMPDIR']) as temp:
            root=Path(temp)/'store';engine(root,'init','--project','orion')
            valid=typed_note('orion','INVALID_DECLARATION_MARKER')
            variants=[valid.replace('Memory kind: preference','Memory kind: diagnosis'),
                      valid.replace('Memory lane: user','Memory lane: psychology'),
                      valid.replace('Memory basis: explicit_statement','Memory basis: medically_verified'),
                      valid.replace('Memory sensitivity: normal','Memory sensitivity: anything'),
                      valid.replace('Memory source: elm://section/','Memory source: https://example.invalid/'),
                      valid.replace('Memory kind: preference\n',''),
                      valid.replace('Memory kind: preference','Memory kind: preference\nMemory kind: explicit_fact'),
                      note('orion','INVALID_DECLARATION_MARKER').replace('\n\n#','\nMemory owner: anyone\n\n#',1),
                      valid.replace('Memory lane: user','Unknown header: barrier\nMemory lane: user'),
                      '\n'*81+valid]
            for i,text in enumerate(variants):
                with self.subTest(case=i):
                    path=root/'20_projects/orion/INVALID.md';path.write_text(text,encoding='utf-8')
                    result=engine(root,'sync')
                    self.assertTrue(result['errors'],result)
                    # New invalid document must not be indexed as unclassified.
                    from contextlib import closing
                    import sqlite3
                    with closing(sqlite3.connect(root/'.elm/index.sqlite')) as con:
                        self.assertEqual(0,con.execute("SELECT count(*) FROM documents WHERE path='20_projects/orion/INVALID.md'").fetchone()[0])

    def test_schema_five_projection_is_refused_until_sync_reparses_typed_declarations(self):
        from contextlib import closing
        import sqlite3
        with tempfile.TemporaryDirectory(prefix='elm-typed-migrate-',dir=os.environ['TMPDIR']) as temp:
            root=Path(temp)/'store';engine(root,'init','--project','orion')
            source='elm://section/'+section_key(root,'20_projects/orion/ACTIVE_CONTEXT.md','Current state')
            (root/'20_projects/orion/USER.md').write_text(typed_note('orion','MIGRATION_PERSONAL_MARKER',source=source),encoding='utf-8')
            engine(root,'sync')
            with closing(sqlite3.connect(root/'.elm/index.sqlite')) as con:
                with con:
                    con.execute("UPDATE elm_meta SET value='5' WHERE key='index_schema_version'")
                    con.execute("DELETE FROM properties WHERE key LIKE 'memory_%'")
            self.assertFalse(engine(root,'status')['healthy'])
            self.assertEqual([],engine(root,'sync')['errors'])
            work=engine(root,'context','MIGRATION_PERSONAL_MARKER','--project','orion','--budget','1200','--no-sync','--no-trace')
            self.assertNotIn('MIGRATION_PERSONAL_MARKER',work['packet'])
            user=engine(root,'context','MIGRATION_PERSONAL_MARKER','--project','orion','--memory-lane','user','--memory-purpose','communication','--budget','1200','--no-sync','--no-trace')
            self.assertIn('MIGRATION_PERSONAL_MARKER',user['packet'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
