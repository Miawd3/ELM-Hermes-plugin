"""Synthetic human API -> real host identity/service/ELM/MemoryManager.

No inference: only external LLM transport is replaced in draft tests.
"""
import json
import sys
import unittest
from unittest.mock import patch

import test_workspace_service as fixtures
import test_workspace_native as native
import test_workspace_api as api
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from elm_plugin.workspace_records import RecordError


class DirectionalPolicyTests(unittest.TestCase):
    setUp = fixtures.WorkspaceServiceTests.setUp
    service = fixtures.WorkspaceServiceTests.service
    manager = native.WorkspaceNativeTests.manager
    client = api.WorkspaceApiTests.client

    def prepared(self):
        s = self.service()
        s.setup(confirm=True)
        a = s.capture('chat-a')
        b = s.capture('chat-b')
        workspace = a['context']['workspace_scope_id']
        record = self.record(s, workspace, 'Amber WORKSPACE_ALLOWED.')
        return s, a, b, workspace, record

    def record(self, s, scope, text, **changes):
        fields = dict(scope_id=scope, title='Fictional evidence', text=text,
            domain='work', kind='explicit_fact', basis='explicit_statement',
            sources=[{'ref':'fictional:directional-brief'}], state='approved')
        return s.create_record({**fields, **changes})

    def opt_in(self, s, enabled=True, session='chat-a'):
        view = s.read_policy(session)
        return s.set_read_policy(session_id=session, workspace_enabled=enabled,
            expected_identity=view['identity'], expected_policy_revision=view['policy_revision'])

    def test_private_chat_explicit_workspace_ingress_keeps_native_proposals_chat_owned(self):
        s, a, b, workspace, record = self.prepared()
        manager, provider = self.manager()
        self.assertEqual(json.loads(manager.handle_tool_call('elm_context', {'query':'amber'}))['results'], [])
        client = self.client()
        # The server derives the pool from the genuine current host identity;
        # the human sends no root, pool identifier or outgoing grant.
        response = client.post('/api/plugins/elm/read-policy', json=dict(session_id='chat-a',
            workspace_enabled=True, expected_identity=s.identity.resolve('chat-a')['fingerprint'],
            expected_policy_revision=None))
        actual = json.loads(manager.handle_tool_call('elm_context', {'query':'amber'}))
        self.assertEqual([r['record_id'] for r in actual['results']], [record['id']],
            f'Explicit incoming workspace permission was not adopted by native recall; HTTP={response.status_code}')
        self.assertEqual(response.status_code, 200, response.text)
        policy = client.get('/api/plugins/elm/read-policy', params={'session_id':'chat-a'}).json()
        self.assertTrue(policy['workspace_enabled'])
        self.assertTrue(policy['private'])
        self.assertEqual(policy['authored_scope_id'], a['scope_id'])
        self.assertEqual(policy['policy_revision'], response.json()['result']['policy_revision'])
        self.assertEqual(self.service().read_policy('chat-a'), policy)
        hit = actual['results'][0]
        self.assertEqual(json.loads(manager.handle_tool_call('elm_read', {'section':hit['section']}))['text'], record['text'])
        proposal = json.loads(manager.handle_tool_call('elm_propose', dict(title='Private proposal',
            text='Amber CHAT_AUTHORED.', domain='work', kind='summary', basis='inference',
            sources=[{'ref':'record:'+record['id'], 'revision':record['revision']}],
            dependencies=[{'id':record['id'], 'revision':record['revision']}])) )
        self.assertEqual(proposal['scope_id'], a['scope_id'])
        self.assertEqual(proposal['state'], 'pending')
        s.approve(proposal['id'], proposal['revision'])
        self.assertEqual({r['id'] for r in s.capture('chat-a')['records']}, {record['id'], proposal['id']})
        self.assertEqual(s.capture('chat-b')['records'], [])
        self.assertEqual([r['id'] for r in s.store.snapshot(workspace)['records']], [record['id']])
        self.assertEqual(s.grants(), [])
        with self.assertRaises(RecordError):
            s.grant(a['scope_id'], workspace, [proposal['id']])

    def test_hidden_typed_dependency_cannot_reappear_in_index_manifest_or_native_fallback(self):
        s, a, b, workspace, allowed = self.prepared()
        hidden = self.record(s, workspace, 'Amber SENSITIVE_SOURCE.', sensitive=True)
        derived = self.record(s, workspace, 'Amber DERIVED_WITH_HIDDEN_DEPENDENCY.',
            dependencies=[{'id':hidden['id'], 'revision':hidden['revision']}],
            sources=[{'ref':'record:'+hidden['id'], 'revision':hidden['revision']}])
        self.opt_in(s)
        manager, provider = self.manager()
        result = json.loads(manager.handle_tool_call('elm_context', {'query':'amber'}))
        self.assertEqual([r['record_id'] for r in result['results']], [allowed['id']],
            'An approved child must not launder a source excluded by typed/sensitive policy')
        self.assertNotIn(hidden['id'], {r['id'] for r in s.capture('chat-a')['records']})
        manifest = json.loads((s._index().root/result['generation']/'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual({r['id'] for r in manifest['records']}, {allowed['id']})
        self.assertNotIn('SENSITIVE_SOURCE', json.dumps(manifest))
        self.assertNotIn(derived['id'], json.dumps(manifest))

    def test_default_isolation_foreign_project_private_member_and_personal_grants(self):
        from hermes_cli import projects_db
        s, a, b, workspace, allowed = self.prepared()
        private = self.record(s, b['scope_id'], 'Amber OTHER_PRIVATE_MEMBER.')
        personal = self.record(s, 'personal', 'Amber PERSONAL_NOT_A_POOL.')
        card = self.record(s, 'personal', 'Amber COMMUNICATION_ONLY.', domain='user',
            kind='preference', topic='communication')
        project = projects_db.create_project(self.projects, name='Foreign synthetic project')
        self.db.create_session('foreign-project', source='desktop')
        projects_db.set_session_project(self.projects, 'foreign-project', project)
        foreign_scope = s.capture('foreign-project')['context']['workspace_scope_id']
        foreign = self.record(s, foreign_scope, 'Amber FOREIGN_PROJECT.')
        pending = self.record(s, workspace, 'Amber NOT_APPROVED.', state='pending')
        generic_user = self.record(s, workspace, 'Amber USER_TOPIC_NOT_COMMUNICATION.', domain='user')
        s.grant('personal', a['scope_id'], [card['id']])
        with self.assertRaises(RecordError):
            s.grant('personal', a['scope_id'], [personal['id']])
        self.assertEqual({r['id'] for r in s.capture('chat-a')['records']}, {card['id']})
        self.opt_in(s)
        manager, provider = self.manager()
        result = json.loads(manager.handle_tool_call('elm_context', {'query':'amber'}))
        self.assertEqual({r['record_id'] for r in result['results']}, {allowed['id'],card['id']})
        self.assertEqual({r['id'] for r in s.capture('chat-b')['records']}, {private['id']})
        self.assertNotIn(allowed['id'], {r['id'] for r in s.capture('foreign-project')['records']})
        self.assertEqual(len(s.grants()), 1)
        for denied in (private,personal,foreign,pending,generic_user):
            self.assertNotIn(denied['text'], json.dumps(result))
        for injected in ({'scope_id':foreign_scope}, {'root':'C:/unrelated'},
                         {'workspace_enabled':True}, {'session_id':'chat-b'}):
            value = json.loads(manager.handle_tool_call('elm_context', {'query':'amber', **injected}))
            self.assertEqual(value.get('error'), 'invalid_arguments')
        self.assertFalse(manager.has_tool('elm_read_policy'))
        self.opt_in(s, False)
        self.assertEqual({r['id'] for r in s.capture('chat-a')['records']}, {card['id']})
        s.revoke('personal', a['scope_id'], [card['id']])
        self.assertEqual(s.capture('chat-a')['records'], [])

    def test_policy_cas_host_identity_and_human_api_reject_pool_root_overrides(self):
        from hermes_cli import projects_db
        s, a, b, workspace, record = self.prepared()
        token = set_hermes_home_override(self.home)
        self.addCleanup(reset_hermes_home_override, token)
        client = self.client()
        payload = dict(session_id='chat-a', workspace_enabled=True,
            expected_identity=s.identity.resolve('chat-a')['fingerprint'], expected_policy_revision=None)
        before = s.store.status()['revision']
        for extra in ({'source_scope':'personal'}, {'workspace_scope_id':workspace}, {'root':'C:/unrelated'}):
            response = client.post('/api/plugins/elm/read-policy', json={**payload, **extra})
            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(s.store.status()['revision'], before)
        for value in (1, 'true', None):
            response = client.post('/api/plugins/elm/read-policy', json={**payload,'workspace_enabled':value})
            self.assertEqual(response.status_code, 400, response.text)
        self.opt_in(s)
        stale = client.post('/api/plugins/elm/read-policy', json=payload)
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertTrue(s.read_policy('chat-a')['workspace_enabled'])
        with self.assertRaises(RecordError):
            s.set_privacy(a['scope_id'], False)
        s.set_privacy(a['scope_id'], True)
        self.assertTrue(s.read_policy('chat-a')['workspace_enabled'])
        self.db.create_session('home-only', source='desktop')
        with self.assertRaises(RecordError):
            self.opt_in(s, session='home-only')
        view = s.read_policy('chat-a')
        other = projects_db.create_project(self.projects, name='Moved synthetic project')
        projects_db.set_session_project(self.projects, 'chat-a', other)
        with self.assertRaises(RecordError) as changed:
            s.set_read_policy('chat-a', False, view['identity'], view['policy_revision'])
        self.assertEqual(changed.exception.code, 'scope_changed')
        self.assertFalse(s.read_policy('chat-a')['membership_current'])
        with self.assertRaises(RecordError):
            s.capture('chat-a')
        self.opt_in(s, False)
        self.assertEqual(s.capture('chat-a')['records'], [])

    def test_stale_index_and_direct_reference_are_denied_even_when_purge_is_held(self):
        s, a, b, workspace, record = self.prepared()
        self.opt_in(s)
        manager, provider = self.manager()
        hit = json.loads(manager.handle_tool_call('elm_context', {'query':'amber'}))['results'][0]
        old = s._index().root/hit['generation']
        with patch.object(s, '_cleanup_index', return_value={'complete':False,'held':[str(old)]}):
            receipt = self.opt_in(s, False)
        self.assertFalse(receipt['index_cleanup']['complete'])
        self.assertTrue(old.exists())
        stale = json.loads(manager.handle_tool_call('elm_read', {'section':hit['section']}))
        self.assertEqual(stale.get('error'), 'section_not_visible', stale)
        self.assertNotIn(record['text'], json.dumps(stale))
        self.assertEqual(json.loads(manager.handle_tool_call('elm_context', {'query':'amber'}))['results'], [])
        self.assertTrue(s._cleanup_index()['complete'])

    def test_policy_revision_change_at_native_publication_withholds_context_read_and_status(self):
        s, a, b, workspace, record = self.prepared()
        self.opt_in(s)
        manager, provider = self.manager()
        module = sys.modules[type(provider).__module__]
        encode = module._bounded_result
        for tool in ('elm_context', 'elm_read', 'elm_status'):
            with self.subTest(tool=tool):
                located = json.loads(manager.handle_tool_call('elm_context', {'query':'amber'}))['results'][0]
                args = {'query':'amber'} if tool == 'elm_context' else {'section':located['section']} if tool == 'elm_read' else {}
                def revoke_and_reenable(*args, **kwargs):
                    self.opt_in(s, False)
                    self.opt_in(s, True)
                    return encode(*args, **kwargs)
                with patch.object(module, '_bounded_result', side_effect=revoke_and_reenable):
                    late = json.loads(manager.handle_tool_call(tool, args))
                self.assertEqual(late.get('error'), 'scope_changed', late)
                self.assertNotIn(record['text'], json.dumps(late))

    def test_host_move_switch_profile_and_foreign_session_withhold_incoming_evidence(self):
        from hermes_cli import projects_db
        s, a, b, workspace, record = self.prepared()
        self.opt_in(s)
        manager, provider = self.manager()
        hit = json.loads(manager.handle_tool_call('elm_context', {'query':'amber'}))['results'][0]
        self.assertEqual(hit['text'], record['text'])
        module = sys.modules[type(provider).__module__]
        encode = module._bounded_result
        other = projects_db.create_project(self.projects, name='Other synthetic workspace')
        def move(*args, **kwargs):
            projects_db.set_session_project(self.projects, 'chat-a', other)
            return encode(*args, **kwargs)
        with patch.object(module, '_bounded_result', side_effect=move):
            late = json.loads(manager.handle_tool_call('elm_read', {'section':hit['section']}))
        self.assertEqual(late.get('error'), 'scope_changed', late)
        self.assertNotIn(record['text'], json.dumps(late))
        self.assertEqual(json.loads(manager.handle_tool_call('elm_context', {'query':'amber'})).get('error'), 'scope_changed')
        manager.on_session_switch('chat-b', reset=True)
        self.assertEqual(json.loads(manager.handle_tool_call('elm_context', {'query':'amber'}))['results'], [])
        self.assertEqual(json.loads(manager.handle_tool_call('elm_read', {'section':hit['section']})).get('error'), 'section_not_visible')
        manager.on_session_switch('absent-session', reset=True)
        self.assertEqual(json.loads(manager.handle_tool_call('elm_context', {'query':'amber'})).get('error'), 'session_unavailable')
        other_home = self.home/'other-synthetic-profile'
        other_home.mkdir()
        token = set_hermes_home_override(other_home)
        try:
            value = json.loads(manager.handle_tool_call('elm_context', {'query':'amber'}))
            self.assertIn('error', value, value)  # MemoryManager refuses before the provider.
            direct = json.loads(provider.handle_tool_call('elm_context', {'query':'amber'}))
            self.assertEqual(direct.get('error'), 'profile_mismatch', direct)
            self.assertNotIn(record['text'], json.dumps(value))
        finally:
            reset_hermes_home_override(token)

    def test_bounded_source_manifest_and_failure_fallback_keep_authority_and_exclusions(self):
        s, a, b, workspace, record = self.prepared()
        record = s.correct(record['id'], record['revision'], dict(kind='interpretation', basis='inference',
            text='Amber provisional source. '*150))
        hidden = self.record(s, b['scope_id'], 'Amber MANIFEST_FOREIGN_PRIVATE.')
        self.opt_in(s)
        manager, provider = self.manager()
        module = sys.modules[type(provider).__module__]
        with patch.object(module, 'MAX_WIRE_CHARS', 4000):
            result = json.loads(manager.handle_tool_call('elm_context', {'query':'amber'}))
        self.assertNotIn('error', result, result)
        hit = result['results'][0]
        self.assertEqual(hit['representation_class'], 'source_manifest')
        self.assertTrue(hit['body_omitted'])
        self.assertEqual((hit['kind'],hit['basis']), ('interpretation','inference'))
        self.assertEqual(hit['memory']['restriction'], 'untrusted_evidence_only_uncertain')
        self.assertNotIn(hidden['text'], json.dumps(result))
        exact = json.loads(manager.handle_tool_call('elm_read', {'section':hit['section']}))
        self.assertEqual(exact['text'], record['text'])
        with patch.object(module, 'MAX_WIRE_CHARS', 50):
            failed = json.loads(manager.handle_tool_call('elm_context', {'query':'amber'}))
        self.assertEqual(failed.get('error'), 'result_too_large', failed)
        self.assertNotIn(record['text'], json.dumps(failed))
        self.assertNotIn(hidden['text'], json.dumps(failed))
        self.assertEqual(manager.prefetch_all('amber', session_id='chat-a'), '')

    def test_policy_revocation_invalidates_dependent_private_records_without_outgoing_grants(self):
        s, a, b, workspace, record = self.prepared()
        self.opt_in(s)
        proposed = s.propose('chat-a', dict(title='Private derived', text='Amber private synthesis.',
            domain='work', kind='summary', basis='inference',
            sources=[{'ref':'record:'+record['id'], 'revision':record['revision']}],
            dependencies=[{'id':record['id'], 'revision':record['revision']}]))
        approved = s.approve(proposed['id'], proposed['revision'])
        self.opt_in(s, False)
        self.assertEqual(s.store.get(proposed['id'])['state'], 'invalidated')
        self.assertEqual(s.capture('chat-a')['records'], [])
        self.opt_in(s, True)
        self.assertEqual({r['id'] for r in s.capture('chat-a')['records']}, {record['id']})
        self.assertEqual(s.grants(), [])
        self.assertEqual(s.capture('chat-b')['records'], [])

    def test_workspace_ingress_does_not_inherit_foreign_record_grants_or_dependencies(self):
        s, a, b, workspace, allowed = self.prepared()
        card = self.record(s, 'personal', 'Amber WORKSPACE_ONLY_COMMUNICATION.', domain='user',
            kind='preference', topic='communication')
        s.grant('personal', workspace, [card['id']])
        derived = self.record(s, workspace, 'Amber DEPENDENCY_NOT_GRANTED_TO_CHAT.', kind='summary', basis='inference',
            sources=[{'ref':'record:'+card['id'], 'revision':card['revision']}],
            dependencies=[{'id':card['id'], 'revision':card['revision']}])
        self.opt_in(s)
        manager, provider = self.manager()
        result = json.loads(manager.handle_tool_call('elm_context', {'query':'amber'}))
        self.assertEqual({r['record_id'] for r in result['results']}, {allowed['id']})
        self.assertNotIn(card['text'], json.dumps(result))
        self.assertNotIn(derived['text'], json.dumps(result))
        # The existing exact communication-card exception still works, but only
        # after a separate individually pinned grant to this very private chat.
        s.grant('personal', a['scope_id'], [card['id']])
        current = s.capture('chat-a')
        self.assertEqual({r['id'] for r in current['records']}, {allowed['id'],card['id'],derived['id']})
        s.revoke('personal', a['scope_id'], [card['id']])
        self.assertEqual({r['id'] for r in s.capture('chat-a')['records']}, {allowed['id']})

    def test_workspace_member_native_read_never_receives_private_chat_authored_records(self):
        s, a, b, workspace, source = self.prepared()
        self.opt_in(s)
        private = self.record(s, a['scope_id'], 'Amber PRIVATE_AUTHORED_NOT_OUTBOUND.')
        s.set_privacy(b['scope_id'], False)
        manager, provider = self.manager('chat-b')
        result = json.loads(manager.handle_tool_call('elm_context', {'query':'amber'}))
        self.assertEqual({r['record_id'] for r in result['results']}, {source['id']})
        self.assertNotIn(private['text'], json.dumps(result))
        self.assertEqual(s.grants(), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
