"""Future-only creation bindings against actual synthetic native host metadata."""
import importlib
import unittest
import test_workspace_service as fixtures
from hermes_cli import projects_db
from elm_plugin.private_controls import PrivateControls


class PrivateCreationTests(unittest.TestCase):
    setUp = fixtures.WorkspaceServiceTests.setUp
    service = fixtures.WorkspaceServiceTests.service

    def test_only_explicit_fresh_chat_receives_defaults_old_first_use_stays_private(self):
        self.service().setup(confirm=True)
        prefs = PrivateControls(self.home)
        before = prefs.read('chat-a')
        settings = before['settings']
        settings['private_chat']['workspace_reads'] = True
        prefs.save('chat-a', before['revision'], settings)
        try:
            C = importlib.import_module('elm_plugin.private_creation').PrivateCreation
        except ModuleNotFoundError as exc:
            if exc.name == 'elm_plugin.private_creation':
                self.fail('New private-container creation has no host-bound, future-only consumer')
            raise
        creator = C(self.home)
        intent = creator.begin('chat-a', 'private_chat', self.project_id, '', 2)
        self.db.create_session('new-private', source='gui')
        projects_db.set_session_project(self.projects, 'new-private', self.project_id)
        done = creator.finish('chat-a', intent['id'], 'new-private')
        self.assertEqual(done['status'], 'configured')
        s = self.service()
        self.assertTrue(s.read_policy('new-private')['workspace_enabled'])
        self.assertFalse(s.read_policy('chat-b')['workspace_enabled'])
        self.assertIsNone(prefs.chat_model_policy('chat-b'))
        self.assertEqual(prefs.chat_model_policy('new-private')['kind'], 'private_chat')

    def test_project_move_before_policy_commit_cannot_grant_an_unselected_workspace(self):
        from unittest.mock import patch
        from elm_plugin.private_creation import PrivateCreation
        from elm_plugin.workspace_service import WorkspaceService
        from elm_plugin.result_inbox import InboxError
        self.service().setup(confirm=True)
        prefs=PrivateControls(self.home);d=prefs.read('chat-a');d['settings']['private_chat']['workspace_reads']=True
        prefs.save('chat-a',1,d['settings'])
        creator=PrivateCreation(self.home);intent=creator.begin('chat-a','private_chat',self.project_id,'',2)
        self.db.create_session('racy-new',source='gui')
        projects_db.set_session_project(self.projects,'racy-new',self.project_id)
        other=projects_db.create_project(self.projects,name='Other fictional project')
        original=WorkspaceService._mutate
        def moved(service,fn,*args,**kwargs):
            projects_db.set_session_project(self.projects,'racy-new',other)
            return original(service,fn,*args,**kwargs)
        with patch.object(WorkspaceService,'_mutate',moved):
            with self.assertRaises(InboxError):creator.finish('chat-a',intent['id'],'racy-new')
        self.assertFalse(self.service().read_policy('racy-new')['workspace_enabled'], 'Unselected incoming source was granted before the final refusal')

    def test_new_container_memory_model_policy_gates_egress_and_routes_explicitly(self):
        from types import SimpleNamespace
        from elm_plugin.private_creation import PrivateCreation
        from elm_plugin.workspace_learning import WorkspaceLearning
        from elm_plugin.workspace_service import ServiceError
        s=self.service();s.setup(confirm=True);s.set_learning(True)
        prefs=PrivateControls(self.home);settings=prefs.read('chat-a')['settings']
        settings['private_chat']['memory'].update(mode='separate',provider='fixture-provider',model='fixture-model',allow_host_fallback=False)
        prefs.save('chat-a',1,settings)
        creator=PrivateCreation(self.home);intent=creator.begin('chat-a','private_chat',self.project_id,'',2)
        self.db.create_session('new-model-chat',source='gui');projects_db.set_session_project(self.projects,'new-model-chat',self.project_id)
        creator.finish('chat-a',intent['id'],'new-model-chat')
        scope=s.capture('new-model-chat')['scope_id']
        record=s.create_record(dict(scope_id=scope,title='Fictional source',text='Use indigo.',domain='work',kind='explicit_fact',basis='explicit_statement',sources=[{'ref':'fictional:test'}],state='approved'))
        calls=[]
        class FakeHost:
            def complete(self,**kwargs):
                calls.append(kwargs)
                return SimpleNamespace(text='{"title":"Draft","text":"Use indigo."}',provider='fixture-provider',model='fixture-model',usage={})
        try: WorkspaceLearning(s,FakeHost()).draft(scope,[record['id']],'summary',session_id='new-model-chat')
        except ServiceError: pass
        self.assertEqual(calls,[], 'Unacknowledged host fallback must not dispatch private source content')
        settings['private_chat']['memory']['allow_host_fallback']=True
        prefs.save('chat-a',2,settings)
        intent2=creator.begin('chat-a','private_chat',self.project_id,'',3)
        self.db.create_session('allowed-model-chat',source='gui');projects_db.set_session_project(self.projects,'allowed-model-chat',self.project_id)
        creator.finish('chat-a',intent2['id'],'allowed-model-chat')
        scope2=s.capture('allowed-model-chat')['scope_id']
        record2=s.create_record(dict(scope_id=scope2,title='Fictional source',text='Use indigo.',domain='work',kind='explicit_fact',basis='explicit_statement',sources=[{'ref':'fictional:test'}],state='approved'))
        drafted=WorkspaceLearning(s,FakeHost()).draft(scope2,[record2['id']],'summary',session_id='allowed-model-chat')
        self.assertEqual((calls[-1]['provider'],calls[-1]['model']),('fixture-provider','fixture-model'))
        self.assertEqual((drafted['state'],drafted['basis']),('pending','inference'))
        self.assertEqual(drafted['generation_receipt']['requested_route']['provider'],'fixture-provider')
        self.assertFalse(prefs.chat_model_policy('new-model-chat')['settings']['private_chat']['memory']['allow_host_fallback'])
        from agent.plugin_llm import PluginLlm
        denied_calls=[]
        denied=PluginLlm(plugin_id='elm',policy_loader=lambda _:SimpleNamespace(plugin_id='elm',allow_provider_override=False),sync_caller=lambda **kw:denied_calls.append(kw))
        with self.assertRaises(ServiceError): WorkspaceLearning(s,denied).draft(scope2,[record2['id']],'summary',session_id='allowed-model-chat')
        self.assertEqual(denied_calls,[], 'Native permission denial must precede transport')

    def test_workspace_members_share_only_pool_reads_and_private_members_keep_own_pool(self):
        from elm_plugin.private_creation import PrivateCreation
        from elm_plugin.result_inbox import InboxError
        s=self.service();s.setup(confirm=True);creator=PrivateCreation(self.home)
        begin=creator.begin('chat-a','private_workspace','','New synthetic workspace',1)
        pid=projects_db.create_project(self.projects,name='New synthetic workspace')
        done=creator.finish('chat-a',begin['id'],pid)
        self.assertTrue(done['policy']['private'])
        self.assertTrue(next(p for p in creator.overview('chat-a')['projects'] if p['id']==pid)['private_workspace'])
        for sid,kind,expected in [('ordinary','workspace_member',True),('private-member','private_chat',False)]:
            intent=creator.begin('chat-a',kind,pid,'',1)
            self.db.create_session(sid,source='gui');projects_db.set_session_project(self.projects,sid,pid)
            creator.finish('chat-a',intent['id'],sid)
            view=s.read_policy(sid)
            self.assertEqual(view['workspace_enabled'],expected)
            self.assertTrue(view['private'])
        stale=creator.begin('chat-a','private_chat',self.project_id,'',1)
        with self.assertRaises(InboxError):creator.finish('chat-a',stale['id'],'chat-b')

    def test_changed_defaults_and_compression_child_are_never_treated_as_new(self):
        from elm_plugin.private_creation import PrivateCreation
        from elm_plugin.result_inbox import InboxError
        self.service().setup(confirm=True);creator=PrivateCreation(self.home)
        intent=creator.begin('chat-a','private_chat',self.project_id,'',1)
        settings=creator.read('chat-a')['settings'];creator.save('chat-a',1,settings)
        self.db.create_session('after-default-change',source='gui');projects_db.set_session_project(self.projects,'after-default-change',self.project_id)
        with self.assertRaises(InboxError):creator.finish('chat-a',intent['id'],'after-default-change')
        intent=creator.begin('chat-a','private_chat',self.project_id,'',2)
        self.db.end_session('chat-b','compression');self.db.create_session('continuation',source='gui',parent_session_id='chat-b')
        with self.assertRaises(InboxError):creator.finish('chat-a',intent['id'],'continuation')
        self.assertIsNone(creator.chat_model_policy('chat-b'))

    def test_follow_chat_uses_explicit_live_sdk_route_snapshot_not_global_default(self):
        from types import SimpleNamespace
        from elm_plugin.private_creation import PrivateCreation
        from elm_plugin.workspace_learning import WorkspaceLearning
        from elm_plugin.workspace_service import ServiceError
        s=self.service();s.setup(confirm=True);s.set_learning(True);prefs=PrivateControls(self.home)
        settings=prefs.read('chat-a')['settings'];settings['private_chat']['memory'].update(mode='follow_chat',allow_host_fallback=True)
        prefs.save('chat-a',1,settings)
        creator=PrivateCreation(self.home);i=creator.begin('chat-a','private_chat',self.project_id,'',2)
        self.db.create_session('follow-chat',source='gui');projects_db.set_session_project(self.projects,'follow-chat',self.project_id)
        creator.finish('chat-a',i['id'],'follow-chat');scope=s.capture('follow-chat')['scope_id']
        r=s.create_record(dict(scope_id=scope,title='Source',text='Use indigo.',domain='work',kind='explicit_fact',basis='explicit_statement',sources=[{'ref':'fictional:snapshot'}],state='approved'))
        calls=[]
        class Host:
            def complete(self,**kw):
                calls.append(kw);return SimpleNamespace(text='{"title":"Draft","text":"Use indigo."}',provider=kw['provider'],model=kw['model'],usage={})
        with self.assertRaises(ServiceError):WorkspaceLearning(s,Host()).draft(scope,[r['id']],'summary',session_id='follow-chat')
        self.assertEqual(calls,[])
        out=WorkspaceLearning(s,Host()).draft(scope,[r['id']],'summary',session_id='follow-chat',model_route={'provider':'fixture-provider','model':'current-chat-model'})
        self.assertEqual((calls[0]['provider'],calls[0]['model']),('fixture-provider','current-chat-model'))
        self.assertEqual(out['generation_receipt']['requested_route']['mode'],'follow_chat')

    def test_private_workspace_processing_uses_immutable_workspace_model_policy(self):
        from types import SimpleNamespace
        from elm_plugin.private_creation import PrivateCreation
        from elm_plugin.workspace_learning import WorkspaceLearning
        from elm_plugin.workspace_service import ServiceError
        s=self.service();s.setup(confirm=True);s.set_learning(True);prefs=PrivateControls(self.home);creator=PrivateCreation(self.home)
        for mode in ('separate','follow_chat'):
            defaults=prefs.read('chat-a');settings=defaults['settings']
            settings['private_workspace']['memory'].update(mode=mode,provider='fixture-provider' if mode=='separate' else '',model='workspace-model' if mode=='separate' else '',allow_host_fallback=True)
            saved=prefs.save('chat-a',defaults['revision'],settings)
            intent=creator.begin('chat-a','private_workspace','',mode,saved['revision'])
            pid=projects_db.create_project(self.projects,name=mode);out=creator.finish('chat-a',intent['id'],pid);scope=out['policy']['scope_id']
            r=s.create_record(dict(scope_id=scope,title='Pool source',text='Use plum.',domain='work',kind='explicit_fact',basis='explicit_statement',sources=[{'ref':'fictional:workspace-model'}],state='approved'))
            member='member-'+mode;self.db.create_session(member,source='gui');projects_db.set_session_project(self.projects,member,pid)
            calls=[]
            class Host:
                def complete(self,**kw):
                    calls.append(kw);return SimpleNamespace(text='{"title":"Draft","text":"Use plum."}',provider=kw.get('provider','global'),model=kw.get('model','global'),usage={})
            # Later profile defaults must not migrate this existing workspace.
            newest=prefs.read('chat-a');newest['settings']['private_workspace']['memory'].update(mode='host',provider='',model='')
            prefs.save('chat-a',newest['revision'],newest['settings'])
            kwargs={}
            if mode=='follow_chat':
                with self.assertRaises(ServiceError):WorkspaceLearning(s,Host()).draft(scope,[r['id']],'summary')
                self.assertEqual(calls,[])
                kwargs={'session_id':member,'model_route':{'provider':'fixture-provider','model':'workspace-model'}}
            WorkspaceLearning(s,Host()).draft(scope,[r['id']],'summary',**kwargs)
            self.assertEqual((calls[0].get('provider'),calls[0].get('model')),('fixture-provider','workspace-model'))
            self.assertIsNone(creator.chat_model_policy(member),'Processing a pool cannot apply defaults to an existing member chat')
