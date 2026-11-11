"""Real owned Git check/pull/scan/exact-target gates; PM publication refused.
No host install, new environment, GitHub/network or user repository is touched.
Fixture repositories and their commits are generated disposable test data.
"""
from pathlib import Path
from contextlib import closing
import json,os,subprocess,tempfile,unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hermes_constants import set_hermes_home_override,reset_hermes_home_override
from hermes_state import SessionDB
from hermes_cli import plugins_cmd as pc
from hermes_cli.plugins_manifest import SUPPORTED_MANIFEST_VERSION
from elm_plugin.product_ui_api import router

class NativePluginPrepublication(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='native-plugin-prepublication-');self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name);self.token=set_hermes_home_override(self.home);self.addCleanup(reset_hermes_home_override,self.token)
        with closing(SessionDB(self.home/'state.db')) as db:db.create_session('chat-a',source='desktop')
        self.git_exe=pc._resolve_git_executable();self.assertTrue(self.git_exe,'Real existing Git required; no installation fallback')
        empty=self.home/'git-global-empty';empty.write_text('');hooks=self.home/'no-hooks';hooks.mkdir()
        envpatch=patch.dict(os.environ,{'GIT_CONFIG_GLOBAL':str(empty),'GIT_CONFIG_NOSYSTEM':'1','GIT_TERMINAL_PROMPT':'0','GIT_AUTHOR_NAME':'fixture','GIT_AUTHOR_EMAIL':'fixture@example.invalid','GIT_COMMITTER_NAME':'fixture','GIT_COMMITTER_EMAIL':'fixture@example.invalid'})
        envpatch.start();self.addCleanup(envpatch.stop);self.hooks=hooks
        self.origin=self.home/'fixture-origin';self.origin.mkdir();self.git('init','-q','-b','main',cwd=self.origin)
        self.old=self.version('1.0.0');self.target=self.home/'plugins'/'fixture-owned';self.target.parent.mkdir()
        self.git('clone','-q',self.origin.as_uri(),str(self.target),cwd=self.home)
        pc._write_install_metadata({'fixture-owned':{'source':self.origin.as_uri(),'revision':self.old,'pinned':False}})
        self.new=self.version('1.0.1')
        app=FastAPI();app.include_router(router,prefix='/ui');self.client=TestClient(app);self.addCleanup(self.client.close)
    def git(self,*args,cwd):
        r=subprocess.run([self.git_exe,'-c','commit.gpgsign=false','-c','core.hooksPath='+str(self.hooks),*args],cwd=cwd,capture_output=True,text=True,encoding='utf-8',timeout=30)
        self.assertEqual(r.returncode,0,r.stderr);return r.stdout.strip()
    def version(self,version):
        (self.origin/'plugin.yaml').write_text(f'name: fixture-owned\nversion: {version}\nmanifest_version: {SUPPORTED_MANIFEST_VERSION}\n',encoding='utf-8')
        (self.origin/'__init__.py').write_text(f'VERSION = {version!r}\ndef register(ctx):\n    pass\n',encoding='utf-8')
        self.git('add','--all',cwd=self.origin);self.git('commit','-q','-m','Synthetic fixture '+version,cwd=self.origin)
        return self.git('rev-parse','HEAD',cwd=self.origin)
    def checked(self):
        response=self.client.post('/ui/updates/check',json={'session_id':'chat-a'});self.assertEqual(response.status_code,200,response.text)
        row=next(x for x in response.json()['rows'] if x['type']=='plugin' and x['name']=='fixture-owned')
        self.assertEqual(row['current'],self.old);self.assertEqual(row['target'],self.new);self.assertTrue(row['selectable'],row)
        return row
    def apply(self,row):return self.client.post('/ui/updates/apply',json={'session_id':'chat-a','selection':row})
    def test_real_native_git_prepares_exact_target_then_pm_refusal_preserves_original(self):
        row=self.checked();before=(self.target/'__init__.py').read_bytes();calls=[]
        def refuse_pm(**kwargs):
            update=kwargs['plugins'].data;stage=Path(update['staged'])
            self.assertEqual(self.git('rev-parse','HEAD',cwd=stage),self.new)
            self.assertEqual(update['new_metadata']['fixture-owned']['revision'],self.new)
            calls.append({'staged_sha':self.new,'target':str(update['target'])})
            raise RuntimeError('SYNTHETIC_PM_REFUSAL_NO_ENVIRONMENT_OR_PUBLICATION_ALLOWED')
        with patch('pm.client.sync_venv',side_effect=refuse_pm):response=self.apply(row)
        self.assertEqual(response.status_code,409,response.text);self.assertEqual(response.json()['code'],'update_refused')
        self.assertEqual(len(calls),1,'Real Git/native scan/target gate never reached the PM handoff')
        self.assertEqual(self.git('rev-parse','HEAD',cwd=self.target),self.old);self.assertEqual((self.target/'__init__.py').read_bytes(),before)
        self.assertEqual(pc._read_install_metadata()['fixture-owned']['revision'],self.old)
        self.assertFalse((self.home/'elm-workspaces').exists())
        print('NATIVE_GIT_PREPUBLICATION '+json.dumps({'real_git':True,'old':self.old,'prepared_target':self.new,'pm_handoff_reached':True,'publication_executed':False,'environment_changed':False,'original_preserved':True}))
    def test_real_native_git_target_move_during_pull_refuses_before_pm(self):
        row=self.checked();real=pc._git_pull_plugin_dir;observed=[]
        def move_then_pull(staged):
            observed.append(self.version('1.0.2'));return real(staged)
        with patch.object(pc,'_git_pull_plugin_dir',side_effect=move_then_pull),patch('pm.client.sync_venv',side_effect=AssertionError('PM must not be reached')) as pm:
            response=self.apply(row)
        self.assertEqual(response.status_code,409,response.text);self.assertEqual(len(observed),1)
        self.assertFalse(pm.called);self.assertEqual(self.git('rev-parse','HEAD',cwd=self.target),self.old)
        self.assertEqual(pc._read_install_metadata()['fixture-owned']['revision'],self.old)
    def test_catalog_review_does_not_approve_caution_in_carried_local_files(self):
        from hermes_cli import plugin_catalog,plugins_cmd_catalog as cat
        from tools.plugin_guard import scan_plugin
        entry=plugin_catalog.PluginCatalogEntry(name='fixture-owned',repo=self.origin.as_uri(),sha=self.new,description='Synthetic catalog transport',maintainer='fixture')
        catalog={'name':entry.name,'repo':entry.repo,'tier':entry.tier,'pin':self.old,'sha':self.old}
        metadata=pc._read_install_metadata();metadata['fixture-owned'].update(catalog=catalog,pinned=True);pc._write_install_metadata(metadata)
        cat.write_catalog_sidecar_record(self.target,catalog,self.old)
        # Literal adversarial TEST DATA. This file is scanned, never executed.
        local=self.target/'tests'/'test_local_fixture.py';local.parent.mkdir();local.write_text("import os\nos.system('rm -rf /')\n",encoding='utf-8')
        exclude=self.target/'.git/info/exclude';exclude.write_text(exclude.read_text()+"\ntests/\n",encoding='utf-8')
        self.assertEqual(scan_plugin(self.target,source='owned-fixture').verdict,'caution')
        with patch.object(plugin_catalog,'fetch_live_catalog',return_value=None),patch.object(plugin_catalog,'load_catalog',return_value=[entry]):
            row=self.checked()
            with patch('pm.client.sync_venv',side_effect=RuntimeError('No publication allowed in fixture')) as pm:
                response=self.apply(row)
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(response.json()['code'],'update_review_required')
        self.assertFalse(pm.called,'Reviewed catalog pin incorrectly approved a carried-file caution')
        self.assertEqual(self.git('rev-parse','HEAD',cwd=self.target),self.old)
        self.assertEqual(local.read_text(),"import os\nos.system('rm -rf /')\n")

    def test_late_local_files_during_catalog_lookup_refuse_before_pm(self):
        row=self.checked()
        from hermes_cli import plugins_cmd_catalog as cat
        import inspect
        real=cat.catalog_install_record;changed=[]
        def edit_during_lookup(path):
            caller=inspect.currentframe().f_back
            while caller and not (caller.f_code.co_name=='plugin' and caller.f_globals.get('__name__','').endswith('.product_ui_api')):
                caller=caller.f_back
            if caller and not changed:
                (self.target/'__init__.py').write_bytes((self.target/'__init__.py').read_bytes()+b'\n# Keep late tracked edit.\n')
                (self.target/'late-user-file.txt').write_text('Keep late untracked bytes.',encoding='utf-8')
                changed.append(True)
            return real(path)
        with patch.object(cat,'catalog_install_record',side_effect=edit_during_lookup),patch('pm.client.sync_venv',side_effect=RuntimeError('No publication allowed in fixture')) as pm:
            response=self.apply(row)
        self.assertEqual(changed,[True],'Fault must occur after the adapter local-file inspection')
        self.assertEqual(response.status_code,409,response.text)
        self.assertFalse(pm.called,'Changed local files were admitted through the native staging gate')
        self.assertIn(b'Keep late tracked edit.',(self.target/'__init__.py').read_bytes())
        self.assertEqual((self.target/'late-user-file.txt').read_text(),'Keep late untracked bytes.')
        self.assertEqual(self.git('rev-parse','HEAD',cwd=self.target),self.old)
        self.assertEqual(pc._read_install_metadata()['fixture-owned']['revision'],self.old)

    def test_tracked_local_edit_is_preserved_before_native_git_preparation(self):
        row=self.checked();original=(self.target/'__init__.py').read_bytes();edited=original+b'\n# Keep this synthetic local edit.\n';(self.target/'__init__.py').write_bytes(edited)
        with patch('pm.client.sync_venv',side_effect=AssertionError('PM must not be reached')) as pm:response=self.apply(row)
        self.assertEqual(response.status_code,409,response.text);self.assertFalse(pm.called)
        self.assertEqual((self.target/'__init__.py').read_bytes(),edited);self.assertEqual(pc._read_install_metadata()['fixture-owned']['revision'],self.old)

if __name__=='__main__':unittest.main(verbosity=2)
