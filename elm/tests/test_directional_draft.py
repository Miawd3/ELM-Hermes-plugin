"""Directional drafting through real human HTTP/host bridge; no model inference."""
import json
import unittest
from unittest.mock import patch

import test_directional_policy as policy
import test_workspace_draft_api as draft_api
from elm_plugin.workspace_learning import WorkspaceLearning
from test_workspace_learning import Facade
from elm_plugin.workspace_records import RecordError


class DirectionalDraftTests(unittest.TestCase):
    def setUp(self):
        policy.DirectionalPolicyTests.setUp(self)
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        token = set_hermes_home_override(self.home)
        self.addCleanup(reset_hermes_home_override, token)
    service = policy.DirectionalPolicyTests.service
    record = policy.DirectionalPolicyTests.record
    opt_in = policy.DirectionalPolicyTests.opt_in
    client = policy.DirectionalPolicyTests.client
    prepared = draft_api.WorkspaceDraftApiTests.prepared

    def test_host_bound_draft_can_select_incoming_workspace_but_writes_private_pending(self):
        client, prefix, chat, local = self.prepared()
        s = self.service()
        workspace = s.capture('chat-a')['context']['workspace_scope_id']
        source = self.record(s, workspace, 'Amber incoming source for private synthesis.')
        self.opt_in(s)
        self.assertEqual(client.post(prefix+'/learning', json={'enabled':True}).status_code, 200)
        response = client.post(prefix+'/draft', json=dict(scope_id=chat, record_ids=[source['id']],
            kind='summary', session_id='chat-a'))
        self.assertEqual(response.status_code, 200, response.text)
        drafted = response.json()['result']
        self.assertEqual(drafted['scope_id'], chat)
        self.assertEqual((drafted['state'],drafted['basis']), ('pending','inference'))
        self.assertEqual(drafted['dependencies'], [{'id':source['id'], 'revision':source['revision']}])
        self.assertEqual(len(self.calls), 1)
        self.assertIn(source['text'], json.dumps(self.calls[0]))
        self.assertNotIn(local['text'], json.dumps(self.calls[0]))
        self.assertEqual({r['id'] for r in s.store.snapshot(workspace)['records']}, {source['id']})
        self.assertEqual(s.grants(), [])

    def setup_directional(self):
        s = self.service()
        s.setup(confirm=True)
        a = s.capture('chat-a')
        b = s.capture('chat-b')
        workspace = a['context']['workspace_scope_id']
        source = self.record(s, workspace, 'Amber SELECTED_WORKSPACE_SOURCE.')
        self.opt_in(s)
        s.set_learning(True)
        return s, a, b, workspace, source

    def test_directional_draft_denies_foreign_unapproved_and_hidden_dependencies_before_egress(self):
        s, a, b, workspace, source = self.setup_directional()
        foreign = self.record(s, b['scope_id'], 'Amber FOREIGN_DRAFT_SOURCE.')
        pending = self.record(s, workspace, 'Amber PENDING_DRAFT_SOURCE.', state='pending')
        hidden = self.record(s, workspace, 'Amber SENSITIVE_DRAFT_SOURCE.', sensitive=True)
        child = self.record(s, workspace, 'Amber HIDDEN_CHILD.', kind='summary', basis='inference',
            sources=[{'ref':'record:'+hidden['id'], 'revision':hidden['revision']}],
            dependencies=[{'id':hidden['id'], 'revision':hidden['revision']}])
        for denied in (foreign,pending,hidden,child):
            facade = Facade()
            with self.subTest(record=denied['id']), self.assertRaises(RecordError):
                WorkspaceLearning(s, facade).draft(a['scope_id'], [denied['id']], 'summary', session_id='chat-a')
            self.assertEqual(facade.calls, [])
        for kwargs in ({}, {'session_id':'chat-b'}):
            facade = Facade()
            with self.assertRaises(RecordError):
                WorkspaceLearning(s, facade).draft(a['scope_id'], [source['id']], 'summary', **kwargs)
            self.assertEqual(facade.calls, [])
        self.assertEqual(s.grants(), [])

    def test_policy_revoke_reenable_during_wait_discards_draft_even_with_same_visible_sources(self):
        s, a, b, workspace, source = self.setup_directional()
        def change():
            self.opt_in(s, False)
            self.opt_in(s, True)
        facade = Facade(callback=change)
        before = s.store.list_records(a['scope_id'])
        with self.assertRaises(RecordError) as refused:
            WorkspaceLearning(s, facade).draft(a['scope_id'], [source['id']], 'summary', session_id='chat-a')
        self.assertEqual(refused.exception.code, 'draft_stale')
        self.assertEqual(s.store.list_records(a['scope_id']), before)
        self.assertEqual(len(facade.calls), 1)
        self.assertFalse((s.base/'generation-receipts').exists())

    def test_host_membership_change_during_wait_discards_incoming_draft(self):
        from hermes_cli import projects_db
        s, a, b, workspace, source = self.setup_directional()
        other = projects_db.create_project(self.projects, name='Moved while drafting')
        def move():
            projects_db.set_session_project(self.projects, 'chat-a', other)
        facade = Facade(callback=move)
        with self.assertRaises(RecordError):
            WorkspaceLearning(s, facade).draft(a['scope_id'], [source['id']], 'summary', session_id='chat-a')
        self.assertEqual(s.store.list_records(a['scope_id']), [])
        self.assertEqual(len(facade.calls), 1)
        self.assertFalse((s.base/'generation-receipts').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
