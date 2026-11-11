"""Human-only namespaced HTTP API. The host owns authentication and profile scope.

Never expose these approval/share/correction handlers as model tools. Profile
and root arguments are not accepted in bodies; get_hermes_home() is the host's
request-scoped public accessor, not a UI inspector or model-provided value.
"""
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from hermes_constants import get_hermes_home

from .workspace_service import WorkspaceService, ServiceError
from .workspace_records import RecordError
from .host_identity import IdentityError
from .engine import ElmError
from .workspace_index import IndexError as WorkspaceIndexError
from .product_ui_api import router as product_ui_router

router = APIRouter()
router.include_router(product_ui_router, prefix='/ui')
_ERRORS = (RecordError, IdentityError, ElmError, WorkspaceIndexError)
_MAX_BODY = 2097152


def failure(exc):
    code = exc.code
    if code in {'session_unavailable','project_unavailable','record_not_found','scope_not_found'}:
        status = 404
    elif code in {'sharing_denied'}:
        status = 403
    elif code in {'already_initialized','not_initialized','scope_changed','store_busy','operation_busy',
                  'revision_conflict','stale_preview','privacy_broadening_denied','unowned_root'}:
        status = 409
    elif code in {'storage_error','corrupt_store','settings_unavailable','host_metadata_unavailable',
                  'index_build_failed','index_validation_failed','corrupt_index'}:
        status = 503
    else:
        status = 400
    return JSONResponse({'code':code, 'message':str(exc), 'detail':str(exc)}, status_code=status)


def invoke(method, *args, **kwargs):
    try:
        service = WorkspaceService(get_hermes_home())
        return {'ok': True, 'result':getattr(service, method)(*args, **kwargs)}
    except _ERRORS as exc:
        return failure(exc)
    except OSError:
        return failure(ServiceError('storage_error', 'Memory storage is unavailable; the write outcome must be reconciled'))


@router.get('/overview')
def overview(session_id: str, scope_id: str | None = None):
    try:
        return WorkspaceService(get_hermes_home()).overview(session_id, scope_id)
    except _ERRORS as exc:
        return failure(exc)
    except OSError:
        return failure(ServiceError('storage_error', 'Memory storage is unavailable'))


@router.get('/read-policy')
def read_policy(session_id: str):
    try:
        return WorkspaceService(get_hermes_home()).read_policy(session_id)
    except _ERRORS as exc:
        return failure(exc)
    except OSError:
        return failure(ServiceError('storage_error', 'Memory storage is unavailable'))


async def payload(request, required, optional):
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > _MAX_BODY:
            raise ServiceError('invalid_payload', 'Memory request exceeds the two-megabyte limit')
        body.extend(chunk)
    try:
        value = json.loads(body)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ServiceError('invalid_payload', 'A valid JSON object is required') from exc
    if not isinstance(value, dict) or not required <= value.keys() or not value.keys() <= required | optional:
        raise ServiceError('invalid_payload', 'Missing or unsupported fields; roots and authority cannot be supplied')
    return value


# Every dispatch target and body schema is fixed here, never caller-selected.
def endpoint(method, required, optional=(), *, record=False, whole=False):
    async def handler(request: Request):
        try:
            values = await payload(request, set(required), set(optional))
        except _ERRORS as exc:
            return failure(exc)
        args = [request.path_params['record_id']] if record else []
        if whole:
            args.append(values)
            values = {}
        return await run_in_threadpool(invoke, method, *args, **values)
    return handler


router.add_api_route('/setup', endpoint('setup', {'confirm'}), methods=['POST'], name='elm_setup')
router.add_api_route('/record', endpoint('create_record',
    {'scope_id','title','text','domain','kind','basis','sources'},
    {'topic','state','dependencies','sensitive'}, whole=True), methods=['POST'], name='elm_create_record')
router.add_api_route('/records/{record_id}/approve', endpoint('approve', {'expected_revision'}, record=True),
                     methods=['POST'], name='elm_approve')
router.add_api_route('/records/{record_id}', endpoint('correct', {'expected_revision','changes'}, record=True),
                     methods=['PATCH'], name='elm_correct')
router.add_api_route('/records/{record_id}/delete-preview', endpoint('delete_preview', set(), record=True),
                     methods=['POST'], name='elm_delete_preview')
router.add_api_route('/records/{record_id}/delete', endpoint('delete', {'preview_token'}, record=True),
                     methods=['POST'], name='elm_delete')
router.add_api_route('/scopes/privacy', endpoint('set_privacy', {'scope_id','private'}),
                     methods=['POST'], name='elm_privacy')
router.add_api_route('/read-policy', endpoint('set_read_policy',
    {'session_id','workspace_enabled','expected_identity','expected_policy_revision'}),
    methods=['POST'], name='elm_read_policy')
router.add_api_route('/grants', endpoint('grant', {'source_scope','target_scope','record_ids'}),
                     methods=['POST'], name='elm_grant')
router.add_api_route('/grants', endpoint('revoke', {'source_scope','target_scope','record_ids'}),
                     methods=['DELETE'], name='elm_revoke')
router.add_api_route('/learning', endpoint('set_learning', {'enabled'}), methods=['POST'], name='elm_learning')
router.add_api_route('/index/rebuild', endpoint('rebuild', {'scope_id','confirm'}),
                     methods=['POST'], name='elm_rebuild')


@router.post('/draft')
async def draft(request: Request):
    try:
        values = await payload(request, {'scope_id','record_ids','kind'}, {'session_id','model_route'})
    except _ERRORS as exc:
        return failure(exc)
    from .workspace_draft_bridge import draft_via_host_command
    # Starlette propagates the host request's profile context into this thread.
    result = await run_in_threadpool(draft_via_host_command, get_hermes_home(), values)
    if result.get('ok') is not True:
        return failure(ServiceError(result['code'], result['message']))
    return result
