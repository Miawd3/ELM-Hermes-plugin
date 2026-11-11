"""Real candidate entrypoint + host command/llm facade + HTTP, offline provider I/O.

Only plugin discovery location and the external completion transport are replaced.
This tests actual package metadata, not the bridge tests' synthetic entrypoint.
"""
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import test_workspace_api as api_fixtures
from hermes_cli import plugins

CANDIDATE = Path(__file__).resolve().parents[1]


class WorkspaceDraftApiTests(unittest.TestCase):
    setUp = api_fixtures.WorkspaceApiTests.setUp
    client = api_fixtures.WorkspaceApiTests.client

    def prepared(self, llm_policy=None):
        config={'plugins':{'enabled':['elm'],'isolation':'in_process'},'model':{'provider':'offline-fixture','model':'fictional-model'}}
        if llm_policy is not None:config['plugins']['entries']={'elm':{'llm':llm_policy}}
        (self.home/'config.yaml').write_text(json.dumps(config), encoding='utf-8')
        discovery = patch.object(plugins, 'get_bundled_plugins_dir', return_value=CANDIDATE.parent)
        discovery.start()
        self.addCleanup(discovery.stop)
        self.addCleanup(plugins.get_plugin_manager().unload)
        self.calls = []
        def complete(**kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(model='fictional-model', provider='offline-fixture',
                choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(
                    {'title':'Release summary','text':'Amber release needs a signed rollback.'})))],
                usage=SimpleNamespace(prompt_tokens=50, completion_tokens=20, total_tokens=70))
        transport = patch('agent.auxiliary_client.call_llm', side_effect=complete)
        transport.start()
        self.addCleanup(transport.stop)
        client = self.client()
        p = '/api/plugins/elm'
        self.assertEqual(client.post(p+'/setup', json={'confirm':True}).status_code,200)
        scope = client.get(p+'/overview',params={'session_id':'chat-a'}).json()['selected_scope_id']
        made = client.post(p+'/record',json=dict(scope_id=scope,title='Fictional release',
            text='Amber release needs a signed rollback.',domain='work',kind='explicit_fact',
            basis='explicit_statement',sources=[{'ref':'fictional:draft-api'}],state='approved'))
        self.assertEqual(made.status_code,200,made.text)
        return client,p,scope,made.json()['result']

    def test_actual_package_registers_host_owned_generation_for_pending_http_readback(self):
        client,p,scope,source = self.prepared()
        payload = dict(scope_id=scope,record_ids=[source['id']],kind='observation')
        disabled = client.post(p+'/draft',json=payload)
        self.assertEqual(disabled.status_code,400,disabled.text)
        self.assertEqual(disabled.json()['code'],'learning_disabled')
        self.assertEqual(self.calls,[])
        self.assertEqual(client.post(p+'/learning',json={'enabled':True}).status_code,200)
        reply = client.post(p+'/draft',json=payload)
        self.assertEqual(reply.status_code,200,reply.text)
        record = reply.json()['result']
        self.assertEqual(len(self.calls),1)
        self.assertEqual((record['state'],record['kind'],record['basis']),('pending','interpretation','inference'))
        self.assertEqual(record['scope_id'],scope)
        self.assertEqual(record['dependencies'],[{'id':source['id'],'revision':source['revision']}])
        receipt = record['generation_receipt']
        self.assertEqual(receipt['record_id'],record['id'])
        self.assertEqual(receipt['requested_kind'],'observation')
        self.assertEqual(receipt['usage']['total_tokens'],70)
        fresh = client.get(p+'/overview',params={'session_id':'chat-a'}).json()
        stored = next(r for r in fresh['records'] if r['id']==record['id'])
        self.assertEqual(stored['state'],'pending')
        self.assertEqual(stored['revision'],record['revision'])
        service_class = next(r.endpoint.__globals__['WorkspaceService'] for r in client.app.routes
                             if getattr(r,'path',None)==p+'/overview')
        service = service_class(self.home)
        self.assertNotIn(record['id'],[r['id'] for r in service.capture('chat-a')['records']])
        saved = json.loads((service.base/'generation-receipts'/(record['id']+'.json')).read_text(encoding='utf-8'))
        self.assertEqual(saved['record_id'],record['id'])
        for extra in ({'root':'C:/unrelated'},{'state':'approved'},{'provider':'other-provider'}):
            refused=client.post(p+'/draft',json={**payload,**extra})
            self.assertEqual(refused.status_code,400,refused.text)
        self.assertEqual(len(self.calls),1)


    def follow_prepared(self,permissions=None):
        from contextlib import closing
        from hermes_state import SessionDB
        client,p,_,_=self.prepared(permissions)
        before=(self.home/'config.yaml').read_bytes()
        prefs=client.get(p+'/ui/private',params={'session_id':'chat-a'}).json()
        settings=prefs['settings'];settings['private_chat']['memory'].update(mode='follow_chat',allow_host_fallback=True)
        saved=client.post(p+'/ui/private/defaults',json={'session_id':'chat-a','expected_revision':prefs['revision'],'settings':settings})
        self.assertEqual(saved.status_code,200,saved.text)
        intent=client.post(p+'/ui/private/create',json={'session_id':'chat-a','kind':'private_chat','project_id':'','name':'','expected_revision':saved.json()['result']['revision']})
        self.assertEqual(intent.status_code,200,intent.text)
        with closing(SessionDB(self.home/'state.db')) as db:db.create_session('api-follow-chat',source='gui',model='fictional-model')
        done=client.post(p+'/ui/private/finish',json={'session_id':'chat-a','intent_id':intent.json()['result']['id'],'created_id':'api-follow-chat'})
        self.assertEqual(done.status_code,200,done.text)
        scope=done.json()['result']['policy']['authored_scope_id']
        made=client.post(p+'/record',json=dict(scope_id=scope,title='Fictional release',text='Amber release needs a signed rollback.',domain='work',kind='explicit_fact',basis='explicit_statement',sources=[{'ref':'fictional:follow-api'}],state='approved'))
        self.assertEqual(made.status_code,200,made.text)
        self.assertEqual(client.post(p+'/learning',json={'enabled':True}).status_code,200)
        self.assertEqual((self.home/'config.yaml').read_bytes(),before,'Private preferences must never widen native grants')
        return client,p,{'scope_id':scope,'record_ids':[made.json()['result']['id']],'kind':'summary','session_id':'api-follow-chat','model_route':{'provider':'offline-fixture','model':'fictional-model'}}

    def test_follow_chat_http_reaches_actual_host_facade_only_with_existing_specific_permissions(self):
        client,p,payload=self.follow_prepared({'allow_provider_override':True,'allow_model_override':True,'allowed_providers':['offline-fixture'],'allowed_models':['fictional-model']})
        missing=client.post(p+'/draft',json={k:v for k,v in payload.items() if k!='model_route'})
        self.assertEqual(missing.status_code,400,missing.text);self.assertEqual(self.calls,[])
        reply=client.post(p+'/draft',json=payload)
        self.assertEqual(reply.status_code,200,reply.text);self.assertEqual(len(self.calls),1)
        receipt=reply.json()['result']['generation_receipt'];self.assertEqual(receipt['requested_route']['mode'],'follow_chat')
        self.assertEqual(receipt['requested_route']['model'],'fictional-model')
        denied=client.post(p+'/draft',json={**payload,'model_route':{'provider':'offline-fixture','model':'not-permitted'}})
        self.assertEqual(denied.status_code,400,denied.text);self.assertEqual(len(self.calls),1)

    def test_follow_chat_preferences_cannot_grant_missing_host_override_permission(self):
        client,p,payload=self.follow_prepared()
        reply=client.post(p+'/draft',json=payload)
        self.assertEqual(reply.status_code,400,reply.text);self.assertEqual(self.calls,[])


if __name__ == '__main__':
    unittest.main(verbosity=2)
