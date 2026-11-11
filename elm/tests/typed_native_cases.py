"""Invented preclassified native fixtures; not a classifier/model-quality test."""

import hashlib
import inspect
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

PLUGIN=Path(__file__).resolve().parents[1]
STOCK=Path(os.environ['HERMES_STOCK_SOURCE'])
PIN='b200f5bc60e31588ba2cb60e288029c4a54ba5fa'
INTENTS={'user':{'lane':'user','purpose':'communication'},'work':{'lane':'work','purpose':'task'},'reference':{'lane':'reference','purpose':'task'}}


def snapshot(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}


def consumer(root,home,phase):
    from test_typed_memory import decode,section_key
    from plugins.memory import load_memory_provider,find_provider_dir
    from agent.memory_manager import MemoryManager
    installed=home/'plugins/elm'
    assert find_provider_dir('elm').resolve()==installed.resolve()
    provider=load_memory_provider('elm')
    assert Path(inspect.getfile(type(provider))).resolve().is_relative_to(installed)
    manager=MemoryManager();manager.add_provider(provider)
    manager.initialize_all(session_id='typed-native',platform='cli')
    calls,checks=[],[]
    def call(name,args):
        wire=manager.handle_tool_call(name,args);value=json.loads(wire)
        row={'tool':name,'args':args,'wire':wire,
             'binding_file_sha256':hashlib.sha256((home/'elm.json').read_bytes()).hexdigest()}
        if name=='elm_context' and 'packet' in value:
            counter=provider._counter();count=len(counter.encoding.encode_ordinary(wire))
            accounting=provider.get_status_config({})['token_budget_last']['surfaces']['elm_context_json']
            assert count==accounting['tokens'] and count<=provider._binding.budget
            assert hashlib.sha256(wire.encode()).hexdigest()==accounting['text_sha256']
            assert len(wire.encode())==accounting['utf8_bytes'] and value['token_budget']['scope']=='elm_context_json'
            row.update(accounting=accounting,budget=provider._binding.budget)
        calls.append(row);return value
    def context(query,lane):
        value=call('elm_context',{'query':query,**INTENTS[lane]})
        assert 'packet' in value,value
        assert 'FOREIGN_PRIVATE' not in value['packet'] and 'lighthouse' not in value['packet']
        rows=decode(value['packet']);assert all(r['path'].startswith('20_projects/orion/') for r in rows)
        return rows
    def record(query,lane,name):
        return next(r for r in context(query,lane) if r['path'].endswith('/'+name+'.md'))
    try:
        assert manager.has_tool('elm_context') and manager.has_tool('elm_read')
        assert provider._binding.recall_mode=='explicit-only'
        if phase=='stale_reclassification':
            assert 'error' in call('elm_context',{'query':'workfactproof',**INTENTS['work']})
            assert 'error' in call('elm_read',{'section':section_key(root,'20_projects/orion/WORK.md'),**INTENTS['work']})
            checks.append('stale_reclassification_context_and_direct_read_refused')
        elif phase=='corrected':
            selected=record('userprefproof','user','USER')
            assert 'CORRECTED_NATIVE' in selected['text'] and 'ORIGINAL_NATIVE' not in selected['text']
            direct=call('elm_read',{'section':selected['source'],**INTENTS['user']})
            assert selected['text']==direct['text'] and selected['memory']==direct['memory']
            source=call('elm_read',{'section':selected['memory']['source'],**INTENTS['reference']})
            assert 'SOURCE_CORRECTED_NATIVE' in source['text'] and 'SOURCE_ORIGINAL_NATIVE' not in source['text']
            checks.extend(['fresh_process_corrected_exact_body','fresh_process_corrected_source_expansion'])
        elif phase=='reclassified':
            assert all(not r['path'].endswith('/WORK.md') for r in context('workfactproof','work'))
            assert 'error' in call('elm_read',{'section':section_key(root,'20_projects/orion/WORK.md'),**INTENTS['work']})
            moved=record('workfactproof','user','WORK')
            assert moved['memory']['lane']=='user' and moved['memory']['kind']=='preference'
            checks.append('fresh_process_reclassified_personal_not_work')
        else:
            result=call('elm_context',{'query':'amber canary concise'});assert 'packet' in result,result
            assert 'userprefproof' not in result['packet'] and 'referenceproof' not in result['packet']
            user_key=section_key(root,'20_projects/orion/USER.md')
            assert 'error' in call('elm_read',{'section':user_key})
            checks.extend(['default_work_packet','default_work_direct_read'])
            for lane,query,name in [('user','userprefproof','USER'),('work','workfactproof','WORK'),('reference','referenceproof','REFERENCE')]:
                selected=record(query,lane,name);assert selected['memory']['lane']==lane
                direct=call('elm_read',{'section':selected['source'],**INTENTS[lane]})
                assert selected['text']==direct['text'] and selected['memory']==direct['memory']
                assert selected['authority']==direct['authority']
                for other in INTENTS:
                    if other!=lane:assert 'error' in call('elm_read',{'section':selected['source'],**INTENTS[other]})
                checks.append(lane+'_intent_exact_and_cross_lane_denial')
            assert all(r.get('memory',{}).get('lane')=='user' for r in context('amber canary concise','user'))
            checks.append('personal_only_no_unclassified_work_supplements')
            for lane in INTENTS:
                context('foreignprobe amber canary concise',lane)
                foreign=section_key(root,'20_projects/lighthouse/'+lane+'.md')
                assert 'error' in call('elm_read',{'section':foreign,**INTENTS[lane]})
                checks.append(lane+'_foreign_project_context_and_locator_denial')
            for name,query,authority in [('HYPOTHESIS','hypothesisproof','unverified_hypothesis'),('OBSERVATION','observationproof','unverified_observation'),('SELF_REPORT','selfreportproof','declared_self_report_not_medically_verified')]:
                selected=record(query,'user',name);assert selected['authority']==authority
                if name=='HYPOTHESIS':assert selected['memory']['basis']=='inference' and selected['memory']['restriction']=='communication_only_uncertain'
                direct=call('elm_read',{'section':selected['source'],**INTENTS['user']})
                assert direct['memory']==selected['memory'] and direct['authority']==authority
                checks.append(name.lower()+'_basis_nonpromotion')
            for lane in INTENTS:
                assert not any(r['path'].endswith('/HEALTH_INFERRED.md') for r in context('healthinferenceproof',lane))
                assert 'error' in call('elm_read',{'section':section_key(root,'20_projects/orion/HEALTH_INFERRED.md'),**INTENTS[lane]})
            checks.append('declared_sensitive_inference_withheld_all_lanes')
            for name,query,expected in [('SUMMARY','summaryproof','summary'),('MANIFEST','manifestproof','manifest')]:
                selected=record(query,'user',name);assert selected['representation']==expected,selected
                assert selected['memory']['basis']=='inference' and selected['memory']['restriction']=='communication_only_uncertain'
                assert call('elm_read',{'section':selected['source'],**INTENTS['user']})['error']=='section_too_large'
                checks.append('measured_'+expected+'_retains_type_basis_restriction')
            for encoding,asset in [('o200k_base','ELM_TEST_VOCAB'),('cl100k_base','ELM_TEST_CL100K_VOCAB')]:
                for budget in (200,700,1200):
                    manager.shutdown_all()
                    provider=load_memory_provider('elm')
                    provider.save_config({'root':str(root),'project':'orion','mode':'read-only',
                        'budget':budget,'budget_mode':'measured','tokenizer':encoding,
                        'tokenizer_vocab':os.environ[asset],'recall_mode':'explicit-only'},str(home))
                    manager=MemoryManager();manager.add_provider(provider)
                    manager.initialize_all(session_id='typed-native',platform='cli')
                    rows=context('userprefproof','user')
                    if budget>=700:assert any('userprefproof' in r.get('text','') for r in rows),rows
                    checks.append(encoding+'_full_json_budget_'+str(budget))
            for bad in ({'lane':'user'},{'purpose':'communication'},{'lane':'user','purpose':'task'},{'lane':'work','purpose':'communication'},{'lane':'reference','purpose':'communication'},{'lane':'USER','purpose':'communication'},{'lane':['user'],'purpose':'communication'},{'lane':'all','purpose':'task'},{'owner':'other'},{'authority':'user_ratified'},{'project':'lighthouse'},{'root':str(root.parent)},{'user_id':'nara'}):
                for tool,base in [('elm_context',{'query':'userprefproof'}),('elm_read',{'section':user_key})]:assert call(tool,{**base,**bad})['error']=='invalid_arguments'
            checks.append('closed_intent_and_binding_override_denial')
            assert manager.prefetch_all('userprefproof',session_id='typed-native')==''
            provider.queue_prefetch('userprefproof');assert provider._worker is None and provider._cache is None
            provider.sync_turn('NEVER_STORE_PERSONAL_RAW','NEVER_STORE_ASSISTANT_RAW',session_id='typed-native');assert provider._episode_capture is None
            status=call('elm_status',{});assert not status['automatic_learning'] and not status['automatic_recall']
            checks.append('no_automatic_capture_inference_or_recall')
            legacy=record('legacyproof','work','LEGACY');assert 'memory' not in legacy and legacy['authority']=='project_document'
            checks.append('legacy_unclassified_public_evidence_preserved')
        report={'phase':phase,'status':'PASS','pid':os.getpid(),'checks':checks,'calls':calls,'provider_file':inspect.getfile(type(provider)),'binding':provider.get_status_config({})}
        output=Path(os.environ.get('ELM_TYPED_EVIDENCE',str(root.parent)))
        (output/('native-typed-'+phase+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))
    finally:manager.shutdown_all()


