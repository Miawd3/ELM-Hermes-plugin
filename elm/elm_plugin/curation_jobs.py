"""Durable source-bound review; dispatch qualification is private loopback-only."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
import re
import hashlib
import json
import threading
import time
import uuid

from .curation_foundation import validate_model_proposals, _wire, _INSTRUCTIONS
from .private_sources_v1 import _source
from .private_workspace_v2 import _transaction, _fail, _now, _record_count


def _hash(value):
    return hashlib.sha256(_wire(value).encode()).hexdigest()


def _owner_key(owner):
    return _hash([owner.profile_id,owner.principal_id,owner.canonical_session_id])


def _jobs(data):
    return data.get('private_curation',{}).get('jobs',{})


def _pins(sources):
    return [dict(source_id=s['id'],sha256=s['sha256'],revision=s['revision'],sensitive=s['sensitive'],state=s['state']) for s in sources]


def _selected(data,chat,pins):
    return [_source(data,chat,p['source_id']) for p in pins]


def _fresh(data,chat,job):
    sources=_selected(data,chat,job['sources'])
    if data['store_id']!=job['store_id'] or _pins(sources)!=job['sources'] or any(s['state']!='active' for s in sources):
        _fail('source_snapshot_changed','Selected sources changed; this result cannot create a record')
    return sources


def _owned(data,chat,key):
    job=_jobs(data).get(key) if type(key) is str else None
    if job is None or job['scope_id']!=chat:
        _fail('job_not_found','No current-chat curation job was found')
    return job


def _summary(job):
    return {k:deepcopy(job[k]) for k in ('job_id','revision','state','created_at')} | dict(
        proposal_count=len(job['proposals']),accepted_indexes=sorted(int(k) for k in job['accepted']))


def _validate_recipient(value):
    base={'provider','endpoint','credential_mode','redirects','automatic_retries','fallback','environment_proxy'}
    optional={'credential_slot','credential_version','route_sha256'}
    if type(value) is not dict or not base<=set(value) or not set(value)<=base|optional:
        raise ValueError('Invalid curation recipient fields')
    if any(value[k] is not False for k in ('redirects','fallback','environment_proxy')) or type(value['automatic_retries']) is not int or value['automatic_retries']!=0:
        raise ValueError('Invalid curation recipient policy')
    # Only the qualified local adapters can create jobs in this milestone.
    from hermes_cli.plugin_llm_transport import _destination
    _destination(value['endpoint'],loopback=value['credential_mode']!='host-enrolled-slot')
    if value['credential_mode']=='host-enrolled-slot':
        if (value.get('credential_slot')!='organizer' or type(value.get('credential_version')) is not int
                or value['credential_version']<1 or type(value.get('route_sha256')) is not str
                or re.fullmatch(r'[0-9a-f]{64}',value['route_sha256']) is None
                or type(value['provider']) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}',value['provider']) is None):
            raise ValueError('Invalid host recipient')
        return
    if value['provider']=='loopback-test':
        if value['credential_mode']!='none' or any(value.get(k) is not None for k in optional):
            raise ValueError('Invalid uncredentialed recipient')
    elif value['provider']=='synthetic-slot-loopback':
        slot=value.get('credential_slot')
        version=value.get('credential_version')
        digest=value.get('route_sha256')
        if (value['credential_mode']!='synthetic-dedicated-slot' or type(slot) is not str
                or re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',slot) is None
                or type(version) is not int or version<1
                or type(digest) is not str or re.fullmatch(r'[0-9a-f]{64}',digest) is None):
            raise ValueError('Invalid synthetic recipient')
    else:
        raise ValueError('Unsupported curation recipient')


def validate_jobs(data):
    extension=data.get('private_curation')
    if extension is None:
        return
    if type(extension) is not dict or set(extension)!={'schema','jobs'} or type(extension['schema']) is not int or extension['schema']!=1 or type(extension['jobs']) is not dict or len(extension['jobs'])>16:
        raise ValueError('Invalid curation registry')
    for key,job in extension['jobs'].items():
        required={'job_id','scope_id','store_id','owner_sha256','revision','state','created_at','sources','payload_sha256','attempt_id','recipient','model','proposals','accepted'}
        if type(job) is not dict or set(job)!=required or job['job_id']!=key or type(key) is not str or re.fullmatch(r'job_[0-9a-f]{32}',key) is None or job['store_id']!=data['store_id']:
            raise ValueError('Invalid curation job')
        if (job['scope_id'] not in data['scopes'] or data['scopes'][job['scope_id']]['kind']!='chat'
                or data['scopes'][job['scope_id']].get('private') is not True
                or 'read_policy' in data['scopes'][job['scope_id']]):
            raise ValueError('Invalid curation scope')
        if type(job['revision']) is not int or job['revision']<1 or job['state'] not in ('attempted','ready') or type(job['created_at']) is not str:
            raise ValueError('Invalid curation state')
        if len(job['created_at'])>64 or datetime.fromisoformat(job['created_at']).utcoffset() is None:
            raise ValueError('Invalid curation timestamp')
        for field in ('owner_sha256','payload_sha256','attempt_id'):
            value=job[field]
            if type(value) is not str or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
                raise ValueError('Invalid curation digest')
        if type(job['model']) is not str or not 1<=len(job['model'])<=128:
            raise ValueError('Invalid curation model')
        _validate_recipient(job['recipient'])
        if type(job['sources']) is not list or not 1<=len(job['sources'])<=4:
            raise ValueError('Invalid curation sources')
        sources=[]
        for pin in job['sources']:
            if type(pin) is not dict or set(pin)!={'source_id','sha256','revision','sensitive','state'} or type(pin['revision']) is not int or pin['revision']!=1 or type(pin['sensitive']) is not bool or pin['state']!='active':
                raise ValueError('Invalid source pin')
            source=deepcopy(_source(data,job['scope_id'],pin['source_id']))
            if source['sha256']!=pin['sha256'] or source['sensitive']!=pin['sensitive']:
                raise ValueError('Invalid retained source binding')
            # Withdrawal changes eligibility, not retained result readability.
            source['state']='active'
            sources.append(source)
        if len({s['id'] for s in sources})!=len(sources):
            raise ValueError('Duplicate curation source')
        proposals=job['proposals']
        if type(proposals) is not list or len(proposals)>4 or (job['state']=='attempted' and proposals):
            raise ValueError('Invalid curation proposals')
        if job['state']=='ready':
            candidates=[]
            for proposal in proposals:
                citation=proposal['sources'][0]
                _,source_id,start,end=citation['ref'].split(':')
                candidates.append(dict(source_id=source_id,sha256=citation['sha256'],quote=proposal['text'],start=int(start),end=int(end),title=proposal['title']))
            if validate_model_proposals(_wire(dict(candidates=candidates)),sources)!=proposals:
                raise ValueError('Invalid proposal provenance')
        _validate_acceptance(data,job)


def _validate_acceptance(data,job):
    proposals=job['proposals']
    if type(job['accepted']) is not dict or any(type(k) is not str or k not in {str(i) for i in range(len(proposals))} or type(v) is not str or re.fullmatch(r'rec_[0-9a-f]{32}',v) is None for k,v in job['accepted'].items()):
        raise ValueError('Invalid proposal acceptance')
    if job['revision']!=(1 if job['state']=='attempted' else 2+len(job['accepted'])):
        raise ValueError('Invalid curation revision')
    if len(set(job['accepted'].values()))!=len(job['accepted']):
        raise ValueError('Duplicate accepted record')
    for record_id in job['accepted'].values():
        record=data['records'].get(record_id) or data['tombstones'].get(record_id)
        if record is None or record['scope_id']!=job['scope_id']:
            raise ValueError('Invalid accepted record ownership')


class CurationJobs:
    def __init__(self):
        self._lock=threading.RLock()
        self._closed=False
        self._transport=None
        self._ledger=None
        self._previews={}
        self._response_model=None
        self._host=False

    def close(self):
        with self._lock:
            self._closed=True
            for item in self._previews.values():
                item['contract'].close()
            self._previews.clear()

    def _live(self):
        if self._closed:
            _fail('service_closed','Curation review service is closed')

    def prepare(self,source_ids,*,model='offline-test',max_output_tokens=512):
        if type(max_output_tokens) is not int or not 1<=max_output_tokens<=512:
            _fail('invalid_output_limit','Requested output token limit must be an integer from 1 to 512')
        route=None
        if self._host:
            from hermes_cli.plugin_organizer import organizer_route
            route=organizer_route()
            model=route['model']
        if self._transport is None and not self._host:
            _fail('curation_dispatch_unavailable','No authenticated production recipient is configured')
        from hermes_cli.plugin_memory import memory_owner,read_memory
        from hermes_cli.plugin_llm_transport import _durable_contract
        with self._lock:
            self._live()
            for key,item in list(self._previews.items()):
                if item['deadline']<=time.monotonic():
                    item['contract'].close()
                    del self._previews[key]
            if len(self._previews)>=16:
                _fail('preview_limit','Curation preview capacity reached')
            owner=memory_owner(version=1)
            if self._response_model is not None and model!=self._response_model:
                _fail('credential_route_changed','Model must match the reviewed dedicated route')
            if type(source_ids) is not list or not 1<=len(source_ids)<=4 or any(type(key) is not str for key in source_ids) or len(set(source_ids))!=len(source_ids):
                _fail('invalid_selection','Select one to four distinct current-chat sources')
            def inspect():
                with _transaction(owner) as (_,data,chat):
                    sources=[deepcopy(_source(data,chat,key)) for key in source_ids]
                    if len(_jobs(data))>=16:
                        _fail('job_limit','Retained curation job capacity reached')
                    if any(s['state']!='active' for s in sources) or sum(len(s['text'].encode()) for s in sources)>16384:
                        _fail('invalid_selection','Select active sources within the source byte budget')
                    rows=[dict(source_id=s['id'],sha256=s['sha256'],content_revision=1,state_revision=s['revision'],
                               title=s['title'],text=s['text'],sensitive=s['sensitive'],declared_reference=s['reference'],
                               declared_author=s['author'],native_origin=deepcopy(s.get('native_capture'))) for s in sources]
                    payload=dict(messages=[dict(role='system',content=_INSTRUCTIONS),
                                           dict(role='user',content=_wire(dict(sources=rows)))],temperature=0,max_tokens=max_output_tokens)
                    preference=None
                    if self._host:
                        from .model_preferences import _row
                        preference=deepcopy(_row(data,chat))
                        if preference['organizer']!={k:route[k] for k in ('provider','model','endpoint')}:
                            _fail('organizer_preference_mismatch','Saved organizer preference must exactly match the enrolled route')
                    return data['store_id'],_pins(sources),payload,preference
            store_id,pins,payload,preference=read_memory(owner,inspect)
            def freshness():
                with _transaction(owner) as (_,data,chat):
                    sources=_fresh(data,chat,dict(store_id=store_id,sources=pins))
                    if self._host:
                        from .model_preferences import _row
                        if _row(data,chat)!=preference:
                            _fail('organizer_preference_changed','Organizer preferences changed')
                    return _hash(dict(store_id=store_id,sources=_pins(sources)))
            if self._host:
                from hermes_cli.plugin_organizer import organizer_contract
                contract=organizer_contract(route,freshness_reader=freshness)
            else:
                contract=_durable_contract(self._transport,self._ledger,freshness_reader=freshness)
            prepared=contract.prepare(payload,model=model,expected_freshness=_hash(dict(store_id=store_id,sources=pins)))
            if self._response_model is not None:
                try:
                    self._transport._before_connect(prepared.wire)
                except BaseException:
                    contract.close()
                    raise
            job_id='job_'+uuid.uuid4().hex
            self._previews[prepared.token]=dict(owner=owner,store_id=store_id,sources=pins,prepared=prepared,contract=contract,job_id=job_id,preference=preference,deadline=time.monotonic()+300)
            return dict(preview_token=prepared.token,job_id=job_id,recipient=asdict(prepared.wire.recipient),
                        source_pins=deepcopy(pins),max_output_tokens=prepared.wire.max_output_tokens,max_payload_bytes=32768,
                        budget=dict(outbound_body_bytes=len(prepared.wire.body),outbound_body_bytes_limit=32768,
                                    response_body_bytes_limit=prepared.wire.max_response_bytes,
                                    requested_max_output_tokens=prepared.wire.max_output_tokens,
                                    input_token_count=None,monetary_limit=None,pricing_verified=False,
                                    timeout_seconds=prepared.wire.timeout_seconds,absolute_deadline=False),
                        cost_notice='Price is unknown. This request can incur provider charges. Token and byte limits are not a monetary cap; explicitly accept this before sending.',
                        egress_payload=json.loads(prepared.wire.body),payload_sha256=prepared.wire.payload_sha256,
                        expires_in_seconds=300,production_dispatch_supported=self._dispatch_available(),
                        notice=('Prepared from selected authorized sources and the enrolled organizer route. Sending requires separate explicit confirmation of this complete payload and unknown cost. Saving credentials/preferences is not egress consent. API compatibility and provider billing are not verified. Results require separate review.' if self._host else 'Local loopback qualification only. Explicit confirmation permits this exact test payload once; no production credentials or price authorization. Results require separate per-proposal review and record approval.'))

    def _dispatch_available(self):
        if not self._host:
            return False
        from hermes_cli.plugin_organizer import dispatch_available
        return dispatch_available()

    def cancel(self,preview_token):
        if self._host:
            from hermes_cli.plugin_organizer import _scope
            _scope()
        from hermes_cli.plugin_memory import memory_owner
        with self._lock:
            self._live()
            item=self._previews.get(preview_token) if type(preview_token) is str else None
            if item is None:
                _fail('preview_unavailable','Curation preview unavailable')
            if memory_owner(version=1)!=item['owner']:
                _fail('owner_changed','Curation preview belongs to another owner snapshot')
            item['contract'].close()
            del self._previews[preview_token]

    def _check_preference(self,data,chat,item):
        if self._host:
            from .model_preferences import _row
            if _row(data,chat)!=item['preference']:
                _fail('organizer_preference_changed','Organizer preferences changed')

    def execute(self,preview_token,*,confirm=False,payload_sha256=None,accept_unknown_cost=False):
        if self._host:
            from hermes_cli.plugin_organizer import _scope,dispatch_available,require_dispatch_ready
            _scope(write=True)
            if not dispatch_available():
                _fail('curation_dispatch_unavailable','Production organizer dispatch remains disabled; no attempt was started')
            require_dispatch_ready()
            if accept_unknown_cost is not True:
                _fail('cost_confirmation_required','Explicitly accept unknown provider charges and no enforced monetary cap')
        if confirm is not True:
            _fail('confirmation_required','Explicit exact-payload confirmation is required')
        from hermes_cli.plugin_memory import memory_owner,publish_memory,read_memory
        with self._lock:
            self._live()
            item=self._previews.get(preview_token) if type(preview_token) is str else None
            if item is None:
                _fail('preview_unavailable','Curation preview unavailable')
            owner=memory_owner(version=1)
            if owner!=item['owner']:
                _fail('owner_changed','Curation preview belongs to another owner snapshot')
            if self._host and payload_sha256!=item['prepared'].wire.payload_sha256:
                _fail('payload_changed','Confirm the exact reviewed payload hash')
            del self._previews[preview_token]
            if item['deadline']<=time.monotonic():
                item['contract'].close()
                _fail('preview_expired','Curation preview expired')
            prepared=item['prepared']
            def preflight():
                with _transaction(owner) as (_,data,chat):
                    _fresh(data,chat,item)
                    self._check_preference(data,chat,item)
                    return None
            try:
                read_memory(owner,preflight)
            except BaseException:
                item['contract'].close()
                raise
            # This read diagnoses already-stale previews without a publication
            # callback. The final write still checks again: intervening races or
            # postcommit errors retain native uncertain-outcome semantics.
            def start():
                with _transaction(owner,write=True) as (_,data,chat):
                    _fresh(data,chat,item)
                    self._check_preference(data,chat,item)
                    jobs=data.setdefault('private_curation',dict(schema=1,jobs={}))['jobs']
                    if len(jobs)>=16 or item['job_id'] in jobs:
                        _fail('job_limit','Curation job capacity or identity conflict')
                    jobs[item['job_id']]=dict(job_id=item['job_id'],scope_id=chat,store_id=item['store_id'],
                        owner_sha256=_owner_key(owner),revision=1,state='attempted',created_at=_now(),sources=item['sources'],
                        payload_sha256=prepared.wire.payload_sha256,attempt_id=prepared.attempt_id,
                        recipient=asdict(prepared.wire.recipient),model=prepared.wire.model,proposals=[],accepted={})
            try:
                publish_memory(owner,start)
            except BaseException:
                item['contract'].close()
                raise
            try:
                response=item['contract'].execute(preview_token,confirm=True,payload_sha256=prepared.wire.payload_sha256)
                if self._response_model is not None or self._host:
                    from hermes_cli.plugin_llm_credentials import parse_chat_completion
                    raw=parse_chat_completion(response,expected_model=prepared.wire.model,max_output_tokens=prepared.wire.max_output_tokens)
                else:
                    # Legacy uncredentialed LOCAL qualification fixture only.
                    raw=response.decode('utf-8')
                def finish():
                    with _transaction(owner,write=True) as (_,data,chat):
                        job=_owned(data,chat,item['job_id'])
                        sources=_fresh(data,chat,job)
                        self._check_preference(data,chat,item)
                        proposals=validate_model_proposals(raw,sources)
                        job.update(state='ready',revision=2,proposals=proposals)
                        return _summary(job)
                return publish_memory(owner,finish)
            except Exception:
                _fail('curation_outcome_unconfirmed','Curation attempt has no confirmed usable result; inspect the retained job and never automatically resend')
            finally:
                item['contract'].close()

    def list(self,*,limit=16,before=None):
        if type(limit) is not int or not 1<=limit<=16 or (before is not None and type(before) is not str):
            _fail('invalid_pagination','Use a bounded curation page')
        from hermes_cli.plugin_memory import memory_owner,read_memory
        with self._lock:
            self._live()
            owner=memory_owner(version=1)
            def inspect():
                with _transaction(owner) as (_,data,chat):
                    rows=sorted((j for j in _jobs(data).values() if j['scope_id']==chat and (before is None or j['job_id']<before)),key=lambda j:j['job_id'],reverse=True)
                    selected=rows[:limit]
                    return dict(jobs=[_summary(j) for j in selected],next_before=selected[-1]['job_id'] if len(rows)>limit else None)
            return read_memory(owner,inspect)

    def get(self,job_id):
        from hermes_cli.plugin_memory import memory_owner,read_memory
        with self._lock:
            self._live()
            owner=memory_owner(version=1)
            def inspect():
                with _transaction(owner) as (_,data,chat):
                    job=_owned(data,chat,job_id)
                    result=dict(job=_summary(job)|dict(proposals=deepcopy(job['proposals']),accepted_records=deepcopy(job['accepted']),
                        recipient=deepcopy(job['recipient']),model=job['model'],payload_sha256=job['payload_sha256']),inspection_only=True,content_role='untrusted_model_proposals')
                    if len(_wire(result).encode())>65536:
                        _fail('result_limit','Full result exceeds inspection limit; no partial review is returned')
                    return result
            return read_memory(owner,inspect)

    def accept(self,job_id,proposal_index,expected_revision,*,confirm=False):
        if confirm is not True or type(proposal_index) is not int or type(expected_revision) is not int:
            _fail('confirmation_required','Explicit proposal selection and revision confirmation required')
        from hermes_cli.plugin_memory import memory_owner,publish_memory
        with self._lock:
            self._live()
            owner=memory_owner(version=1)
            def create():
                with _transaction(owner,write=True) as (_,data,chat):
                    job=_owned(data,chat,job_id)
                    _fresh(data,chat,job)
                    if job['owner_sha256']!=_owner_key(owner):
                        _fail('owner_changed','Curation result belongs to another canonical owner')
                    if job['state']!='ready' or job['revision']!=expected_revision or not 0<=proposal_index<len(job['proposals']) or str(proposal_index) in job['accepted']:
                        _fail('proposal_conflict','Review the current unconsumed proposal revision')
                    if _record_count(data)>=512:
                        _fail('store_limit','Private record capacity reached')
                    proposal=job['proposals'][proposal_index]
                    fields={k:deepcopy(v) for k,v in proposal.items() if k not in ('proposal_kind','title_status','source_origin','approval_required')}
                    key,now='rec_'+uuid.uuid4().hex,_now()
                    if key in data['records'] or key in data['tombstones']:
                        _fail('revision_conflict','Record identity conflict')
                    record=dict(id=key,revision=1,scope_id=chat,created_at=now,updated_at=now,**fields)
                    data['records'][key]=record
                    job['accepted'][str(proposal_index)]=key
                    job['revision']+=1
                    return dict(record=deepcopy(record),job=_summary(job))
            return publish_memory(owner,create)


def _qualification_workflow(transport,ledger):
    from hermes_cli.plugin_llm_transport import _LoopbackTransport,AttemptLedger
    if type(transport) is not _LoopbackTransport or type(ledger) is not AttemptLedger:
        _fail('qualification_only','Only the private local loopback qualification adapter is supported')
    service=CurationJobs()
    service._transport,service._ledger=transport,ledger
    return service


def _credential_qualification_workflow(resolver,slot_id,ledger):
    from hermes_cli.plugin_llm_credentials import _CredentialLoopbackTransport
    from hermes_cli.plugin_llm_transport import AttemptLedger
    from hermes_cli.plugin_memory import memory_owner
    if type(ledger) is not AttemptLedger:
        _fail('qualification_only','A durable test ledger is required')
    transport=_CredentialLoopbackTransport(resolver,slot_id,memory_owner(version=1))
    service=CurationJobs()
    service._transport,service._ledger=transport,ledger
    service._response_model=transport._route['model']
    return service


def register_curation_jobs_rpc(ctx):
    try:
        from hermes_cli.plugin_memory import memory_capabilities
    except ImportError:
        return False
    cap=memory_capabilities()
    if not callable(getattr(ctx,'register_rpc',None)) or not cap.get('record_read') or not cap.get('publication'):
        return False
    from .private_workspace_rpc import _fields
    service=CurationJobs()
    def list_jobs(params,**kwargs):
        _fields(params,(),('limit','before'))
        return service.list(limit=params.get('limit',16),before=params.get('before'))
    def get(params,**kwargs):
        _fields(params,('job_id',))
        return service.get(params['job_id'])
    def accept(params,**kwargs):
        _fields(params,('job_id','proposal_index','expected_revision','confirm'))
        return service.accept(params['job_id'],params['proposal_index'],params['expected_revision'],confirm=params['confirm'])
    organizer=CurationJobs()
    organizer._host=True
    def organizer_preview(params,**kwargs):
        _fields(params,('source_ids',),('max_output_tokens',))
        return organizer.prepare(params['source_ids'],max_output_tokens=params.get('max_output_tokens',512))
    def organizer_execute(params,**kwargs):
        _fields(params,('preview_token','confirm','payload_sha256','accept_unknown_cost'))
        return organizer.execute(params['preview_token'],confirm=params['confirm'],payload_sha256=params['payload_sha256'],accept_unknown_cost=params['accept_unknown_cost'])
    def organizer_cancel(params,**kwargs):
        _fields(params,('preview_token',))
        organizer.cancel(params['preview_token'])
        return {'cancelled':True}
    ctx.register_rpc('private.curation.organizer.preview',organizer_preview,memory_scope='local_read')
    ctx.register_rpc('private.curation.organizer.execute',organizer_execute)
    ctx.register_rpc('private.curation.organizer.cancel',organizer_cancel,memory_scope='local_read')
    if callable(getattr(ctx,'on_unload',None)):
        ctx.on_unload(organizer.close)
    ctx.register_rpc('private.curation.jobs.list',list_jobs,memory_scope='local_read')
    ctx.register_rpc('private.curation.jobs.get',get,memory_scope='local_read')
    ctx.register_rpc('private.curation.jobs.accept',accept)
    if callable(getattr(ctx,'on_unload',None)):
        ctx.on_unload(service.close)
    return True
