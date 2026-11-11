"""Owner integration through real standalone API loader and native MemoryManager.
No live authentication/profile/activation. Native discovery alone is redirected.
"""
import importlib.util,json,unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from agent.memory_manager import MemoryManager
from plugins import memory
from hermes_constants import set_hermes_home_override,reset_hermes_home_override
from elm_plugin.result_inbox import ResultInbox
import test_workspace_service as fixtures
CANDIDATE=Path(__file__).resolve().parents[1]

class ImportantOwnerIntegration(unittest.TestCase):
    setUp=fixtures.WorkspaceServiceTests.setUp
    service=fixtures.WorkspaceServiceTests.service
    def bind_home(self):
        token=set_hermes_home_override(self.home);self.addCleanup(reset_hermes_home_override,token)
    def manager(self,session_id='chat-a',agent_context='primary'):
        self.bind_home()
        with patch.object(memory,'find_provider_dir',return_value=CANDIDATE):provider=memory.load_memory_provider('elm')
        self.assertIsNotNone(provider);self.assertTrue(provider.is_available())
        manager=MemoryManager();manager.add_provider(provider)
        manager.initialize_all(session_id=session_id,hermes_home=str(self.home),platform='desktop',agent_context=agent_context)
        self.addCleanup(manager.shutdown_all);return manager,provider
    def test_standalone_namespaced_api_mount_saves_only_ui_state(self):
        self.bind_home()
        spec=importlib.util.spec_from_file_location('important_owner_standalone_api',CANDIDATE/'dashboard/plugin_api.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        app=FastAPI();app.include_router(module.router,prefix='/api/plugins/elm')
        with TestClient(app) as client:
            empty=client.get('/api/plugins/elm/ui/results',params={'session_id':'chat-a'})
            self.assertEqual(empty.status_code,200,'Product UI router is not mounted through the actual standalone plugin entry')
            self.assertEqual(empty.json()['results'],[])
            made=client.post('/api/plugins/elm/ui/results',json={'session_id':'chat-a','title':'Fictional output','body':'Complete literal output <no HTML>.','kind':'final'})
            self.assertEqual(made.status_code,200);result=made.json()['result'];self.assertEqual(result['status'],'unread')
            own=client.get('/api/plugins/elm/ui/results/'+result['id'],params={'session_id':'chat-a'}).json()
            self.assertTrue(own['exists']);self.assertEqual(own['result']['body'],'Complete literal output <no HTML>.')
            other=client.get('/api/plugins/elm/ui/results/'+result['id'],params={'session_id':'chat-b'}).json()
            self.assertFalse(other['exists']);self.assertIsNone(other['result'])
            bad=client.post('/api/plugins/elm/ui/results',json={'session_id':'chat-a','title':'x','body':'x','kind':'final','root':'C:/unrelated'})
            self.assertEqual(bad.status_code,400)
        self.assertFalse((self.home/'elm-workspaces').exists(),'Saving output must not initialize memory')
    def test_native_save_is_bounded_chat_only_and_not_a_memory_fact(self):
        service=self.service();service.setup(confirm=True);before=(service.store.root/'manifest.json').read_bytes()
        manager,provider=self.manager()
        self.assertTrue(manager.has_tool('elm_important'),'The Important publisher is not wired through the real native consumer')
        body='Authored fictional result. '+('Literal long output. '*700)
        wire=manager.handle_tool_call('elm_important',{'title':'Important fixture','body':body,'kind':'final'})
        self.assertLessEqual(len(wire),12000);value=json.loads(wire);self.assertTrue(value['ok']);self.assertEqual(value['disposition'],'saved')
        result_id=value['result']['id'];self.assertEqual(value['directive'],'::elm-result{id="'+result_id+'"}')
        self.assertNotIn(body,wire,'Do not echo a potentially100k body into a bounded tool receipt')
        saved=ResultInbox(self.home).get('chat-a',result_id);self.assertEqual(saved['result']['body'],body)
        self.assertEqual(saved['result']['status'],'unread');self.assertFalse(ResultInbox(self.home).get('chat-b',result_id)['exists'])
        self.assertEqual((service.store.root/'manifest.json').read_bytes(),before)
        self.assertFalse(value['whole_request_completion_verified']);self.assertFalse(value['user_read_verified'])
        schema=next(t for t in provider.get_tool_schemas() if t['name']=='elm_important')
        self.assertEqual(set(schema['parameters']['properties']),{'title','body','kind'})
        for injected in ({'session_id':'chat-b'},{'root':'C:/unrelated'},{'status':'read'}):
            denied=json.loads(manager.handle_tool_call('elm_important',{'title':'x','body':'x','kind':'progress',**injected}))
            self.assertEqual(denied['error'],'invalid_arguments')

    def test_native_unknown_host_is_refused_before_any_ui_write(self):
        self.service().setup(confirm=True);manager,provider=self.manager(session_id='not-yet-persisted')
        self.assertTrue(manager.has_tool('elm_important'))
        value=json.loads(manager.handle_tool_call('elm_important',{'title':'T','body':'B','kind':'progress'}))
        self.assertEqual(value.get('error'),'session_unavailable')
        self.assertFalse((self.home/'elm-product-ui').exists())
    def test_native_profile_and_delegated_context_cannot_publish_primary_output(self):
        self.service().setup(confirm=True);manager,provider=self.manager()
        other=self.home/'other-profile';other.mkdir();token=set_hermes_home_override(other)
        try:value=json.loads(manager.handle_tool_call('elm_important',{'title':'T','body':'B','kind':'progress'}))
        finally:reset_hermes_home_override(token)
        # The real host manager refuses before the plugin and intentionally
        # exposes only a generic error, not its private profile diagnostic code.
        self.assertIn('refused',value['error']);self.assertFalse((other/'elm-product-ui').exists())
        delegated,_=self.manager(agent_context='delegated')
        blocked=json.loads(delegated.handle_tool_call('elm_important',{'title':'T','body':'B','kind':'final'}))
        self.assertEqual(blocked['error'],'write_blocked');self.assertFalse((self.home/'elm-product-ui').exists())
    def test_native_scope_change_after_save_withholds_old_content_and_locator(self):
        import importlib
        self.service().setup(confirm=True);manager,provider=self.manager()
        helper=importlib.import_module(importlib.import_module(type(provider).__module__).publish_current.__module__)
        real=helper.publish_important_result;saved=[]
        def switch_after_commit(**kwargs):
            result=real(**kwargs);saved.append(result['result']['id']);provider.on_session_switch('chat-b');return result
        with patch.object(helper,'publish_important_result',side_effect=switch_after_commit):
            wire=manager.handle_tool_call('elm_important',{'title':'Old chat output','body':'OLD_CHAT_LITERAL_BODY','kind':'partial'})
        result=json.loads(wire);self.assertEqual(result['disposition'],'saved_but_withheld')
        self.assertEqual(result['save_status'],'saved_in_admitted_chat');self.assertFalse(result['automatic_retry'])
        self.assertNotIn('OLD_CHAT_LITERAL_BODY',wire);self.assertNotIn(saved[0],wire)
        self.assertTrue(ResultInbox(self.home).get('chat-a',saved[0])['exists']);self.assertFalse(ResultInbox(self.home).get('chat-b',saved[0])['exists'])
    def test_native_missing_postcommit_row_is_uncertain_without_republishing(self):
        import importlib
        self.service().setup(confirm=True);manager,provider=self.manager()
        helper=importlib.import_module(importlib.import_module(type(provider).__module__).publish_current.__module__)
        native_inbox=helper.publish_important_result.__globals__['ResultInbox']
        with patch.object(native_inbox,'get',return_value={'result':None,'exists':False}) as readback:
            result=json.loads(manager.handle_tool_call('elm_important',{'title':'T','body':'B','kind':'progress'}))
        self.assertEqual(result.get('disposition'),'publication_unconfirmed',result)
        self.assertEqual(result['save_status'],'unknown');self.assertFalse(result['automatic_retry'])
        self.assertEqual(readback.call_count,1)
        self.assertEqual(len(ResultInbox(self.home).list('chat-a')['results']),1,'A readback failure must not repeat the committed insert')

    def test_postcommit_readback_failure_is_unconfirmed_and_not_retried_by_handler(self):
        import importlib
        self.service().setup(confirm=True);manager,provider=self.manager()
        helper=importlib.import_module(importlib.import_module(type(provider).__module__).publish_current.__module__)
        real=helper.publish_important_result;calls=[]
        def fail_after_commit(**kwargs):
            result=real(**kwargs);calls.append(result['result']['id']);raise OSError('Synthetic postcommit readback loss')
        with patch.object(helper,'publish_important_result',side_effect=fail_after_commit):
            result=json.loads(manager.handle_tool_call('elm_important',{'title':'T','body':'B','kind':'progress'}))
        self.assertEqual(result['disposition'],'publication_unconfirmed');self.assertEqual(result['save_status'],'unknown')
        self.assertFalse(result['automatic_retry']);self.assertEqual(len(calls),1)
        self.assertEqual(len(ResultInbox(self.home).list('chat-a')['results']),1)

if __name__=='__main__':unittest.main(verbosity=2)
