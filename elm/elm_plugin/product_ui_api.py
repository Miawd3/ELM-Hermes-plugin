"""Human-only product UI router; owner mounts at /ui in authenticated plugin API.

Authentication/profile middleware belongs to the host. get_hermes_home is its
request-scoped accessor. Do not expose this human router as an agent tool.
"""
import json
import re
import shutil
import threading
import sqlite3
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from hermes_constants import get_hermes_home
from .host_identity import IdentityError
from .result_inbox import ResultInbox, InboxError

router = APIRouter()


def endpoint(method, required, *, action=None, target=False):
    async def handler(request: Request):
        try:
            values = await payload(request, required)
        except InboxError as exc:
            return failure(exc)
        if target:
            values['result_id'] = request.path_params['result_id']
        if action:
            values['action'] = action
        result = await run_in_threadpool(invoke, method, **values)
        return result if isinstance(result, JSONResponse) else {'ok':True, 'result':result}
    return handler


for _action in ('view','read','dismiss','restore'):
    router.add_api_route('/results/{result_id}/'+_action,
        endpoint('mutate', {'session_id','expected_revision'}, action=_action, target=True), methods=['POST'])
router.add_api_route('/results/{result_id}',
    endpoint('mutate', {'session_id','expected_revision'}, action='delete', target=True), methods=['DELETE'])
router.add_api_route('/attention',
    endpoint('set_attention', {'session_id','expected_revision','mode','updates_visible'}), methods=['POST'])


@router.get('/attention')
def attention(session_id: str):
    return invoke('attention', session_id=session_id)



def failure(exc):
    code = getattr(exc, 'code', 'ui_storage_error')
    status = (404 if code in ('session_unavailable','project_unavailable','result_not_found','creation_not_found') else
              403 if code == 'sharing_denied' else
              409 if code in ('creation_refused','unsupported_cap','already_bound','store_busy','operation_busy','not_initialized') else
              409 if code in ('revision_conflict','scope_changed','unowned_ui_root','result_limit','publication_unconfirmed','update_refused','update_review_required','update_unconfirmed') else
              503 if code in ('ui_storage_error','invalid_ui_schema','host_metadata_unavailable','corrupt_settings') else 400)
    return JSONResponse({'ok':False, 'code':code, 'message':str(exc) if hasattr(exc,'code') else
                         'Product UI storage is unavailable; reconcile an uncertain write before retrying.'}, status_code=status)


def invoke(method, **values):
    try:
        return getattr(ResultInbox(get_hermes_home()), method)(**values)
    except (InboxError, IdentityError, OSError, sqlite3.Error) as exc:
        return failure(exc)


def private_invoke(method, **values):
    from .private_creation import PrivateCreation
    from .workspace_records import RecordError
    try:
        return getattr(PrivateCreation(get_hermes_home()), method)(**values)
    except (InboxError, IdentityError, RecordError, OSError, sqlite3.Error) as exc:
        return failure(exc)


@router.get('/private')
def private_overview(session_id: str):
    return private_invoke('overview', session_id=session_id)


@router.get('/private/status')
def private_creation_status(session_id: str, intent_id: str):
    return private_invoke('status', session_id=session_id, intent_id=intent_id)


def private_endpoint(method, fields):
    async def handler(request: Request):
        try:
            values = await payload(request, fields)
        except InboxError as exc:
            return failure(exc)
        result = await run_in_threadpool(private_invoke, method, **values)
        return result if isinstance(result, JSONResponse) else {'ok':True,'result':result}
    return handler


router.add_api_route('/private/defaults', private_endpoint('save', {'session_id','expected_revision','settings'}), methods=['POST'])
router.add_api_route('/private/create', private_endpoint('begin', {'session_id','kind','project_id','name','expected_revision'}), methods=['POST'])
router.add_api_route('/private/finish', private_endpoint('finish', {'session_id','intent_id','created_id'}), methods=['POST'])
router.add_api_route('/private/abandon', private_endpoint('abandon', {'session_id','intent_id','confirm'}), methods=['POST'])


