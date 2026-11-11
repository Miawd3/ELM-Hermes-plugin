"""Host-bound saved-output publishing; not durable memory or root acceptance.

The memory provider owns initialization, profile/session binding and its epoch.
Only the three authored-output fields are model-controlled. UI state is separate.
"""
import json
import re
import sqlite3
from .schemas import schema,string
from .workspace_service import ServiceError
from .workspace_records import RecordError
from .host_identity import HostIdentity, IdentityError
from .result_inbox import InboxError,publish_important_result

IMPORTANT_SCHEMA=schema('elm_important',
    'Save important assistant output in this host chat only. Not a memory fact, user-read receipt or proof the whole request is finished. Return the saved own-result directive in your reply.',
    {'title':string(300),'body':string(100000),'kind':string(enum=['progress','partial','blocked','final'])},
    ['title','body','kind'])

def _wire(value):
    result=json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))
    if len(result)>12000:raise ServiceError('result_too_large','Important receipt exceeds its bounded surface')
    return result

def _uncertain(code='publication_unconfirmed',*,saved=False):
    return _wire({'error':code,'disposition':'saved_but_withheld' if saved else 'publication_unconfirmed',
        'save_status':'saved_in_admitted_chat' if saved else 'unknown','automatic_retry':False,
        'message':'Do not republish automatically. Reconcile Important results in the admitted chat; no content or pointer is delivered across a changed scope.'})

def publish_current(provider,args,kwargs):
    if not isinstance(args,dict) or set(args)!={'title','body','kind'}:
        raise ServiceError('invalid_arguments','Only title, body and kind are permitted')
    for key,maximum in (('title',300),('body',100000)):
        value=args[key]
        if not isinstance(value,str) or not value.strip() or len(value)>maximum or '\x00' in value:
            raise ServiceError('invalid_arguments','Important title/body must be bounded nonblank text')
    if args['kind'] not in ('progress','partial','blocked','final'):
        raise ServiceError('invalid_arguments','Important kind must be progress, partial, blocked or final')
    with provider._lock:
        provider._guard(kwargs)
        if provider._agent_context!='primary':
            raise ServiceError('write_blocked','Delegated agents cannot publish primary-chat Important output')
        session,epoch=provider._session_id,provider._epoch
        # Refuse an unpersisted/foreign host identity before entering a writer;
        # errors after writer entry remain conservatively unconfirmed.
        HostIdentity(provider._home).resolve(session)
        try:
            published=publish_important_result(current_session_id=session,**args)
        except (InboxError,IdentityError,OSError,sqlite3.Error):
            # A postcommit readback can fail too; never turn this into an
            # automatic repeat or falsely assert that no row was saved.
            return _uncertain()
        result=published.get('result')
        if not isinstance(result,dict) or not isinstance(result.get('id'),str) or re.fullmatch(r'[0-9a-f]{32}',result['id']) is None:
            return _uncertain()
        # The full stored body is NOT echoed into the bounded native receipt.
        receipt={'ok':True,'disposition':'saved','result':{k:result[k] for k in ('id','kind','status','revision')},
            'directive':published['directive'],'whole_request_completion_verified':False,'user_read_verified':False,
            'meaning':'Saved assistant output in the admitted chat only. Final is a declared kind, not independent request acceptance. Viewed is not Read; acknowledgment stays human-owned.'}
        wire=_wire(receipt)
        try:
            provider._guard(kwargs)
        except RecordError:
            return _uncertain('scope_changed_after_save',saved=True)
        if session!=provider._session_id or epoch!=provider._epoch:
            return _uncertain('scope_changed_after_save',saved=True)
        return wire
