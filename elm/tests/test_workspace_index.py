"""Real subprocess enforcement fixtures, not model-classification evaluation."""
from contextlib import closing
from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN))
from elm_plugin.engine import run_engine, ElmError


def record(id='rec_alpha', *, scope='workspace:a', text='Amber canary requires a signed rollback.',
           domain='work', kind='explicit_fact', basis='explicit_statement', **fields):
    return dict(id=id, revision=1, scope_id=scope, title='Fictional release '+id, text=text,
                domain=domain, kind=kind, basis=basis, topic='facts',
                sources=[{'ref':'fixture:invented-conversation', 'quote':'Invented human statement', 'revision':1}],
                state='approved', dependencies=[], sensitive=False, **fields)


def key(root, path, heading):
    with closing(sqlite3.connect(root/'.elm/index.sqlite')) as con:
        return con.execute('SELECT s.section_key FROM sections s JOIN documents d ON d.id=s.document_id WHERE d.path=? AND s.heading=?',
                           (path, heading)).fetchone()[0]


def typed(text, lane, kind, basis, source, sensitivity='normal'):
    return (f'Title: Fictional {kind}\nScope: fixture only\nTags: fixture\nStatus: active\n'
            f'Summary: Fictional evidence only.\nMemory lane: {lane}\nMemory kind: {kind}\n'
            f'Memory sensitivity: {sensitivity}\nMemory source: {source}\nMemory basis: {basis}\n\n'
            f'# Evidence\n\n{text}\n')


class EngineReview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='review-', dir=os.environ['TMPDIR'])
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)/'home'; self.home.mkdir()
        self.root = Path(self.tmp.name)/'root'
        self.run_engine('init', '--project', 'fixture')
        self.source = 'elm://section/'+key(self.root, '20_projects/fixture/ACTIVE_CONTEXT.md', 'Current state')

    def run_engine(self, *args, **kwargs):
        return run_engine(self.home, self.root, *args, **kwargs)

    def test_review_context_fallback_and_exact_read_keep_uncertain_original_kinds(self):
        sys.path.insert(0,str(PLUGIN/'engine'))
        from elm_memory.context import build_context_packet
        for lane,kind in [('work','interpretation'),('reference','summary')]:
            for summary in ['Fictional evidence only.','']:
                with self.subTest(lane=lane,kind=kind,summary=bool(summary)):
                    path=self.root/'20_projects/fixture/LONG.md'
                    path.write_text(typed('FALLBACK_REVIEW amber '*4000,lane,kind,'inference',self.source).replace('Summary: Fictional evidence only.','Summary: '+summary),encoding='utf-8')
                    self.assertFalse(self.run_engine('sync')['errors'])
                    raw=self.run_engine('context','--project','fixture','--memory-lane',lane,'--memory-purpose','review',
                                        '--budget','700','--no-sync','--no-trace','--packing-input',task='FALLBACK_REVIEW')
                    packet=build_context_packet('FALLBACK_REVIEW',raw['candidates'],700,scope=raw['scope'])
                    selected=next(r for r in packet['sources'] if r['path'].endswith('LONG.md'))
                    self.assertEqual(kind,selected['memory']['kind'])
                    self.assertEqual('inference',selected['memory']['basis'])
                    self.assertEqual('untrusted_evidence_only_uncertain',selected['memory']['restriction'])
                    self.assertEqual('source_summary' if summary else 'relevant_source_manifest',selected['representation_class'])
                    self.assertIn('untrusted_evidence_only_uncertain',packet['packet'])
                    section=key(self.root,'20_projects/fixture/LONG.md','Evidence')
                    with self.assertRaises(ElmError):
                        self.run_engine('read',section,'--project','fixture','--memory-lane',lane,'--memory-purpose','task')

    def test_sensitive_inferences_remain_denied_and_user_review_is_not_a_grant(self):
        for lane in ['work','reference','user']:
            (self.root/f'20_projects/fixture/{lane}.md').write_text(typed('HEALTH_INFERENCE_EXCLUDED amber',lane,'hypothesis','inference',self.source,'sensitive_health'),encoding='utf-8')
        self.assertFalse(self.run_engine('sync')['errors'])
        for lane,purpose in [('work','review'),('reference','review'),('work','task'),('user','communication')]:
            with self.subTest(lane=lane,purpose=purpose):
                raw=self.run_engine('context','--project','fixture','--memory-lane',lane,'--memory-purpose',purpose,
                                    '--budget','1200','--no-sync','--no-trace',task='HEALTH_INFERENCE_EXCLUDED')
                self.assertNotIn('HEALTH_INFERENCE_EXCLUDED',raw['packet'])
                self.assertFalse(any(s['path'].endswith(('/work.md','/reference.md','/user.md')) for s in raw['sources']))
                section=key(self.root,f'20_projects/fixture/{lane}.md','Evidence')
                with self.assertRaises(ElmError): self.run_engine('read',section,'--project','fixture','--memory-lane',lane,'--memory-purpose',purpose)
        with self.assertRaises(ElmError):
            self.run_engine('search','--project','fixture','--memory-lane','user','--memory-purpose','review',task='amber')
        with self.assertRaises(ElmError):
            self.run_engine('search','--memory-lane','work','--memory-purpose','review',task='amber')

    def test_explicit_review_retrieves_original_inference_labels_and_preserves_legacy_denials(self):
        path = self.root/'20_projects/fixture/INTERPRETATION.md'
        path.write_text(typed('AMBER_REVIEW may benefit from a rollback rehearsal.', 'work', 'hypothesis', 'inference', self.source), encoding='utf-8')
        self.assertFalse(self.run_engine('sync')['errors'])
        section = key(self.root, '20_projects/fixture/INTERPRETATION.md', 'Evidence')
        for lane, purpose in [('work','task'), ('user','communication'), ('reference','task')]:
            result = self.run_engine('search', '--project','fixture','--memory-lane',lane,'--memory-purpose',purpose,'--no-sync',task='AMBER_REVIEW')
            self.assertEqual([], result['results'])
        result = self.run_engine('search', '--project','fixture','--memory-lane','work','--memory-purpose','review','--no-sync',task='AMBER_REVIEW')
        self.assertEqual(section, result['results'][0]['section_key'])
        direct = self.run_engine('read', section, '--project','fixture','--memory-lane','work','--memory-purpose','review')
        self.assertEqual('inference', direct['memory']['basis'])
        self.assertEqual('untrusted_evidence_only_uncertain', direct['memory']['restriction'])
        self.assertEqual('unverified_hypothesis', direct['authority'])