async def payload(request, required, optional=()):
    body = bytearray()
    async for chunk in request.stream():
        if len(body)+len(chunk) > 500000:
            raise InboxError('invalid_payload', 'Product UI request exceeds 500000 bytes')
        body.extend(chunk)
    try:
        value = json.loads(body)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise InboxError('invalid_payload', 'A JSON object is required') from exc
    if not isinstance(value, dict) or not set(required) <= value.keys() or not value.keys() <= set(required)|set(optional):
        raise InboxError('invalid_payload', 'Missing or unsupported fields; profile and filesystem roots cannot be supplied')
    return value


@router.get('/results')
def results(session_id: str, limit: int = 50, cursor: str | None = None, include_dismissed: bool = False):
    return invoke('list', session_id=session_id, limit=limit, cursor=cursor, include_dismissed=include_dismissed)


@router.get('/results/{result_id}')
def result(result_id: str, session_id: str):
    return invoke('get', session_id=session_id, result_id=result_id)


@router.post('/results')
async def publish(request: Request):
    try:
        values = await payload(request, {'session_id','title','body','kind'})
    except InboxError as exc:
        return failure(exc)
    result = await run_in_threadpool(invoke, 'publish', **values)
    return result if isinstance(result, JSONResponse) else {'ok':True, 'result':result}


_UPDATE_LOCK = threading.Lock()
_SELECTION_KEYS = {'type','name','source','identifier','current','target','status','selectable','detail'}


