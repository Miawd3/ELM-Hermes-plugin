"""Real plugin HTTP handlers with ASGI transport and synthetic host databases.

Direct router qualification, not host authentication/enablement or live Desktop.
"""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from hermes_state import SessionDB


class WorkspaceApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='workspace-api-')
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        db = SessionDB(self.home/'state.db')
        db.create_session('chat-a', source='desktop')
        db.close()
        token = set_hermes_home_override(self.home)
        self.addCleanup(reset_hermes_home_override, token)

    def client(self):
        path = Path(__file__).resolve().parents[1]/'dashboard'/'plugin_api.py'
        self.assertTrue(path.is_file(), 'The native sidebar backend is not implemented')
        name = 'owned_api_test_' + uuid4().hex
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        self.addCleanup(sys.modules.pop, name, None)
        spec.loader.exec_module(module)
        app = FastAPI()
        app.include_router(module.router, prefix='/api/plugins/elm')
        client = TestClient(app)
        self.addCleanup(client.close)
        return client

    def test_actual_http_setup_create_approve_and_readback(self):
        client = self.client()
        prefix = '/api/plugins/elm'
        response = client.get(prefix+'/overview', params={'session_id':'chat-a'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()['setup'])
        refused = client.post(prefix+'/setup', json={'confirm':False})
        self.assertEqual(refused.status_code, 400, refused.text)
        self.assertFalse((self.home/'elm-workspaces').exists())
        setup = client.post(prefix+'/setup', json={'confirm':True})
        self.assertEqual(setup.status_code, 200, setup.text)
        overview = client.get(prefix+'/overview', params={'session_id':'chat-a'}).json()
        record = client.post(prefix+'/record', json=dict(scope_id=overview['selected_scope_id'],
            title='Banner', text='Use indigo banners.', domain='work', kind='explicit_fact',
            basis='explicit_statement', sources=[{'ref':'fictional:brief-1'}]))
        self.assertEqual(record.status_code, 200, record.text)
        created = record.json()['result']
        readback = client.get(prefix+'/overview', params={'session_id':'chat-a'}).json()['records']
        self.assertEqual(readback[0]['id'], created['id'])
        self.assertEqual(readback[0]['state'], 'pending')
        approved = client.post(prefix+f"/records/{created['id']}/approve", json={'expected_revision':created['revision']})
        self.assertEqual(approved.status_code, 200, approved.text)
        readback = client.get(prefix+'/overview', params={'session_id':'chat-a'}).json()['records']
        self.assertEqual(readback[0]['revision'], approved.json()['result']['revision'])
        self.assertEqual(readback[0]['state'], 'approved')
        unknown = client.get(prefix+'/overview', params={'session_id':'missing-chat'})
        self.assertEqual(unknown.status_code, 404, unknown.text)
        self.assertNotIn('indigo', unknown.text)


    def test_http_correction_consent_grants_and_confirmed_deletion(self):
        client = self.client()
        p = '/api/plugins/elm'
        self.assertEqual(client.post(p+'/setup', json={'confirm':True}).status_code, 200)
        current = client.get(p+'/overview', params={'session_id':'chat-a'}).json()
        scope = current['selected_scope_id']
        created = client.post(p+'/record', json=dict(scope_id='personal', title='Communication',
            text='Use short paragraphs.', domain='user', kind='preference', basis='explicit_statement',
            topic='communication', sources=[{'ref':'fictional:preference'}], state='approved')).json()['result']
        changed = client.patch(p+f"/records/{created['id']}", json={'expected_revision':created['revision'],
            'changes':{'text':'Use short paragraphs and clear headings.'}})
        self.assertEqual(changed.status_code, 200, changed.text)
        record = changed.json()['result']
        readback = client.get(p+'/overview', params={'session_id':'chat-a','scope_id':'personal'}).json()['records'][0]
        self.assertEqual((readback['text'],readback['revision']), (record['text'],record['revision']))
        learning = client.post(p+'/learning', json={'enabled':True})
        self.assertEqual(learning.status_code, 200, learning.text)
        self.assertTrue(client.get(p+'/overview', params={'session_id':'chat-a'}).json()['status']['learning_enabled'])
        grant = dict(source_scope='personal', target_scope=scope, record_ids=[record['id']])
        self.assertEqual(client.post(p+'/grants', json=grant).status_code, 200)
        self.assertEqual(client.get(p+'/overview', params={'session_id':'chat-a'}).json()['grants'][0]['record_id'], record['id'])
        self.assertEqual(client.request('DELETE', p+'/grants', json=grant).status_code, 200)
        self.assertEqual(client.get(p+'/overview', params={'session_id':'chat-a'}).json()['grants'], [])
        preview = client.post(p+f"/records/{record['id']}/delete-preview", json={})
        self.assertEqual(preview.status_code, 200, preview.text)
        deleted = client.post(p+f"/records/{record['id']}/delete", json={'preview_token':preview.json()['result']['preview_token']})
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(client.get(p+'/overview', params={'session_id':'chat-a','scope_id':'personal'}).json()['records'], [])
        privacy = client.post(p+'/scopes/privacy', json={'scope_id':scope,'private':False})
        self.assertEqual(privacy.status_code, 200, privacy.text)
        self.assertFalse(client.get(p+'/overview', params={'session_id':'chat-a'}).json()['context']['private'])

    def test_http_profile_is_host_owned_and_malformed_writes_have_no_effect(self):
        client = self.client()
        p = '/api/plugins/elm'
        invalid = client.post(p+'/setup', json={'confirm':True,'hermes_home':'C:/unrelated'})
        self.assertEqual(invalid.status_code, 400, invalid.text)
        self.assertFalse((self.home/'elm-workspaces').exists())
        self.assertEqual(client.post(p+'/setup', content=b'{bad', headers={'Content-Type':'application/json'}).status_code, 400)
        self.assertEqual(client.post(p+'/setup', json={'confirm':True}).status_code, 200)
        current = client.get(p+'/overview', params={'session_id':'chat-a'}).json()
        client.post(p+'/record', json=dict(scope_id=current['selected_scope_id'], title='Fictional private',
            text='indigo-private-first-profile', domain='work', kind='explicit_fact', basis='explicit_statement',
            sources=[{'ref':'fictional:private'}], state='approved'))
        other = self.home/'other-profile'
        other.mkdir()
        db = SessionDB(other/'state.db')
        db.create_session('chat-a', source='desktop')
        db.close()
        token = set_hermes_home_override(other)
        try:
            response = client.get(p+'/overview', params={'session_id':'chat-a'})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertFalse(response.json()['setup'])
            self.assertNotIn('indigo-private-first-profile', response.text)
        finally:
            reset_hermes_home_override(token)
        original = client.get(p+'/overview', params={'session_id':'chat-a'})
        self.assertIn('indigo-private-first-profile', original.text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