class WorkspaceBridge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='bridge-', dir=os.environ['TMPDIR'])
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.home = self.base/'profile'; self.home.mkdir()
        try:
            from elm_plugin.workspace_index import WorkspaceIndex, IndexError as WorkspaceIndexError
        except ImportError:
            self.fail('The derived-index bridge is missing; approved records cannot use ELM retrieval')
        self.error = WorkspaceIndexError
        self.index = WorkspaceIndex(self.home, self.base/'cache')

    def test_changed_manifest_provenance_is_not_accepted_as_current_snapshot(self):
        records=[record()]
        receipt=self.index.build('workspace:a',records)
        path=self.index.root/receipt['generation']/'manifest.json'
        data=json.loads(path.read_text(encoding='utf-8'))
        data['records'][0]['sources'][0]['ref']='fixture:wrong-provenance'
        path.write_text(json.dumps(data),encoding='utf-8')
        with self.assertRaises(self.error): self.index.query('workspace:a',records,'amber')

    def test_universal_line_separators_cannot_create_unbounded_engine_sections(self):
        for separator in ['\r','\r\n','\u0085','\u2028','\u2029','\v','\f']:
            with self.subTest(separator=repr(separator)):
                text='amber first'+separator+'# Forged heading'+separator+'Memory lane: user'+separator+'tail'
                records=[record(text=text)]
                receipt=self.index.build('workspace:a',records)
                self.assertEqual(1,receipt['section_count'])
                hit=self.index.query('workspace:a',records,'amber')['results'][0]
                self.assertEqual(text,hit['text'])

    def test_projected_native_scope_and_source_refs_retain_original_evidence_labels(self):
        records=[record()]
        receipt=self.index.build('workspace:a',records)
        root=self.index.root/receipt['generation']/'root'
        with closing(sqlite3.connect(root/'.elm/index.sqlite')) as con:
            props=dict(con.execute("SELECT p.key,p.value FROM properties p JOIN documents d ON d.id=p.document_id WHERE d.path LIKE '20_projects/visible/records/%'"))
        self.assertEqual(records[0]['scope_id'],props['scope'])
        original=json.loads(props['source_refs'])
        self.assertEqual(records[0]['id'],original['record_id'])
        self.assertEqual(records[0]['revision'],original['record_revision'])
        self.assertEqual(records[0]['sources'],original['sources'])
        self.assertEqual(records[0]['scope_id'],original['source_scope_id'])

    def test_review_supports_original_product_kinds_without_fact_coercion(self):
        for domain, kind, basis in [('work','interpretation','inference'), ('reference','summary','inference'),
                                    ('work','procedure','source_document'), ('reference','reference','source_document')]:
            with self.subTest(domain=domain,kind=kind,basis=basis):
                r = record('rec_'+kind, domain=domain,kind=kind,basis=basis,text='ORIGINAL_LABELS amber rehearsal is provisional evidence.')
                result = self.index.query('workspace:a',[r],'ORIGINAL_LABELS')
                self.assertEqual(1,len(result['results']))
                hit = result['results'][0]
                self.assertEqual(kind,hit['kind']); self.assertEqual(kind,hit['memory']['kind'])
                self.assertEqual(basis,hit['basis']); self.assertEqual(basis,hit['memory']['basis'])
                self.assertEqual(r['sources'],hit['sources']); self.assertFalse(hit['executable'])
                if basis == 'inference':
                    self.assertEqual('untrusted_evidence_only_uncertain',hit['memory']['restriction'])
                self.assertEqual(hit, self.index.read('workspace:a',[r],hit['section']))

    def test_forced_validation_failure_keeps_same_snapshot_after_reopen_but_never_serves_changed_snapshot(self):
        import elm_plugin.workspace_index as module
        original = [record()]
        receipt = self.index.build('workspace:a',original)
        old_root = self.index.root/receipt['generation']/'root'
        real = module.run_engine
        failures = []
        def break_staging(home,root,*args,**kwargs):
            if args[0] == 'status' and root != old_root:
                # An actual invalid SQLite projection, not a fake status result.
                with closing(sqlite3.connect(root/'.elm/index.sqlite')) as con:
                    with con: con.execute("UPDATE elm_meta SET value='0' WHERE key='index_schema_version'")
                actual = real(home,root,*args,**kwargs)
                failures.append(actual)
                return actual
            return real(home,root,*args,**kwargs)
        with patch.object(module,'run_engine',side_effect=break_staging):
            with self.assertRaises(self.error): self.index.build('workspace:a',original,force=True)
        self.assertFalse(failures[0]['healthy'])
        reopened = module.WorkspaceIndex(self.home,self.base/'cache')
        self.assertEqual(receipt['generation'],reopened.query('workspace:a',original,'amber')['generation'])
        import subprocess
        child_code = ('import json,sys,os; from pathlib import Path; '
                      'sys.path.insert(0,sys.argv[1]); from elm_plugin.workspace_index import WorkspaceIndex; '
                      'a=json.load(sys.stdin); x=WorkspaceIndex(Path(a["home"]),Path(a["cache"])); '
                      'print(json.dumps(dict(pid=os.getpid(),result=x.query(a["scope"],a["records"],"amber"))))')
        child=subprocess.run([sys.executable,'-I','-S','-B','-c',child_code,str(PLUGIN)],
                             input=json.dumps(dict(home=str(self.home),cache=str(self.base/'cache'),scope='workspace:a',records=original)),
                             text=True,encoding='utf-8',capture_output=True,timeout=30,cwd=self.base)
        self.assertEqual(0,child.returncode,child.stderr)
        independent=json.loads(child.stdout)
        self.assertNotEqual(os.getpid(),independent['pid'])
        self.assertEqual(receipt['generation'],independent['result']['generation'])
        self.assertEqual(original[0]['text'],independent['result']['results'][0]['text'])
        changed = deepcopy(original); changed[0]['revision']=2; changed[0]['text']='CORRECTED sapphire release.'
        with patch.object(module,'run_engine',side_effect=break_staging):
            with self.assertRaises(self.error): reopened.query('workspace:a',changed,'amber')
        self.assertEqual(receipt['generation'],reopened.status('workspace:a')['generation'])
        status = reopened.status('workspace:a')
        self.assertEqual(3,len(status['held_paths']))
        print(json.dumps({'injected_real_validation_failures':failures,'held_generation_status':status}))

    def test_wrong_scope_revocation_correction_and_deleted_record_locators_are_refused(self):
        original=[record()]
        hit=self.index.query('workspace:a',original,'amber')['results'][0]
        with self.assertRaises(self.error): self.index.read('chat:other',[],hit['section'])
        changed=deepcopy(original); changed[0]['revision']=2; changed[0]['text']='CORRECTED sapphire release.'
        with self.assertRaises(self.error): self.index.read('workspace:a',changed,hit['section'])
        fresh=self.index.query('workspace:a',changed,'CORRECTED')['results'][0]
        self.assertEqual(2,fresh['record_revision']); self.assertNotIn('Amber',fresh['text'])
        with self.assertRaises(self.error): self.index.read('workspace:a',[],fresh['section'])
        self.assertEqual([],self.index.query('workspace:a',[],'CORRECTED')['results'])
        for locator in ['20_projects/visible/records/a.md','1','--root','elm://section/section_11111111-1111-4111-8111-111111111111']:
            with self.assertRaises(self.error): self.index.read('workspace:a',original,locator)

    def test_large_original_has_bounded_exact_expandable_sections(self):
        text=('amber 🟡 canary\n# source heading\nMemory lane: user\n' * 450)+'TAIL_EXACT'
        records=[record(text=text)]
        result=self.index.query('workspace:a',records,'amber',limit=2)
        self.assertEqual(2,len(result['results']))
        for hit in result['results']:
            self.assertLessEqual(len(hit['text']),4000)
            self.assertEqual('exact_source_section',hit['representation_class'])
        # Every remaining chunk must be discoverable through the public result,
        # not a private manifest path or guessed engine section ID.
        self.assertIn('record_sections',result['results'][0])
        chunks=[]
        for binding in result['results'][0]['record_sections']:
            hit=self.index.read('workspace:a',records,binding['section'])
            chunks.append(hit['text'])
            self.assertEqual(records[0]['sources'],hit['sources'])
        self.assertEqual(text,''.join(chunks))

    def test_purge_preserves_unrelated_files_and_reports_real_windows_held_copy(self):
        import ctypes
        self.index.build('workspace:a',[record()])
        unrelated=self.base/'cache'/'unrelated.txt'; unrelated.write_text('keep',encoding='utf-8')
        selected=self.index._load('workspace:a')[0]
        path=next((selected/'root'/'20_projects/visible/records').glob('*.md'))
        if os.name != 'nt': self.skipTest('This actual held-file assertion is Windows-specific')
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p]
        kernel.CreateFileW.restype=ctypes.c_void_p
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        handle=kernel.CreateFileW(str(path),0x80000000,1,None,3,0,None)  # no FILE_SHARE_DELETE
        self.assertNotEqual(ctypes.c_void_p(-1).value,handle)
        try:
            receipt=self.index.purge()
            self.assertFalse(receipt['removed']); self.assertTrue(receipt['held_paths'])
            self.assertTrue(path.exists()); self.assertTrue(receipt['copies_retained'])
            print(json.dumps({'actual_windows_held_purge':receipt}))
        finally: kernel.CloseHandle(handle)
        retry=self.index.purge()
        self.assertTrue(retry['removed']); self.assertFalse(retry['copies_retained'])
        self.assertFalse(path.exists()); self.assertEqual('keep',unrelated.read_text(encoding='utf-8'))

    def test_generic_sensitive_flag_is_not_reclassified_as_health_or_delivered(self):
        r=record('rec_sensitive_card',domain='user',kind='preference',basis='explicit_statement',text='SENSITIVE_CARD Please use short paragraphs.')
        r.update(topic='communication',sensitive=True)
        result=self.index.query('workspace:a',[r],'SENSITIVE_CARD')
        self.assertEqual([],result['results'])
        self.assertEqual(1,result['withheld_record_count'])

    def test_snapshot_validation_communication_card_and_sensitive_withholding(self):
        for changes in [dict(state='pending'),dict(state='invalidated'),dict(basis='inference'),dict(sources=[]),dict(revision=True)]:
            r=record(); r.update(changes)
            with self.assertRaises(self.error): self.index.query('workspace:a',[r],'amber')
        for q in ['', 'x'*2049, None]:
            with self.assertRaises(self.error): self.index.query('workspace:a',[record()],q)
        r=record('rec_preference',domain='user',kind='preference',basis='explicit_statement',text='CARD_COMMUNICATION Please use short paragraphs.')
        r['topic']='communication';r['scope_id']='personal:fixture'
        result=self.index.query('workspace:a',[r],'CARD_COMMUNICATION')
        self.assertEqual('personal:fixture',result['results'][0]['source_scope_id'])
        self.assertEqual('communication_only',result['results'][0]['memory']['restriction'])
        sensitive=record('rec_sensitive',text='SENSITIVE_EXCLUDED amber',kind='interpretation',basis='inference')
        sensitive['sensitive']=True
        self.assertEqual([],self.index.query('workspace:a',[sensitive],'SENSITIVE_EXCLUDED')['results'])

    def test_upgrade_selects_new_generation_and_refuses_unowned_cache(self):
        import elm_plugin.workspace_index as module
        first=self.index.build('workspace:a',[record()])
        with patch.object(module.WorkspaceIndex,'_engine_version',return_value='qualified-next-engine'):
            self.assertEqual('upgrade_required',self.index.status('workspace:a')['state'])
            second=self.index.build('workspace:a',[record()])
            self.assertNotEqual(first['generation'],second['generation'])
            self.assertEqual('qualified-next-engine',second['engine_sha256'])
        bad=self.base/'unrelated-cache'/'elm-workspace-index';bad.mkdir(parents=True)
        (bad/'unrelated.txt').write_text('keep',encoding='utf-8')
        with self.assertRaises(self.error): module.WorkspaceIndex(self.home,bad.parent).build('workspace:a',[record()])
        self.assertEqual('keep',(bad/'unrelated.txt').read_text(encoding='utf-8'))
        with self.assertRaises(self.error): module.WorkspaceIndex(self.base/'different-profile',self.base/'cache').purge()

    def test_real_engine_query_and_exact_read_preserve_scoped_provenance(self):
        records = [record(), record('rec_user', domain='user', kind='preference', basis='explicit_statement',
                                   text='PRIVATE_DISTRACTOR amber canary rollback '*30)]
        result = self.index.query('workspace:a', records, 'amber canary rollback')
        self.assertTrue(result['results'], result)
        self.assertNotIn('PRIVATE_DISTRACTOR', json.dumps(result))
        hit = result['results'][0]
        for name, value in [('record_id','rec_alpha'), ('record_revision',1), ('domain','work'),
                            ('source_scope_id','workspace:a'), ('kind','explicit_fact'), ('basis','explicit_statement')]:
            self.assertEqual(value, hit[name])
        self.assertEqual(records[0]['sources'], hit['sources'])
        self.assertEqual(records[0]['text'], hit['text'])
        exact = self.index.read('workspace:a', records, hit['section'])
        self.assertEqual(hit['text'], exact['text'])
        self.assertEqual(hit['sources'], exact['sources'])
        self.assertEqual(result['generation'], exact['generation'])
        self.assertEqual(result['generation'], self.index.build('workspace:a', list(reversed(records)))['generation'])
        print(json.dumps({'real_bridge_example':result}, ensure_ascii=False))


if __name__ == '__main__':
    unittest.main(verbosity=2)