class NativeUpdates:
    """Native check/scan/publication only; no force, new packs or capability grants."""
    def __init__(self, home, session_id):
        self.home=home.resolve();self.session_id=session_id
        self.context=ResultInbox(home).identity.resolve(session_id)

    def scope(self):
        if get_hermes_home().resolve()!=self.home or ResultInbox(self.home).identity.resolve(self.session_id)['fingerprint']!=self.context['fingerprint']:
            raise InboxError('scope_changed','Host profile/chat changed during update')

    @staticmethod
    def skill_path(entry, name):
        from tools.skills_hub_install import _resolve_lock_install_path
        from tools.skills_guard import content_hash
        if not entry:raise InboxError('update_refused','Not an installed skill')
        p=_resolve_lock_install_path(entry.get('install_path',''),name)
        if not re.fullmatch('sha256:[0-9a-f]{16}',entry.get('content_hash','')) or not p.is_dir() or content_hash(p)!=entry['content_hash']:
            raise InboxError('update_refused','Local edits or unknown installed hash; nothing will be overwritten')
        return p

    def check(self):
        self.scope();rows=[];errors=[]
        try:
            from tools.skills_hub import HubLockFile
            from tools.skills_hub_install import check_for_skill_updates
            lock=HubLockFile()
            for r in check_for_skill_updates(lock=lock):
                entry=lock.get_installed(r['name']);detail=''
                try:self.skill_path(entry,r['name']);owned=True
                except (ValueError,OSError) as exc:owned=False;detail=str(exc)
                status=r.get('status','unknown')
                rows.append(dict(type='skill',name=r['name'],source=r.get('source',''),identifier=r.get('identifier',''),
                    current=r.get('current_hash') or (entry or {}).get('content_hash',''),target=r.get('latest_hash',''),status=status,
                    selectable=bool(owned and status=='update_available' and re.fullmatch('sha256:[0-9a-f]{16}',r.get('latest_hash',''))),
                    detail=detail or ('' if status in ('update_available','up_to_date') else 'Native source unavailable; not evidence of being current.')))
        except Exception as exc:errors.append({'type':'skill','message':str(exc)})
        self.scope()
        return {'schema':1,'context':ResultInbox._context(self.context),'rows':rows,'errors':errors,
            'plugin_updates':'disabled_in_catalog_build',
            'policy':'Explicit existing skills only; no force, new packs, auto-update changes or capability grants. Plugin updates are disabled; use Hermes native plugin controls and reviewed catalog pins.'}

    def apply(self, selection):
        if isinstance(selection,dict) and selection.get('type')=='plugin':
            raise InboxError('update_refused','Plugin updates are disabled in this catalog build; use Hermes native plugin controls.')
        if not isinstance(selection,dict) or set(selection)!=_SELECTION_KEYS or selection.get('type') != 'skill' or not isinstance(selection.get('name'),str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',selection['name']):
            raise InboxError('invalid_payload','An exact checked installed-item selection is required')
        if not _UPDATE_LOCK.acquire(blocking=False):raise InboxError('update_refused','An update is already in progress')
        try:
            fresh=[r for r in self.check()['rows'] if r['type']==selection['type'] and r['name']==selection['name']]
            if len(fresh)!=1 or not fresh[0]['selectable'] or any(fresh[0][k]!=selection[k] for k in ('type','name','source','identifier','current','target')):
                raise InboxError('update_refused','Selected update is stale, locally edited, unavailable or not installed. Check again; nothing applied.')
            self.scope()
            observed=self.skill(selection)
            self.scope()
            return {k:selection[k] for k in ('type','name','current','target')}|{'observed':observed,'status':'updated',
                'detail':'Native installed skill content hash verified.'}
        finally:_UPDATE_LOCK.release()

    def skill(self, selection):
        from tools.skills_hub import HubLockFile
        from tools.skills_hub_install import check_for_skill_updates,bundle_content_hash,quarantine_bundle,install_from_quarantine
        from tools.skills_guard import scan_skill,should_allow_install,content_hash
        name=selection['name'];lock=HubLockFile();entry=lock.get_installed(name);path=self.skill_path(entry,name)
        matches=check_for_skill_updates(name=selection['name'],lock=lock)
        bundle=matches[0].get('bundle') if len(matches)==1 else None
        if bundle is None or bundle.name!=name or bundle.source!=entry['source'] or bundle.identifier!=entry['identifier'] or bundle_content_hash(bundle)!=selection['target']:
            raise InboxError('update_refused','Upstream changed after inspection; select again')
        q=quarantine_bundle(bundle)
        try:
            scan=scan_skill(q,source=bundle.source);allowed,reason=should_allow_install(scan,force=False)
            if not allowed:raise InboxError('update_review_required',f'Native scan refused {scan.verdict}: {reason}. No force is offered here.')
            if content_hash(q)!=selection['target']:raise InboxError('update_refused','Staged bytes changed')
            self.scope()
            if lock.get_installed(name)!=entry:raise InboxError('update_refused','Installed metadata changed')
            self.skill_path(entry,name)
            category=path.parent.relative_to(self.home/'skills').as_posix()
            installed=install_from_quarantine(q,name,'' if category=='.' else category,bundle,scan)
            observed=HubLockFile().get_installed(name)
            if not observed or observed['content_hash']!=selection['target'] or content_hash(installed)!=selection['target']:
                raise InboxError('update_unconfirmed','Native write returned but exact installed hash is unconfirmed; do not repeat')
            return observed['content_hash']
        finally:
            if q.exists():shutil.rmtree(q)

@router.get('/updates/installed')
def update_installed(session_id: str, type: str, name: str):
    try:
        service=NativeUpdates(get_hermes_home(),session_id)
        if type=='plugin':
            raise InboxError('update_refused','Plugin update inspection is disabled in this catalog build.')
        if type != 'skill' or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',name):
            raise InboxError('invalid_payload','A literal installed item type/name is required')
        if type=='skill':
            from tools.skills_hub import HubLockFile
            from tools.skills_guard import content_hash
            observed=content_hash(service.skill_path(HubLockFile().get_installed(name),name))
        service.scope()
        return {'schema':1,'context':ResultInbox._context(service.context),'type':type,'name':name,'observed':observed}
    except (InboxError,IdentityError,OSError) as exc:return failure(exc)


@router.post('/updates/check')
async def updates_check(request: Request):
    try:
        values=await payload(request,{'session_id'})
        return await run_in_threadpool(lambda:NativeUpdates(get_hermes_home(),**values).check())
    except (InboxError,IdentityError,OSError) as exc:return failure(exc)


@router.post('/updates/apply')
async def updates_apply(request: Request):
    try:
        values=await payload(request,{'session_id','selection'});selection=values.pop('selection')
        result=await run_in_threadpool(lambda:NativeUpdates(get_hermes_home(),**values).apply(selection))
        return {'ok':True,'result':result}
    except (InboxError,IdentityError,OSError) as exc:return failure(exc)
