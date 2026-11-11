"""Real profile store for explicit future-container settings; no model calls."""
import importlib
import unittest
import test_product_ui_api as product_api


class PrivateControlsTests(unittest.TestCase):
    setUp = product_api.ProductResultsTests.setUp
    modules = product_api.ProductResultsTests.modules
    client = product_api.ProductResultsTests.client

    def test_future_defaults_persist_separately_without_memory_initialization(self):
        try:
            module = importlib.import_module('elm_plugin.private_controls')
        except ModuleNotFoundError as exc:
            if exc.name == 'elm_plugin.private_controls':
                self.fail('Future private-container defaults have no authoritative store')
            raise
        store = module.PrivateControls(self.home)
        before = store.read('chat-a')
        self.assertFalse((self.home/'elm-product-ui').exists())
        self.assertFalse(before['settings']['private_chat']['workspace_reads'])
        self.assertTrue(before['settings']['private_workspace']['workspace_reads'])
        settings = before['settings']
        settings['private_chat']['workspace_reads'] = True
        saved = store.save('chat-a', before['revision'], settings)
        self.assertGreater(saved['revision'], before['revision'])
        self.assertEqual(store.read('chat-b'), saved)
        self.assertFalse((self.home/'elm-workspaces').exists())
        self.assertIsNone(store.chat_model_policy('chat-a'))

    def test_cas_rejects_stale_defaults_and_never_replaces_bound_chat(self):
        from elm_plugin.private_controls import PrivateControls
        from elm_plugin.result_inbox import InboxError
        s = PrivateControls(self.home)
        initial = s.read('chat-a')
        bound = s.bind_chat_model_policy('chat-a', initial['settings'])
        changed = initial['settings']
        changed['private_chat']['workspace_reads'] = True
        s.save('chat-a', 1, changed)
        with self.assertRaises(InboxError): s.save('chat-b', 1, changed)
        with self.assertRaises(InboxError): s.bind_chat_model_policy('chat-a', changed)
        self.assertEqual(s.chat_model_policy('chat-a'), bound)
        self.assertIsNone(s.chat_model_policy('chat-b'))

    def test_real_human_api_readback_cap_refusal_and_authority_field_rejection(self):
        c = self.client(); root = '/api/plugins/elm/ui/private'
        before = c.get(root, params={'session_id':'chat-a'})
        self.assertEqual(before.status_code, 200, before.text)
        data = before.json(); self.assertFalse(data['memory_setup'])
        body = dict(session_id='chat-a', expected_revision=1, settings=data['settings'])
        saved = c.post(root+'/defaults', json=body)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(c.get(root,params={'session_id':'chat-b'}).json()['settings'], saved.json()['result']['settings'])
        self.assertEqual(c.post(root+'/defaults', json=body).status_code, 409)
        body['expected_revision'] = 2; body['settings']['cap_enabled'] = True
        self.assertEqual(c.post(root+'/defaults', json=body).json()['code'], 'unsupported_cap')
        self.assertFalse(c.get(root,params={'session_id':'chat-a'}).json()['settings']['cap_enabled'])
        body['home'] = 'C:/fictional'
        self.assertEqual(c.post(root+'/defaults',json=body).status_code,400)
        self.assertFalse((self.home/'elm-workspaces').exists())

    def test_corrupt_settings_and_unknown_nested_fields_fail_closed(self):
        import sqlite3
        from contextlib import closing
        from elm_plugin.private_controls import PrivateControls
        from elm_plugin.result_inbox import InboxError
        s = PrivateControls(self.home); data = s.read('chat-a')['settings']
        data['private_chat']['conversation']['home']='no'
        with self.assertRaises(InboxError): s.save('chat-a',1,data)
        self.assertFalse((self.home/'elm-product-ui').exists())
        data=s.read('chat-a')['settings']; s.save('chat-a',1,data)
        with closing(sqlite3.connect(s.path)) as db:
            db.execute("UPDATE private_defaults SET payload='{}'");db.commit()
        with self.assertRaises(InboxError): s.read('chat-a')

    def test_two_concurrent_cas_writes_have_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        from elm_plugin.private_controls import PrivateControls
        from elm_plugin.result_inbox import InboxError
        s=PrivateControls(self.home);data=s.read('chat-a')['settings'];s.save('chat-a',1,data)
        def save():
            try:return s.save('chat-a',2,data)['revision']
            except InboxError as e:return e.code
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(lambda _:save(),range(2)))
        self.assertCountEqual(results,[3,'revision_conflict'])
