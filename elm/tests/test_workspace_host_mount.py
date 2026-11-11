"""Actual stock host dashboard assembly/mounter/auth, in-process ASGI only.

Uses the supported loopback dashboard session-token scheme, not an overridden
identity dependency. TestClient is deliberately NOT entered as a context manager:
server lifespan launches services and is outside this offline qualification.
The secondary synthetic profile disables ELM; its supported refusal is tested,
not misrepresented as successful secondary plugin-host execution.
"""
import json
import os
from pathlib import Path
import shutil
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from hermes_state import SessionDB


class WorkspaceHostMountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = Path(os.environ['HERMES_HOME']).resolve()
        cls.stage = cls.home.parent
        owned_current=('elm-comparison-ui-v1' in cls.stage.parts
                       and (cls.stage/'OWNER.json').is_file()
                       and json.loads((cls.stage/'OWNER.json').read_text())=={
                           'owner':'elm-comparison-ui-v1','label':cls.stage.name,
                           'purpose':'credential-free synthetic test profile'})
        if not ('elm-productization-20261110' in cls.stage.parts or owned_current) or not cls.stage.name.startswith('host-mount-'):
            raise RuntimeError('Requires the owned offline product runner with fresh host-mount label')
        cls.source = Path(__file__).resolve().parents[1]
        cls.installed = cls.home / 'plugins' / 'elm'
        cls.installed.mkdir(parents=True)
        # Only this API's Python package + dashboard manifest/entry, no corpus or host tree.
        for relative in ('elm_plugin', 'dashboard'):
            for src in (cls.source / relative).rglob('*'):
                if src.is_file() and (src.suffix == '.py' or src.name == 'manifest.json'):
                    dest = cls.installed / src.relative_to(cls.source)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, dest)
        (cls.home / 'config.yaml').write_text('plugins:\n  enabled: [elm]\n  disabled: []\n  isolation: in_process\n', encoding='utf-8')
        cls.other = cls.home / 'profiles' / 'synthetic-b'
        cls.other.mkdir(parents=True)
        (cls.other / 'config.yaml').write_text('plugins:\n  enabled: []\n  disabled: [elm]\n  isolation: in_process\n', encoding='utf-8')
        for home in (cls.home, cls.other):
            db = SessionDB(home / 'state.db')
            db.create_session('same-durable-chat', source='desktop')
            db.create_session('other-durable-chat', source='desktop')
            db.close()
        # This imports the REAL host app; its import-time sweep discovers and
        # mounts the synthetic installed candidate using _mount_one_plugin_api.
        from hermes_cli import web_server, web_server_dashboard
        cls.host = web_server
        cls.dashboard = web_server_dashboard
        cls.app = web_server.app
        cls.app.state.bound_host = '127.0.0.1'
        cls.app.state.auth_required = False
        cls.plugin = next(p for p in web_server._get_dashboard_plugins() if p['name'] == 'elm')
        if Path(cls.plugin['_dir']).resolve() != (cls.installed / 'dashboard').resolve():
            raise AssertionError('Host discovery did not select the owned candidate')

    def client(self):
        client = TestClient(self.app, base_url='http://127.0.0.1')
        self.addCleanup(client.close)
        return client

    def test_important_results_use_actual_host_auth_and_profile_scope(self):
        c=self.client();p='/api/plugins/elm/ui';sid='same-durable-chat'
        body={'session_id':sid,'title':'Synthetic important result','body':'HOST_AUTH_FIXTURE_BODY','kind':'partial'}
        for headers in ({},{'X-Hermes-Session-Token':'definitely-invalid'}):
            self.assertEqual(c.post(p+'/results',json=body,headers=headers).status_code,401)
            self.assertEqual(c.get(p+'/results',params={'session_id':sid},headers=headers).status_code,401)
        headers={'X-Hermes-Session-Token':self.host._SESSION_TOKEN}
        made=c.post(p+'/results',json=body,headers=headers);self.assertEqual(made.status_code,200,made.text)
        result_id=made.json()['result']['id']
        own=c.get(p+'/results/'+result_id,params={'session_id':sid},headers=headers)
        self.assertEqual(own.status_code,200);self.assertEqual(own.json()['result']['body'],body['body'])
        other=c.get(p+'/results/'+result_id,params={'session_id':'other-durable-chat'},headers=headers)
        self.assertEqual(other.status_code,200);self.assertFalse(other.json()['exists'])
        secondary=c.get(p+'/results/'+result_id,params={'session_id':sid,'profile':'synthetic-b'},headers=headers)
        self.assertIn(secondary.status_code,(403,404));self.assertNotIn(body['body'],secondary.text)
        self.assertFalse((self.other/'elm-product-ui').exists())

    def test_actual_host_mount_authentication_and_request_profile_boundary(self):
        c = self.client()
        p = '/api/plugins/elm'
        home = self.home
        self.assertEqual(self.plugin['source'], 'user')
        self.assertTrue(self.dashboard._plugin_api_mounted(self.app, 'elm'))
        # Route scope dependency must be the host's actual dependency, not one
        # recreated by this test. No include_router is used anywhere here.
        routes = [r for r in self.app.routes if getattr(r, 'path', '').startswith(p + '/')]
        setup_route = next(r for r in routes if r.path == p + '/setup')
        self.assertIn(self.dashboard._plugin_route_secret_scope,
                      [d.call for d in setup_route.dependant.dependencies])
        self.assertFalse(self.app.dependency_overrides)
        self.assertFalse((home / 'elm-workspaces').exists())
        # Missing/wrong credentials, body parsing and profile/plugin-name probes
        # must all be refused before creating the store or reaching handlers.
        for headers in ({}, {'X-Hermes-Session-Token': 'definitely-invalid'},
                        {'Authorization': 'Bearer definitely-invalid'}):
            for method, path, kwargs in (
                ('POST', p + '/setup', {'json': {'confirm': True}}),
                ('GET', p + '/overview?session_id=same-durable-chat', {}),
                ('POST', p + '/record', {'json': {'scope_id': 'personal'}}),
                ('POST', p + '/setup?profile=synthetic-b', {'content': b'{invalid'}),
                ('POST', '/api/plugins/unknown-plugin/setup', {'json': {'confirm': True}}),
            ):
                with self.subTest(auth=bool(headers), method=method, path=path):
                    r = c.request(method, path, headers=headers, **kwargs)
                    self.assertEqual(r.status_code, 401, r.text)
                    self.assertFalse((home / 'elm-workspaces').exists())
                    self.assertFalse((self.other / 'elm-workspaces').exists())
        # Use the real host-minted process session token. Never persisted or logged.
        headers = {'X-Hermes-Session-Token': self.host._SESSION_TOKEN}
        r = c.get(p + '/overview', params={'session_id': 'same-durable-chat'}, headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()['setup'])
        r = c.post(p + '/setup', json={'confirm': True}, headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        r = c.get(p + '/overview', params={'session_id': 'same-durable-chat'}, headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        overview = r.json()
        self.assertTrue(overview['setup'])
        self.assertEqual(overview['context']['session_id'], 'same-durable-chat')
        record = dict(scope_id=overview['selected_scope_id'], title='Fictional host secret',
                      text='synthetic-indigo-profile-A-only', domain='work', kind='explicit_fact',
                      basis='explicit_statement', sources=[{'ref': 'fictional:host-mount'}])
        r = c.post(p + '/record', json=record, headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        created = r.json()['result']
        r = c.get(p + '/overview', params={'session_id': 'same-durable-chat'},
                  headers={'Authorization': 'Bearer ' + self.host._SESSION_TOKEN})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([(x['id'], x['revision'], x['text']) for x in r.json()['records']],
                         [(created['id'], created['revision'], record['text'])])
        before = self.snapshot(home / 'elm-workspaces')
        # Actual named-profile resolution and enablement checks. B has the same
        # durable session ID but withholds plugin consent; never bypass routing
        # by pretending a user plugin is bundled or faking a profile dependency.
        for method, path, kwargs in (
            ('GET', p + '/overview', {'params': {'session_id': 'same-durable-chat', 'profile': 'synthetic-b'}}),
            ('POST', p + '/setup?profile=synthetic-b', {'json': {'confirm': True}}),
            ('POST', p + '/record?profile=synthetic-b', {'json': record}),
        ):
            r = c.request(method, path, headers=headers, **kwargs)
            self.assertEqual(r.status_code, 404, r.text)
            self.assertNotIn(record['text'], r.text)
            self.assertFalse((self.other / 'elm-workspaces').exists())
        self.assertEqual(before, self.snapshot(home / 'elm-workspaces'))
        # Returning to A proves the named request scope did not stick globally.
        r = c.get(p + '/overview', params={'session_id': 'same-durable-chat'}, headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['records'][0]['id'], created['id'])
        self.assertIn(record['text'], r.text)
        r = c.get(p + '/overview', params={'session_id': 'not-in-host-db'}, headers=headers)
        self.assertEqual(r.status_code, 404, r.text)
        self.assertNotIn(record['text'], r.text)
        # A later unauthenticated write cannot mutate an already populated store.
        r = c.post(p + '/record', json=record)
        self.assertEqual(r.status_code, 401, r.text)
        self.assertEqual(before, self.snapshot(home / 'elm-workspaces'))

    @staticmethod
    def snapshot(root):
        return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}

    def test_actual_mounter_refuses_unenabled_disabled_and_project_sources(self):
        for source, enabled, disabled in (
            ('user', set(), set()), ('user', {'elm'}, {'elm'}), ('project', {'elm'}, set())
        ):
            with self.subTest(source=source, enabled=enabled, disabled=disabled):
                app = FastAPI()
                plugin = dict(self.plugin, source=source)
                self.assertFalse(self.dashboard._mount_one_plugin_api(app, plugin, enabled, disabled))
                self.assertFalse(self.dashboard._plugin_api_mounted(app, 'elm'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
