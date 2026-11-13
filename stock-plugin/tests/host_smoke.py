"""Run with PYTHONPATH=<stock Hermes>:<ELM>. No network or paid calls."""
import tempfile
from pathlib import Path
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from elm_plugin.stock_store import Store,session_key,Denied
from elm_plugin.stock_runtime import Runtime

class LocalContext:
    def session_surface(self):return 'desktop'
    @property
    def llm(self):raise AssertionError('No model calls in smoke test')

with tempfile.TemporaryDirectory() as tmp:
    a,b=Path(tmp)/'home-a',Path(tmp)/'home-b'
    store=Store();runtime=Runtime(LocalContext(),store)
    sid=session_key('chat','desktop')
    token=set_hermes_home_override(a)
    try:
        runtime.command('on',session_id='chat',platform='desktop')
        runtime.command('save user synthetic smoke memory',session_id='chat',platform='desktop')
        assert len(store.records(sid,'synthetic'))==1
        assert (a/'plugin-data'/'elm'/'stock-v1.sqlite3').exists()
    finally:reset_hermes_home_override(token)
    token=set_hermes_home_override(b)
    try:
        try:store.records(sid,'synthetic')
        except Denied:pass
        else:raise AssertionError('Cross-profile grant leaked')
        runtime.command('on',session_id='chat',platform='desktop')
        assert store.records(sid,'synthetic')==[]
    finally:reset_hermes_home_override(token)
    token=set_hermes_home_override(a)
    try:
        assert len(Store().records(sid,'synthetic'))==1
    finally:reset_hermes_home_override(token)
print('PASS: stock public plugin_db, profile switching, no cross-profile grant/data, retained data after reopening; no model calls.')
