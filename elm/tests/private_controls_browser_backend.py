"""Isolated browser fixture. Real plugin API/stores; native RPC is a labeled stand-in."""
import os, sys, json, uuid
from pathlib import Path
from contextlib import closing
stage=Path(os.environ['PRIVATE_UI_STAGE']).resolve()
assert stage.parent==Path(os.environ['PRIVATE_UI_STAGE_ROOT']).resolve()
assert json.loads((stage/'OWNER.json').read_text())['owner']=='private-controls-browser'
host=Path(os.environ['HERMES_STOCK_SOURCE']).resolve()
deps=Path(os.environ['ELM_TEST_DEPS']).resolve()
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(host),str(deps)]
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import FileResponse,HTMLResponse
from hermes_constants import set_hermes_home_override
from hermes_state import SessionDB
from hermes_cli import projects_db
from elm_plugin.workspace_api import router
from elm_plugin.workspace_service import WorkspaceService
from elm_plugin.private_controls import PrivateControls
from tui_gateway.contracts.canonical_sessions import CanonicalCreateParams
from tui_gateway.contracts.projects_pets import ProjectsCreateParams
home=stage/'home';home.mkdir(exist_ok=True)
assert not (home/'state.db').exists(), 'Never adopt an existing fixture session database'
set_hermes_home_override(home)
with closing(SessionDB(home/'state.db')) as db:db.create_session('a',source='gui')
with closing(projects_db.connect(home/'projects.db')) as db:
    project=projects_db.create_project(db,name='Original fixture project')
    projects_db.set_session_project(db,'a',project)
service=WorkspaceService(home);service.setup(confirm=True)
context=service.capture('a')
service.create_record(dict(scope_id=context['context']['workspace_scope_id'],title='Fictional pool source',text='Amber fixture evidence.',domain='work',kind='explicit_fact',basis='explicit_statement',sources=[{'ref':'fictional:browser'}],state='approved'))
app=FastAPI();app.include_router(router,prefix='/api/plugins/elm')
native_calls=[]
@app.middleware('http')
async def guard(request,call_next):
    if request.url.path not in ('/','/bundle.js') and request.headers.get('x-fixture')!='private-controls-fixture':
        raise HTTPException(403,'Synthetic fixture header required')
    return await call_next(request)
@app.get('/')
def index():
    return HTMLResponse('''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>:root{--ui-text-primary:#e8e9ef;--ui-text-secondary:#b0b8c4}body{margin:0;background:#15171c;color:var(--ui-text-primary);font:16px system-ui}button,input,select{font:inherit;max-width:100%;box-sizing:border-box}input,select,button{background:#252b35;color:inherit;border:1px solid #6a7486;padding:.4rem}input[type=checkbox]{margin-right:.5rem}button{margin:.25rem}fieldset{min-width:0}p{overflow-wrap:anywhere}#fixture-label{padding:.4rem 1.2rem;color:#bcc7dd;font-size:13px}</style><div id="fixture-label">Isolated synthetic fixture — real API/store, native SDK RPC stand-in; not the live app</div><div id="root"></div><script type="module" src="/bundle.js"></script>''')
@app.get('/bundle.js')
def bundle():return FileResponse(stage/'bundle.js',media_type='text/javascript')
@app.post('/fixture/rpc')
async def rpc(request:Request):
    body=await request.json();method=body['method'];p=body['params']
    if method=='model.options':
        return {'providers':[{'slug':'fixture-provider','name':'Synthetic','authenticated':True,'models':['fixture-model'],'unavailable_models':[]}]}
    native_calls.append({'method':method,'params':p})
    if method=='session.create':
        allowed={'request_id','source','project_id','provider','model','follow_profile_config'}
        assert not set(p)-allowed
        CanonicalCreateParams.model_validate(p)
        sid='fixture-'+uuid.uuid4().hex
        with closing(SessionDB(home/'state.db')) as db:db.create_session(sid,source=p['source'],model=p.get('model'))
        if p.get('project_id'):
            with closing(projects_db.connect(home/'projects.db')) as db:projects_db.set_session_project(db,sid,p['project_id'])
        return {'session_id':sid,'stored_session_id':sid,'message_count':0,'messages':[],'info':{'model':p.get('model'),'provider':p.get('provider')}}
    if method=='projects.create':
        ProjectsCreateParams.model_validate(p);assert p['use'] is False and p['create_directory'] is False
        with closing(projects_db.connect(home/'projects.db')) as db:pid=projects_db.create_project(db,name=p['name'])
        return {'project':{'id':pid,'name':p['name']}}
    raise HTTPException(400,'Fixture RPC not allowed')
@app.get('/fixture/snapshot')
def snapshot(session_id:str='a'):
    view=service.read_policy(session_id)
    with closing(SessionDB(home/'state.db',read_only=True)) as db:row=db.get_session_list_row(session_id)
    return {'policy':view,'model_policy':PrivateControls(home).chat_model_policy(session_id),'row':row,'native_calls':native_calls}
if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=int(sys.argv[1]),log_level='error')