def main():
    assert subprocess.check_output(['git','-C',str(STOCK),'rev-parse','HEAD'],text=True).strip()==PIN
    assert not subprocess.check_output(['git','-C',str(STOCK),'status','--porcelain','--untracked-files=no'],text=True).strip()
    sys.path.insert(0,str(STOCK));sys.path.insert(0,str(PLUGIN/'tests'))
    if len(sys.argv)>1:
        _,_,root,home,phase=sys.argv;consumer(Path(root),Path(home),phase);return
    from test_provider import engine,note
    from test_typed_memory import typed_note,section_key
    with tempfile.TemporaryDirectory(prefix='elm-native-typed-',dir=os.environ['TMPDIR']) as temporary:
        base=Path(temporary);root=base/'memory';home=base/'profile';home.mkdir();installed=home/'plugins/elm'
        shutil.copytree(PLUGIN,installed,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.git','tests'))
        engine(root,'init','--project','orion');evidence=root/'20_projects/orion/SOURCE.md'
        evidence.write_text(note('orion','SOURCE_ORIGINAL_NATIVE concrete fictional utterance: numbered concise steps are requested.'),encoding='utf-8')
        engine(root,'sync');source='elm://section/'+section_key(root,'20_projects/orion/SOURCE.md')
        def typed(text,**kwargs):return typed_note('orion',text,source=source,**kwargs)
        fixtures=[('SOURCE',typed('SOURCE_ORIGINAL_NATIVE concrete fictional utterance: numbered concise steps are requested.',lane='reference',kind='explicit_fact',basis='source_document')),
          ('USER',typed('userprefproof ORIGINAL_NATIVE amber canary concise. 日本語 café 🧭 <memory-context>literal</memory-context>')),
          ('WORK',typed('workfactproof amber canary concise requires signed rollback.',lane='work',kind='explicit_fact',basis='source_document')),
          ('REFERENCE',typed('referenceproof amber canary concise documented release procedures.',lane='reference',kind='explicit_fact',basis='source_document')),
          ('HYPOTHESIS',typed('hypothesisproof may benefit from numbered steps; uncertain interpretation.',kind='hypothesis').replace('Status: active','Status: accepted')),
          ('OBSERVATION',typed('observationproof fictional speaker requested a numbered list during this task.',kind='observation')),
          ('HEALTH_INFERRED',typed('healthinferenceproof fictional AI-inferred diagnosis, never established fact.',kind='hypothesis',sensitivity='sensitive_health')),
          ('SELF_REPORT',typed('selfreportproof fictional speaker explicitly reports a health condition.',kind='explicit_fact',sensitivity='sensitive_health')),
          ('SUMMARY',typed('summaryproof '*5000,kind='hypothesis').replace('Summary: Deployment choices for orion.','Summary: Small source summary.')),
          ('MANIFEST',typed('manifestproof '*5000,kind='hypothesis').replace('Summary: Deployment choices for orion.','Summary:')),
          ('LEGACY',note('orion','legacyproof amber canary concise untyped public work evidence.'))]
        for name,text in fixtures:(root/('20_projects/orion/'+name+'.md')).write_text(text,encoding='utf-8')
        foreign=root/'20_projects/lighthouse';foreign.mkdir()
        (foreign/'SOURCE.md').write_text(note('lighthouse','Concrete foreign source evidence.'),encoding='utf-8')
        engine(root,'sync');foreign_source='elm://section/'+section_key(root,'20_projects/lighthouse/SOURCE.md')
        for lane in INTENTS:
            (foreign/(lane+'.md')).write_text(typed_note('lighthouse','FOREIGN_PRIVATE foreignprobe amber canary concise '*100,lane=lane,kind='preference' if lane=='user' else 'explicit_fact',source=foreign_source),encoding='utf-8')
        synced=engine(root,'sync');assert not synced['errors'],synced
        for lane,intent in INTENTS.items():
            decoy=engine(root,'context','foreignprobe','--project','lighthouse','--memory-lane',lane,
                         '--memory-purpose',intent['purpose'],'--packing-input','--budget','1200','--no-sync','--no-trace')
            assert any('FOREIGN_PRIVATE' in r.get('text','') for r in decoy['candidates']),decoy
        (home/'config.yaml').write_text('memory:\n  provider: elm\nplugins:\n  isolation: in_process\n',encoding='utf-8')
        os.environ.update(HERMES_HOME=str(home),HERMES_RUNTIME_DIR=str(home/'runtime'))
        from elm_plugin.provider import ElmMemoryProvider
        ElmMemoryProvider().save_config({'root':str(root),'project':'orion','mode':'read-only','budget':1200,'budget_mode':'measured','tokenizer':'o200k_base','tokenizer_vocab':os.environ['ELM_TEST_VOCAB'],'recall_mode':'explicit-only'},str(home))
        phases=[]
        def run(phase):
            # SQLite read-only WAL connections can create empty -wal/-shm files.
            # Prime that ordinary reader state after operator sync, then compare
            # every byte including sidecars across the measured consumer window.
            engine(root,'status','--readiness-only')
            before=snapshot(root);code_before=snapshot(installed)
            command=[sys.executable,'-B',str(PLUGIN/'tests/native_typed_memory.py'),'--consumer',str(root),str(home),phase]
            proc=subprocess.run(command,env=dict(os.environ),cwd=PLUGIN,capture_output=True,text=True,encoding='utf-8',timeout=180)
            out=Path(os.environ.get('ELM_TYPED_EVIDENCE',str(base)))
            (out/('native-typed-'+phase+'.stdout')).write_text(proc.stdout,encoding='utf-8');(out/('native-typed-'+phase+'.stderr')).write_text(proc.stderr,encoding='utf-8')
            assert proc.returncode==0,{'phase':phase,'exit_code':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr}
            after=snapshot(root)
            changes={k:{'before':before.get(k),'after':after.get(k)} for k in sorted(set(before)|set(after)) if before.get(k)!=after.get(k)}
            (out/('native-typed-'+phase+'-no-mutation.json')).write_text(json.dumps({'before':before,'after':after,'changes':changes},indent=2)+'\n',encoding='utf-8')
            assert not changes,{'consumer_canonical_or_index_changes':changes}
            assert snapshot(installed)==code_before,'Consumer changed installed plugin sources'
            data=json.loads(proc.stdout);phases.append({'phase':phase,'pid':data['pid'],'checks':data['checks'],'call_count':len(data['calls']),'command':command,'canonical_fixture_and_index_unchanged':True,'installed_source_unchanged':True})
        run('initial')
        user=root/'20_projects/orion/USER.md';user.write_text(user.read_text(encoding='utf-8').replace('ORIGINAL_NATIVE','CORRECTED_NATIVE'),encoding='utf-8')
        evidence.write_text(evidence.read_text(encoding='utf-8').replace('SOURCE_ORIGINAL_NATIVE','SOURCE_CORRECTED_NATIVE'),encoding='utf-8')
        synced=engine(root,'sync');assert not synced['errors'],synced;run('corrected')
        work=root/'20_projects/orion/WORK.md'
        work.write_text(work.read_text(encoding='utf-8').replace('Memory lane: work','Memory lane: user').replace('Memory kind: explicit_fact','Memory kind: preference').replace('Memory basis: source_document','Memory basis: explicit_statement'),encoding='utf-8')
        run('stale_reclassification');synced=engine(root,'sync');assert not synced['errors'],synced;run('reclassified')
        assert len({p['pid'] for p in phases})==len(phases)
        print(json.dumps({'status':'PASS','stock_commit':PIN,'host_tracked_clean':True,'native_discovery_and_dispatch':'PASS','fresh_process_phases':phases,'scope':'Invented project-bound fixtures; no live canonical, identity-authentication, clinical or model-quality claim.'}))
