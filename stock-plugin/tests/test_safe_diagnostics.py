"""No pre-grant diagnostic may open a DB or reveal stored/profile data."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from elm_plugin.stock_runtime import Runtime, HELP
from elm_plugin.stock_store import Store

class Context:
    def session_surface(self): raise AssertionError('no extra host lookup')

class SafeDiagnosticsTests(unittest.TestCase):
    def test_missing_storage_never_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'absent'/'db'
            def forbidden():
                path.parent.mkdir()
                raise AssertionError('connection factory invoked')
            runtime=Runtime(Context(),Store(forbidden))
            for command in ('', 'help', 'diagnostics', '"', None, {}):
                runtime.command(command,session_id='current',platform='local')
                self.assertFalse(path.parent.exists())

    def test_static_help_independent_of_context(self):
        def forbidden(): raise AssertionError('storage touched')
        runtime=Runtime(Context(),Store(forbidden))
        for platform in ('local','discord','gui','',None,{}):
            for sid in ('',None,'secret_session', 'x'*513):
                self.assertEqual(runtime.command('help',session_id=sid,platform=platform),HELP)
                data=json.loads(runtime.command('diagnostics',session_id=sid,platform=platform))
                self.assertEqual(data['authorization'],'not_checked')
                self.assertEqual(data['storage'],'not_opened')
                self.assertNotIn('secret_session',json.dumps(data))

    def test_states_never_read_or_changed_and_no_private_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths=[Path(tmp)/'profile-a.db',Path(tmp)/'profile-b.db']
            stores=[Store(lambda p=p:sqlite3.connect(p)) for p in paths]
            store=stores[0]
            for state in ('valid','expired','revoked','wrong_profile','malformed'):
                store.grant_local('secret_session',project='hidden-project',user=True,capture=True)
                if state=='expired':
                    with store.open() as db: db.execute('UPDATE stock_local_grants SET expires=0')
                elif state=='revoked':
                    store.settings(store.require_local_grant('secret_session'),{'enabled':False})
                elif state=='wrong_profile':
                    stores[1].grant_local('different_chat')
                elif state=='malformed':
                    paths[0].write_bytes(b'not a sqlite file private contents')
                target=stores[1] if state=='wrong_profile' else store
                before={p:p.read_bytes() for p in paths if p.exists()}
                calls=[]
                original=target.connection
                def watched():
                    calls.append(True)
                    return original()
                runtime=Runtime(Context(),Store(watched))
                result=runtime.command('diagnostics',session_id='secret_session',platform='local')
                self.assertEqual(calls,[])
                self.assertEqual(json.loads(result)['authorization'],'not_checked')
                self.assertFalse(any(secret in result for secret in ('hidden-project','secret_session','different_chat','profile-a','private contents')))
                self.assertEqual(before,{p:p.read_bytes() for p in paths if p.exists()})
                if state=='malformed': paths[0].unlink()

    def test_memory_routes_still_require_grant(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime=Runtime(Context(),Store(lambda:sqlite3.connect(Path(tmp)/'db')))
            for command in ('status','list','save reference secret','help extra','diagnostics extra','off'):
                result=runtime.command(command,session_id='a',platform='local')
                self.assertIn('exact_session_cli_grant_required',result)
