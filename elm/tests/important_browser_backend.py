"""Synthetic real API/store bridge. No host plugin activation or HTTP socket."""
import sys, os, json, socket
from pathlib import Path
host, plugin, dependencies = sys.argv[1:4]
sys.path[:0] = [plugin, host, dependencies]
def guard(event, args):
    if event in ('socket.connect','socket.bind'):
        address=args[1]; frame=sys._getframe(1)
        if (frame.f_code.co_name=='_fallback_socketpair' and
            Path(frame.f_code.co_filename).resolve()==Path(socket.__file__).resolve() and
            isinstance(address,tuple) and address[0] in ('127.0.0.1','::1')): return
        raise RuntimeError('Network forbidden except exact stdlib socketpair')
sys.addaudithook(guard)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from hermes_state import SessionDB
from elm_plugin.result_inbox import publish_important_result
from elm_plugin.product_ui_api import router
home=Path(os.environ['HERMES_HOME']); set_hermes_home_override(home)
with __import__('contextlib').closing(SessionDB(home/'state.db')) as db:
    for sid in ('chat-a','chat-b'): db.create_session(sid, source='desktop')
seed=publish_important_result(current_session_id='chat-a',title='Rollback package · partial',
    body='The package is staged. Signature verification is still blocked.\n\n<script>window.injected=true</script>\n'+('LongIdentifier'*15),kind='partial')
# Existing installed skills, with only the upstream transport replaced. Native
# check/quarantine/scan/install functions remain the real production consumers.
from unittest.mock import patch
from tools.skills_hub import HubLockFile
from tools.skills_hub_models import SkillBundle
from tools.skills_guard import content_hash
skill=home/'skills'/'fictional-owned';skill.mkdir(parents=True)
(skill/'SKILL.md').write_text('---\nname: fictional-owned\ndescription: Synthetic update fixture.\n---\n\nOld harmless prose.\n',encoding='utf-8')
HubLockFile().record_install(name='fictional-owned',source='github',identifier='fictional/repo/fictional-owned',trust_level='community',scan_verdict='safe',skill_hash=content_hash(skill),install_path='fictional-owned',files=['SKILL.md'])
bundle=SkillBundle(name='fictional-owned',files={'SKILL.md':'---\nname: fictional-owned\ndescription: Synthetic update fixture.\n---\n\nNew harmless prose.\n'},source='github',identifier='fictional/repo/fictional-owned',trust_level='community')
class Source:
    def source_id(self):return 'github'
    def fetch(self,identifier):return bundle
transport=patch('tools.skills_hub_search.create_source_router',return_value=[Source()]);transport.start()
manual=home/'plugins'/'manual-fixture';manual.mkdir(parents=True)
(manual/'plugin.yaml').write_text('name: manual-fixture\nversion: 1.0.0\ndescription: Synthetic manual plugin without provenance.\n',encoding='utf-8')
app=FastAPI(); app.include_router(router,prefix='/api/plugins/elm/ui')
c=TestClient(app)
print(json.dumps({'ready':True,'pid':os.getpid(),'seed':seed}),flush=True)
try:
    for line in sys.stdin:
        req=json.loads(line)
        if req.get('control')=='close': break
        try:
            if req.get('control')=='reopen':
                c.close();c=TestClient(app)
                value={'memory_root_exists':(home/'elm-workspaces').exists(),'result':c.get('/api/plugins/elm/ui/results',params={'session_id':'chat-a'}).json()}
                print(json.dumps({'id':req['id'],'status':200,'body':value}),flush=True);continue
            r=c.request(req.get('method','GET'),req['path'],**({'json':req['body']} if req.get('body') is not None else {}))
            print(json.dumps({'id':req['id'],'status':r.status_code,'body':r.json()}),flush=True)
        except Exception as exc:
            print(json.dumps({'id':req['id'],'status':500,'body':{'message':str(exc)}}),flush=True)
finally:c.close()
