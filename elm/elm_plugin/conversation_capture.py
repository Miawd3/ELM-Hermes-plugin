"""Explicit local finalized-turn capture, sensitive by construction; no external extraction."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import secrets
import threading
import time

from .private_workspace_v2 import _transaction, _paths, _digest, _fail
from .private_sources_v1 import _items, _hash
from .workspace_records import _now

_NOTICE = ('Locally retain future supported finalized user/assistant text as secret-redacted PRIVATE sensitive snapshots. '
           'Assistant text is not a user claim or delivery proof. No model/external extraction or automatic approval is enabled. '
           'Capture stops at the retained-turn/source/byte cap; nothing is silently evicted. Disable stops future captures, '
           'not existing retained sources. Withdrawal retains text; no purge is provided.')


def _default():
    return dict(revision=0, enabled=False, max_turns=8, max_utf8_bytes=16384, admission_watermark=0)


def _settings(data, chat):
    return data.get('private_capture', {}).get('settings', {}).get(chat, _default())


def _receipts(data):
    return data.get('private_capture', {}).get('receipts', {})


def _validate(enabled, max_turns, max_utf8_bytes):
    if (type(enabled) is not bool or type(max_turns) is not int or not 1 <= max_turns <= 32
            or type(max_utf8_bytes) is not int or not 2048 <= max_utf8_bytes <= 32768):
        _fail('invalid_payload', 'Capture requires boolean enabled, turns1..32 and UTF-8 bytes2048..32768')


def validate_capture(data):
    ext = data.get('private_capture', dict(schema=1, settings={}, receipts={}))
    if (type(ext) is not dict or set(ext) != {'schema','settings','receipts'}
            or type(ext['schema']) is not int or ext['schema'] != 1
            or type(ext['settings']) is not dict or len(ext['settings']) > 512
            or type(ext['receipts']) is not dict or len(ext['receipts']) > 32):
        raise ValueError('Invalid local capture registry')
    for chat, setting in ext['settings'].items():
        scope = data['scopes'].get(chat)
        if (not scope or scope['kind'] != 'chat' or scope['private'] is not True
                or type(setting) is not dict or set(setting) != set(_default())
                or type(setting['revision']) is not int or setting['revision'] < 1
                or type(setting['admission_watermark']) is not int or setting['admission_watermark'] < 0):
            raise ValueError('Invalid capture settings ownership')
        _validate(setting['enabled'],setting['max_turns'],setting['max_utf8_bytes'])
    referenced = set()
    for key, receipt in ext['receipts'].items():
        fields = {'capture_id','scope_id','sequence','created_at','user_source_id','assistant_source_id','user_utf8_bytes','assistant_utf8_bytes','phase'}
        if (type(receipt) is not dict or set(receipt) != fields or receipt['capture_id'] != key
                or type(key) is not str or len(key) != 32 or any(c not in '0123456789abcdef' for c in key)
                or type(receipt['sequence']) is not int or receipt['sequence'] < 1
                or receipt['phase'] != 'finalized_before_delivery'):
            raise ValueError('Invalid capture receipt')
        if datetime.fromisoformat(receipt['created_at']).tzinfo is None:
            raise ValueError('Invalid capture timestamp')
        for role in ('user','assistant'):
            source_id = receipt[role+'_source_id']
            source = _items(data).get(source_id)
            provenance = dict(admission_id=key, role=role, phase='finalized_before_delivery', representation='secret_redacted_native_text')
            if (source is None or source['scope_id'] != receipt['scope_id'] or source['sensitive'] is not True
                    or source.get('native_capture') != provenance or source_id in referenced
                    or type(receipt[role+'_utf8_bytes']) is not int or receipt[role+'_utf8_bytes'] != len(source['text'].encode('utf-8'))):
                raise ValueError('Captured source provenance mismatch')
            referenced.add(source_id)
    if {key for key, item in _items(data).items() if 'native_capture' in item} != referenced:
        raise ValueError('Native captured sources require their atomic receipt')


def _count(data, chat):
    return sum(v['scope_id'] == chat for v in _receipts(data).values())


def _status(data, chat):
    from hermes_cli.plugin_memory import memory_capabilities
    setting = _settings(data, chat)
    count = _count(data, chat)
    return dict(**{k:v for k,v in setting.items() if k != 'admission_watermark'}, captured_turns=count,
                remaining_turns=max(0,setting['max_turns']-count),
                capacity_reason='retained_turn_cap' if count >= setting['max_turns'] else ('store_capture_capacity' if len(_receipts(data)) >= 32 else ('source_cap' if len(_items(data)) + 2 > 64 else None)),
                host_supported=memory_capabilities().get('local_turn_capture') is True,
                external_egress=False, sensitive=True, notice=_NOTICE)


def _snapshot(owner):
    root, _, _, chat = _paths(owner)
    if not root.exists():
        return _default(), None, _status({},chat)
    with _transaction(owner) as (_,data,chat):
        return deepcopy(_settings(data,chat)), data['store_id'], _status(data,chat)


class CaptureSettings:
    def __init__(self):
        self._lock=threading.Lock()
        self._active=True
        self._tokens={}

    def close(self):
        with self._lock:
            self._active=False
            self._tokens.clear()

    def _live(self):
        if not self._active:
            _fail('context_expired','Capture workflow is no longer active')

    def status(self):
        from hermes_cli.plugin_memory import memory_owner,read_memory
        owner=memory_owner(version=1)
        with self._lock:
            self._live()
            return read_memory(owner,lambda:_snapshot(owner)[2])

    def preview(self,*,enabled,max_turns=8,max_utf8_bytes=16384):
        _validate(enabled,max_turns,max_utf8_bytes)
        from hermes_cli.plugin_memory import memory_owner,read_memory
        owner=memory_owner(version=1)
        with self._lock:
            self._live()
            prior,store_id,_=read_memory(owner,lambda:_snapshot(owner))
            if enabled and store_id is None:
                _fail('not_initialized','Explicit private setup is required before capture opt-in')
            now=time.monotonic()
            self._tokens={k:v for k,v in self._tokens.items() if v[0]>now}
            if len(self._tokens)>=64:
                _fail('preview_limit','Too many capture previews')
            proposed=dict(enabled=enabled,max_turns=max_turns,max_utf8_bytes=max_utf8_bytes)
            token=secrets.token_urlsafe(32)
            self._tokens[token]=(now+300,owner,store_id,prior,proposed)
            return dict(preview_token=token,expires_in_seconds=300,settings=proposed,notice=_NOTICE)

    def apply(self,preview_token,*,confirm=False):
        if confirm is not True:
            _fail('confirmation_required','Explicit local capture consent is required')
        if type(preview_token) is not str or len(preview_token)>128:
            _fail('stale_preview','Capture preview unavailable')
        from hermes_cli.plugin_memory import memory_owner,publish_memory,capture_admission_watermark
        owner=memory_owner(version=1)
        with self._lock:
            self._live()
            item=self._tokens.get(preview_token)
            if item is None:
                _fail('stale_preview','Capture preview unavailable; review again')
            expiry,expected,store_id,prior,proposed=item
            if (owner.profile_id,owner.principal_id,owner.canonical_session_id)!=(expected.profile_id,expected.principal_id,expected.canonical_session_id):
                _fail('stale_preview','Capture preview is not owned by this chat')
            del self._tokens[preview_token]
            if owner!=expected or time.monotonic()>=expiry:
                _fail('stale_preview','Capture context changed or expired')
            def save():
                if store_id is None:
                    if _snapshot(owner)[1] is not None:
                        _fail('stale_preview','Capture store changed')
                    return _snapshot(owner)[2]
                with _transaction(owner,write=True,create_chat=True) as (_,data,chat):
                    if data['store_id']!=store_id or _settings(data,chat)!=prior:
                        _fail('stale_preview','Capture settings changed')
                    setting=dict(**proposed,revision=prior['revision']+1,admission_watermark=capture_admission_watermark())
                    data.setdefault('private_capture',dict(schema=1,settings={},receipts={}))['settings'][chat]=setting
                    return _status(data,chat)
            return publish_memory(owner,save)

    def list(self,*,limit=16,before=None):
        if type(limit) is not int or not 1<=limit<=32:
            _fail('invalid_payload','Capture limit must be one to thirty-two')
        from hermes_cli.plugin_memory import memory_owner,read_memory
        owner=memory_owner(version=1)
        with self._lock:
            self._live()
            def inspect():
                with _transaction(owner) as (_,data,chat):
                    rows=sorted((v for v in _receipts(data).values() if v['scope_id']==chat),key=lambda v:(v['created_at'],v['capture_id']),reverse=True)
                    if before is not None:
                        matches=[i for i,v in enumerate(rows) if v['capture_id']==before]
                        if not matches:
                            _fail('stale_preview','Capture cursor unavailable; refresh this chat')
                        rows=rows[matches[0]+1:]
                    page=rows[:limit]
                    return dict(turns=[{k:deepcopy(v) for k,v in row.items() if k not in ('scope_id','sequence')} for row in page],
                                truncated=len(rows)>limit,next_before=page[-1]['capture_id'] if page and len(rows)>limit else None)
            return read_memory(owner,inspect)


def capture_finalized(provider,*,session_id,receipt,user_text,assistant_text):
    if provider._closed or provider._home is None:
        return {'status':'disabled'}
    from hermes_cli.plugin_memory import request_memory_owner,capture_turn_memory,capture_turn_provenance
    actual = capture_turn_provenance()
    if (type(receipt) is not dict or set(receipt) != {'admission_id','sequence'}
            or receipt['admission_id'] != actual['admission_id'] or type(receipt['sequence']) is not int
            or receipt['sequence'] != actual['sequence'] or type(user_text) is not str or type(assistant_text) is not str
            or _hash(user_text) != actual['user_sha256'] or _hash(assistant_text) != actual['assistant_sha256']):
        _fail('capture_identity_mismatch','Capture receipt or redacted text does not match the native finalization')
    owner=request_memory_owner(version=1,alias=session_id)
    if owner.profile_id!=provider._home:
        return {'status':'disabled'}
    def eligible(data,chat):
        setting=_settings(data,chat)
        if not setting['enabled']:
            return {'status':'disabled'}
        if provider._closed:
            _fail('context_expired','Capture provider closed')
        if receipt['sequence']<=setting['admission_watermark']:
            return {'status':'skipped','reason':'admitted_before_consent'}
        existing=_receipts(data).get(receipt['admission_id'])
        if existing is not None:
            if existing['scope_id']!=chat:
                _fail('scope_changed','Capture identity does not belong to current chat')
            return {'status':'already_captured'}
        if _count(data,chat)>=setting['max_turns'] or len(_receipts(data))>=32:
            return {'status':'skipped','reason':'retained_turn_cap'}
        if len(_items(data))+2>64:
            return {'status':'skipped','reason':'source_cap'}
        if type(user_text) is not str or type(assistant_text) is not str or not user_text or not assistant_text:
            return {'status':'skipped','reason':'unsupported_text'}
        sizes=[len(v.encode('utf-8')) for v in (user_text,assistant_text)]
        if sum(sizes)>setting['max_utf8_bytes']:
            return {'status':'skipped','reason':'turn_byte_cap'}
        return None
    def save():
        root,_,_,_=_paths(owner)
        if not root.exists():
            return {'status':'disabled'}
        with _transaction(owner) as (_,data,chat):
            outcome=eligible(data,chat)
            if outcome is not None:
                return outcome
        with _transaction(owner,write=True) as (_,data,chat):
            if eligible(data,chat) is not None:
                _fail('capture_changed','Capture policy/capacity changed; no write was made')
            sizes=[len(v.encode('utf-8')) for v in (user_text,assistant_text)]
            now=_now()
            sources=data.setdefault('private_sources',dict(schema=1,items={}))['items']
            ids={}
            for role,text in (('user',user_text),('assistant',assistant_text)):
                key='src_'+_digest([chat,receipt['admission_id'],role])[:32]
                if key in sources:
                    _fail('revision_conflict','Capture source identity collision')
                ids[role]=key
                sources[key]=dict(id=key,scope_id=chat,title='Captured '+role+' text',text=text,
                    reference='hermes-admission:'+receipt['admission_id']+':'+role,author=role,sha256=_hash(text),
                    revision=1,state='active',created_at=now,sensitive=True,
                    native_capture=dict(admission_id=receipt['admission_id'],role=role,phase='finalized_before_delivery',representation='secret_redacted_native_text'))
            entry=dict(capture_id=receipt['admission_id'],scope_id=chat,sequence=receipt['sequence'],created_at=now,
                       user_source_id=ids['user'],assistant_source_id=ids['assistant'],user_utf8_bytes=sizes[0],assistant_utf8_bytes=sizes[1],phase='finalized_before_delivery')
            data['private_capture']['receipts'][receipt['admission_id']]=entry
            if provider._closed:
                _fail('context_expired','Capture provider closed before commit')
            return {'status':'captured','capture_id':receipt['admission_id']}
    return capture_turn_memory(owner,save)


def register_capture_rpc(ctx):
    try:
        from hermes_cli.plugin_memory import memory_capabilities
    except ImportError:
        return False
    if not callable(getattr(ctx,'register_rpc',None)) or not memory_capabilities().get('local_turn_capture'):
        return False
    from .private_workspace_rpc import _fields
    service=CaptureSettings()
    def status(params,**kwargs):
        _fields(params)
        return service.status()
    def preview(params,**kwargs):
        _fields(params,('enabled',),('max_turns','max_utf8_bytes'))
        return service.preview(**{k:v for k,v in params.items() if k!='session_id'})
    def apply(params,**kwargs):
        _fields(params,('preview_token','confirm'))
        return service.apply(params['preview_token'],confirm=params['confirm'])
    def list_captures(params,**kwargs):
        _fields(params,(),('limit','before'))
        return service.list(limit=params.get('limit',16),before=params.get('before'))
    ctx.register_rpc('private.capture_settings.status',status,memory_scope='local_read')
    ctx.register_rpc('private.capture_settings.preview',preview,memory_scope='local_read')
    ctx.register_rpc('private.capture_settings.apply',apply)
    ctx.register_rpc('private.capture.list',list_captures,memory_scope='local_read')
    if callable(getattr(ctx,'on_unload',None)):
        ctx.on_unload(service.close)
    return True
