"""Reviewed user-supplied exports only; never reads or adopts legacy directories."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
import re
import secrets
import threading
import time
import uuid

from .private_workspace_v2 import _transaction, _authored_fields, _record_count, _fail, _now

_NOTICE='This is a copy of a user-supplied export, not verified legacy ownership or migration. You declare the right to copy every selected item. Original scopes, approvals and authorship are unverified claims. New records are PRIVATE to this current chat, pending and sensitive; no original is read, changed or deleted. Separate record review/approval remains required.'


def _wire(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)


def _hash(value):
    return hashlib.sha256(_wire(value).encode()).hexdigest()


def _parse(export_text):
    def pairs(items):
        out={}
        for key,value in items:
            if key in out:
                raise ValueError('duplicate field')
            out[key]=value
        return out
    try:
        if type(export_text) is not str or len(export_text.encode())>65536:
            raise ValueError('export size')
        value=json.loads(export_text,object_pairs_hook=pairs,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
        if type(value) is not dict or set(value)!={'format','records'} or value['format']!='elm-selected-records-v1' or type(value['records']) is not list or not 1<=len(value['records'])<=8:
            raise ValueError('export format')
        required={'id','title','text','sources'}
        allowed=required|{'domain','kind','basis','topic','state','sensitive','scope_id','revision','created_at','updated_at','dependencies'}
        ids=set()
        for row in value['records']:
            if type(row) is not dict or not required<=set(row) or not set(row)<=allowed:
                raise ValueError('record fields')
            if type(row['id']) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',row['id']) is None or row['id'] in ids:
                raise ValueError('original identity')
            ids.add(row['id'])
            for field in ('domain','kind','basis','topic'):
                if field in row and (type(row[field]) is not str or not row[field] or len(row[field])>128):
                    raise ValueError('declared classification')
            if row.get('dependencies',[])!=[]:
                raise ValueError('unsupported dependencies')
            if 'sensitive' in row and type(row['sensitive']) is not bool:
                raise ValueError('sensitivity')
            if 'revision' in row and (type(row['revision']) is not int or not 1<=row['revision']<=2147483647):
                raise ValueError('revision')
            if 'state' in row and row['state'] not in ('pending','approved','invalidated'):
                raise ValueError('state')
            for key in ('scope_id','created_at','updated_at'):
                if key in row and (type(row[key]) is not str or len(row[key])>256):
                    raise ValueError('origin metadata')
            if type(row['sources']) is not list or not 1<=len(row['sources'])<=7:
                raise ValueError('source count')
            for source in row['sources']:
                if type(source) is not dict or type(source.get('ref')) is not str or source['ref'].startswith(('record:','elm-snapshot-v1:')):
                    raise ValueError('unverifiable source link')
        return value
    except Exception:
        _fail('invalid_import_export','Supply a bounded selected-record export; linked records/private snapshots and unsupported fields are not adopted')


def _candidates(export,canonical_sha256):
    candidates=[]
    claims=[]
    for index,row in enumerate(export['records']):
        sources=deepcopy(row['sources'])+[dict(ref=f'declared-export-v1:{canonical_sha256}:{index}')]
        fields=_authored_fields(row['title'],row['text'],sources,'reference','reference','source_document','facts',True)
        candidates.append(fields)
        claim={key:deepcopy(row[key]) for key in ('id','scope_id','revision','state','sensitive','created_at','updated_at','domain','kind','basis','topic') if key in row}
        if len(_wire(claim).encode())>4096:
            _fail('import_metadata_limit','Original claim metadata exceeds the retained receipt limit; no preview was issued')
        claims.append(claim)
    return candidates,claims


def _receipts(data):
    return data.get('private_imports',{}).get('receipts',{})


def _summary(receipt):
    return {key:deepcopy(receipt[key]) for key in ('batch_id','created_at','export_sha256','canonical_sha256','record_ids','original_claims','ownership_declaration')}


def validate_imports(data):
    extension=data.get('private_imports')
    if extension is None:
        return
    if type(extension) is not dict or set(extension)!={'schema','receipts'} or type(extension['schema']) is not int or extension['schema']!=1 or type(extension['receipts']) is not dict or len(extension['receipts'])>64:
        raise ValueError('Invalid import receipts')
    for key,row in extension['receipts'].items():
        fields={'batch_id','scope_id','store_id','created_at','export_sha256','canonical_sha256','record_ids','original_claims','ownership_declaration'}
        if type(row) is not dict or set(row)!=fields or row['batch_id']!=key or row['store_id']!=data['store_id']:
            raise ValueError('Invalid import receipt')
        for field in ('batch_id','export_sha256','canonical_sha256'):
            if type(row[field]) is not str or re.fullmatch('[0-9a-f]{64}',row[field]) is None:
                raise ValueError('Invalid import digest')
        scope=data['scopes'].get(row['scope_id'])
        if scope is None or scope['kind']!='chat' or scope.get('private') is not True or 'read_policy' in scope:
            raise ValueError('Invalid import scope')
        if key!=_hash([1,row['scope_id'],row['canonical_sha256']]):
            raise ValueError('Invalid import identity')
        if type(row['created_at']) is not str or len(row['created_at'])>64 or datetime.fromisoformat(row['created_at']).utcoffset() is None or row['ownership_declaration']!='user_declared_right_to_copy':
            raise ValueError('Invalid import declaration')
        ids=row['record_ids']
        if type(ids) is not list or not 1<=len(ids)<=8 or len(set(ids))!=len(ids) or type(row['original_claims']) is not list or len(row['original_claims'])!=len(ids):
            raise ValueError('Invalid import records')
        for record_id in ids:
            if type(record_id) is not str or re.fullmatch('rec_[0-9a-f]{32}',record_id) is None:
                raise ValueError('Invalid import record identity')
            record=data['records'].get(record_id) or data['tombstones'].get(record_id)
            if record is None or record['scope_id']!=row['scope_id']:
                raise ValueError('Invalid import record ownership')
        for claim in row['original_claims']:
            if type(claim) is not dict or 'id' not in claim or not set(claim)<={'id','scope_id','revision','state','sensitive','created_at','updated_at','domain','kind','basis','topic'} or len(_wire(claim))>4096:
                raise ValueError('Invalid original claims')
            _parse(_wire(dict(format='elm-selected-records-v1',records=[dict(title='Claim',text='Claim',sources=[dict(ref='declared-only')],**claim)])))


class PrivateImportV1:
    def __init__(self):
        self._lock=threading.RLock()
        self._tokens={}
        self._closed=False

    def close(self):
        with self._lock:
            self._closed=True
            self._tokens.clear()

    def _live(self):
        if self._closed:
            _fail('service_closed','Import service is closed')

    def preview(self,export_text,*,ownership_declared=False):
        if ownership_declared is not True:
            _fail('ownership_declaration_required','Explicitly declare your right to copy every supplied record; legacy ownership is not verified')
        from hermes_cli.plugin_memory import memory_owner,read_memory
        owner=memory_owner(version=1)
        export=_parse(export_text)
        canonical_sha=_hash(export)
        export_sha=hashlib.sha256(export_text.encode()).hexdigest()
        candidates,claims=_candidates(export,canonical_sha)
        with self._lock:
            self._live()
            for key,value in list(self._tokens.items()):
                if value['deadline']<=time.monotonic():
                    del self._tokens[key]
            def inspect():
                with _transaction(owner) as (_,data,chat):
                    batch_id=_hash([1,chat,canonical_sha])
                    previous=_receipts(data).get(batch_id)
                    if previous is None and (len(_receipts(data))>=64 or _record_count(data)+len(candidates)>512):
                        _fail('store_limit','Import receipt or private record capacity reached')
                    return data['store_id'],batch_id,deepcopy(previous)
            store_id,batch_id,existing=read_memory(owner,inspect)
            payload=dict(store_id=store_id,batch_id=batch_id,canonical_sha256=canonical_sha,export_sha256=export_sha,
                         candidates=candidates,original_claims=claims)
            size=len(_wire(payload).encode())
            if size>131072 or len(self._tokens)>=16 or sum(v['size'] for v in self._tokens.values())+size>1048576:
                _fail('preview_limit','Import preview capacity reached; no content is truncated')
            token=secrets.token_urlsafe(32)
            self._tokens[token]=dict(owner=owner,payload=payload,deadline=time.monotonic()+300,size=size)
            return dict(preview_token=token,expires_in_seconds=300,batch_id=batch_id,export_sha256=export_sha,
                        canonical_sha256=canonical_sha,candidates=deepcopy(candidates),original_claims=deepcopy(claims),
                        destination=dict(kind='current_private_chat',context_key=_hash([asdict(owner),store_id])),
                        already_imported=existing is not None,existing_receipt=_summary(existing) if existing else None,notice=_NOTICE)

    def apply(self,preview_token,*,confirm=False):
        if confirm is not True:
            _fail('confirmation_required','Explicit full-preview import confirmation is required')
        from hermes_cli.plugin_memory import memory_owner,read_memory,publish_memory
        with self._lock:
            self._live()
            item=self._tokens.get(preview_token) if type(preview_token) is str else None
            if item is None:
                _fail('preview_unavailable','Import preview unavailable')
            owner=memory_owner(version=1)
            if owner!=item['owner']:
                _fail('owner_changed','Import preview belongs to a different native owner snapshot')
            del self._tokens[preview_token]
            if item['deadline']<=time.monotonic():
                _fail('preview_expired','Import preview expired')
            payload=item['payload']
            def existing():
                with _transaction(owner) as (_,data,chat):
                    if data['store_id']!=payload['store_id']:
                        _fail('store_changed','Import destination changed; review again')
                    row=_receipts(data).get(payload['batch_id'])
                    return _summary(row) if row else None
            previous=read_memory(owner,existing)
            if previous is not None:
                return dict(applied=False,already_imported=True,receipt=previous)
            def copy_records():
                with _transaction(owner,write=True,create_chat=True) as (_,data,chat):
                    if data['store_id']!=payload['store_id']:
                        _fail('store_changed','Import destination changed; review again')
                    receipts=data.setdefault('private_imports',dict(schema=1,receipts={}))['receipts']
                    if payload['batch_id'] in receipts:
                        return dict(applied=False,already_imported=True,receipt=_summary(receipts[payload['batch_id']]))
                    if len(receipts)>=64 or _record_count(data)+len(payload['candidates'])>512:
                        _fail('store_limit','Import receipt or private record capacity reached')
                    now=_now()
                    ids=[]
                    for fields in payload['candidates']:
                        key='rec_'+uuid.uuid4().hex
                        if key in data['records'] or key in data['tombstones']:
                            _fail('revision_conflict','New import record identity collided')
                        data['records'][key]=dict(id=key,revision=1,scope_id=chat,created_at=now,updated_at=now,**deepcopy(fields))
                        ids.append(key)
                    row=dict(batch_id=payload['batch_id'],scope_id=chat,store_id=data['store_id'],created_at=now,
                             export_sha256=payload['export_sha256'],canonical_sha256=payload['canonical_sha256'],record_ids=ids,
                             original_claims=deepcopy(payload['original_claims']),ownership_declaration='user_declared_right_to_copy')
                    receipts[row['batch_id']]=row
                    return dict(applied=True,already_imported=False,receipt=_summary(row))
            return publish_memory(owner,copy_records)

    def list(self,*,limit=16,before=None):
        if type(limit) is not int or not 1<=limit<=16 or (before is not None and (type(before) is not str or re.fullmatch('[0-9a-f]{64}',before) is None)):
            _fail('invalid_pagination','Use a bounded import receipt page')
        from hermes_cli.plugin_memory import memory_owner,read_memory
        owner=memory_owner(version=1)
        with self._lock:
            self._live()
            def inspect():
                with _transaction(owner) as (_,data,chat):
                    rows=sorted((r for r in _receipts(data).values() if r['scope_id']==chat and (before is None or r['batch_id']<before)),key=lambda r:r['batch_id'],reverse=True)
                    selected=rows[:limit]
                    return dict(receipts=[{k:v for k,v in _summary(r).items() if k!='original_claims'} for r in selected],next_before=selected[-1]['batch_id'] if len(rows)>limit else None)
            return read_memory(owner,inspect)

    def get(self,batch_id):
        from hermes_cli.plugin_memory import memory_owner,read_memory
        owner=memory_owner(version=1)
        with self._lock:
            self._live()
            def inspect():
                with _transaction(owner) as (_,data,chat):
                    row=_receipts(data).get(batch_id) if type(batch_id) is str else None
                    if row is None or row['scope_id']!=chat:
                        _fail('import_not_found','No current-chat import receipt was found')
                    return dict(receipt=_summary(row))
            return read_memory(owner,inspect)


def register_private_import_rpc(ctx):
    try:
        from hermes_cli.plugin_memory import memory_capabilities
    except ImportError:
        return False
    cap=memory_capabilities()
    if not callable(getattr(ctx,'register_rpc',None)) or not cap.get('record_read') or not cap.get('publication'):
        return False
    from .private_workspace_rpc import _fields
    service=PrivateImportV1()
    def preview(params,**kwargs):
        _fields(params,('export_text','ownership_declared'))
        return service.preview(params['export_text'],ownership_declared=params['ownership_declared'])
    def apply(params,**kwargs):
        _fields(params,('preview_token','confirm'))
        return service.apply(params['preview_token'],confirm=params['confirm'])
    def list_receipts(params,**kwargs):
        _fields(params,(),('limit','before'))
        return service.list(limit=params.get('limit',16),before=params.get('before'))
    def get(params,**kwargs):
        _fields(params,('batch_id',))
        return service.get(params['batch_id'])
    ctx.register_rpc('private.import.preview',preview,memory_scope='local_read')
    ctx.register_rpc('private.import.apply',apply)
    ctx.register_rpc('private.import.list',list_receipts,memory_scope='local_read')
    ctx.register_rpc('private.import.get',get,memory_scope='local_read')
    if callable(getattr(ctx,'on_unload',None)):
        ctx.on_unload(service.close)
    return True
