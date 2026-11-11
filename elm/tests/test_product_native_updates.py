"""Native skill check/quarantine/scan/install consumers; source transport synthetic."""
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hermes_state import SessionDB
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from tools.skills_hub_models import SkillBundle
from tools.skills_hub import HubLockFile
from tools.skills_hub_install import bundle_content_hash
from tools.skills_guard import content_hash


class NativeUpdatesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='important-updates-');self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name)
        self.token=set_hermes_home_override(self.home);self.addCleanup(reset_hermes_home_override,self.token)
        with closing(SessionDB(self.home/'state.db')) as db:db.create_session('chat-a',source='desktop')
        self.skill=self.home/'skills'/'fictional-owned';self.skill.mkdir(parents=True)
        (self.skill/'SKILL.md').write_text('---\nname: fictional-owned\ndescription: Synthetic update fixture.\n---\n\nOld harmless prose.\n',encoding='utf-8')
        self.old=content_hash(self.skill)
        HubLockFile().record_install(name='fictional-owned',source='github',identifier='fictional/repo/fictional-owned',
            trust_level='community',scan_verdict='safe',skill_hash=self.old,install_path='fictional-owned',files=['SKILL.md'])
        self.bundle=SkillBundle(name='fictional-owned',files={'SKILL.md':'---\nname: fictional-owned\ndescription: Synthetic update fixture.\n---\n\nNew harmless prose.\n'},source='github',identifier='fictional/repo/fictional-owned',trust_level='community')
        outer=self
        class Source:
            def source_id(self):return 'github'
            def fetch(self,identifier):return outer.bundle
        self.source=Source()
        self.transport=patch('tools.skills_hub_search.create_source_router',return_value=[self.source]);self.transport.start();self.addCleanup(self.transport.stop)
        from elm_plugin.product_ui_api import router
        app=FastAPI();app.include_router(router,prefix='/ui');self.c=TestClient(app);self.addCleanup(self.c.close)

    def check(self):return self.c.post('/ui/updates/check',json={'session_id':'chat-a'})

    def test_selected_native_skill_update_applies_exact_bundle_with_readback(self):
        r=self.check();self.assertEqual(r.status_code,200)
        self.assertTrue(r.json()['rows'],r.json())
        row=next(x for x in r.json()['rows'] if x['type']=='skill')
        self.assertEqual(row['current'],self.old)
        self.assertEqual(row['target'],bundle_content_hash(self.bundle))
        self.assertTrue(row['selectable'],row)
        applied=self.c.post('/ui/updates/apply',json={'session_id':'chat-a','selection':row})
        self.assertEqual(applied.status_code,200)
        self.assertEqual(applied.json()['result']['status'],'updated')
        observed=self.c.get('/ui/updates/installed',params={'session_id':'chat-a','type':'skill','name':'fictional-owned'})
        self.assertEqual(observed.status_code,200)
        self.assertEqual(observed.json()['observed'],row['target'])
        self.assertEqual(content_hash(self.skill),row['target'])
        self.assertEqual(HubLockFile().get_installed('fictional-owned')['content_hash'],row['target'])
        self.assertFalse((self.home/'elm-workspaces').exists())
        self.assertFalse((self.home/'config.yaml').exists())
        self.assertEqual(len(HubLockFile().list_installed()),1)

    def test_local_edits_stale_target_new_install_and_force_are_refused(self):
        r=self.check();self.assertEqual(r.status_code,200)
        self.assertTrue(r.json()['rows'],r.json())
        row=next(x for x in r.json()['rows'] if x['type']=='skill')
        (self.skill/'notes.txt').write_text('Keep my local notes.',encoding='utf-8')
        refused=self.c.post('/ui/updates/apply',json={'session_id':'chat-a','selection':row})
        self.assertEqual(refused.status_code,409)
        self.assertTrue((self.skill/'notes.txt').exists())
        self.assertEqual(HubLockFile().get_installed('fictional-owned')['content_hash'],self.old)
        forged={**row,'name':'not-installed'}
        self.assertNotEqual(self.c.post('/ui/updates/apply',json={'session_id':'chat-a','selection':forged}).status_code,200)
        self.assertEqual(self.c.post('/ui/updates/apply',json={'session_id':'chat-a','selection':row,'force':True}).status_code,400)
        self.assertFalse((self.home/'skills'/'not-installed').exists())

    def test_changed_upstream_scan_block_and_unknown_check_never_apply_silently(self):
        original=(self.skill/'SKILL.md').read_bytes()
        row=next(x for x in self.check().json()['rows'] if x['type']=='skill')
        self.bundle.files['SKILL.md']+='Upstream changed after selection.\n'
        refused=self.c.post('/ui/updates/apply',json={'session_id':'chat-a','selection':row})
        self.assertEqual(refused.status_code,409)
        self.assertEqual((self.skill/'SKILL.md').read_bytes(),original)
        self.bundle.files['payload.sh']='cat .env\n'
        checked=self.check().json()
        row=next(x for x in checked['rows'] if x['type']=='skill')
        blocked=self.c.post('/ui/updates/apply',json={'session_id':'chat-a','selection':row})
        self.assertEqual(blocked.status_code,409)
        self.assertEqual(blocked.json()['code'],'update_review_required')
        self.assertEqual((self.skill/'SKILL.md').read_bytes(),original)
        self.assertFalse((self.skill/'payload.sh').exists())
        self.assertEqual(HubLockFile().get_installed('fictional-owned')['content_hash'],self.old)
        with patch('tools.skills_hub_search.create_source_router',side_effect=RuntimeError('Synthetic upstream unavailable')):
            failed=self.check().json()
        self.assertEqual(failed['errors'][0]['type'],'skill')
        self.assertIn('unavailable',failed['errors'][0]['message'])
        self.assertFalse(any(x['type']=='skill' for x in failed['rows']))
        self.assertEqual(self.c.post('/ui/updates/check',json={'session_id':'not-owned'}).status_code,404)
        self.assertFalse((self.home/'config.yaml').exists())

    def test_local_edit_during_native_scan_is_kept_at_publication_boundary(self):
        row=next(x for x in self.check().json()['rows'] if x['type']=='skill')
        from tools.skills_guard import scan_skill
        def concurrent_edit(path,source):
            result=scan_skill(path,source=source)
            (self.skill/'keep-during-scan.txt').write_text('Concurrent synthetic edit.',encoding='utf-8')
            return result
        with patch('tools.skills_guard.scan_skill',side_effect=concurrent_edit):
            result=self.c.post('/ui/updates/apply',json={'session_id':'chat-a','selection':row})
        self.assertEqual(result.status_code,409)
        self.assertTrue((self.skill/'keep-during-scan.txt').exists())
        self.assertEqual(HubLockFile().get_installed('fictional-owned')['content_hash'],self.old)
        self.assertIn('Old harmless prose.',(self.skill/'SKILL.md').read_text(encoding='utf-8'))

if __name__=='__main__':unittest.main(verbosity=2)
