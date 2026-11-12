import * as SDK from '@hermes/plugin-sdk';
import { createElement as h, useLayoutEffect, useState, useSyncExternalStore } from 'react';

const read = atom => atom?.get?.();
const states = ['all', 'pending', 'approved', 'invalidated'];
export const manualSourceAllowed = (reference, project) => !project || typeof reference === 'string' && !reference.trimStart().startsWith('elm-snapshot-v1:');
export function reviewIdentity(host, epoch) {
  const s = host?.state || {}, owner = read(s.focusedSessionOwner);
  const session = read(s.focusedSessionId), stored = read(s.focusedStoredSessionId);
  const profile = read(s.focusedSessionProfile), connection = read(s.connectionId);
  const ambient = read(s.profile), gateway = read(s.gateway);
  const key = JSON.stringify([session, stored, profile, connection, ambient, gateway, owner, epoch()]);
  const error = !session || !stored ? 'Focus an existing saved chat, then refresh.'
    : !owner || !profile || !connection || !ambient ? 'Focused chat ownership is unavailable.'
    : owner.profile !== profile || owner.connectionId !== connection || profile !== ambient
      ? 'Select this chat’s owning profile and connection before reviewing memory.'
    : gateway !== 'open' ? 'Reconnect the gateway, then refresh.'
    : typeof host?.request !== 'function' ? 'This host does not support authenticated memory requests.' : '';
  return { key, session, error };
}
const exactKeys=(value,keys)=>value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).length===keys.length&&Object.keys(value).every(k=>keys.includes(k));
export function validOrganizerPreview(p,ids,requested=512){
  const hash=x=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x);
  if(!exactKeys(p,['preview_token','job_id','recipient','source_pins','max_output_tokens','max_payload_bytes','cost_notice','egress_payload','payload_sha256','expires_in_seconds','production_dispatch_supported','notice','budget'])||typeof p.preview_token!=='string'||!/^[-_A-Za-z0-9]{43}$/.test(p.preview_token)||typeof p.job_id!=='string'||!/^job_[a-f0-9]{32}$/.test(p.job_id)||p.expires_in_seconds!==300||typeof p.production_dispatch_supported!=='boolean'||p.max_output_tokens!==requested||!Number.isInteger(requested)||requested<1||requested>512||p.max_payload_bytes!==32768||!hash(p.payload_sha256)||typeof p.notice!=='string'||p.notice.length>2048||typeof p.cost_notice!=='string'||p.cost_notice.length>2048)return false;
  const r=p.recipient;
  if(!exactKeys(r,['provider','endpoint','credential_mode','credential_slot','credential_version','route_sha256','redirects','automatic_retries','fallback','environment_proxy'])||typeof r.provider!=='string'||!/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(r.provider)||r.credential_mode!=='host-enrolled-slot'||r.credential_slot!=='organizer'||!Number.isSafeInteger(r.credential_version)||r.credential_version<1||!hash(r.route_sha256)||r.redirects!==false||r.automatic_retries!==0||r.fallback!==false||r.environment_proxy!==false)return false;
  try{const url=new URL(r.endpoint);if(url.protocol!=='https:'||url.username||url.password||url.search||url.hash||url.pathname!=='/v1/chat/completions'||r.endpoint.length>256)return false}catch{return false}
  if(!Array.isArray(p.source_pins)||p.source_pins.length!==ids.length||new Set(p.source_pins.map(s=>s?.source_id)).size!==ids.length||!p.source_pins.every(s=>exactKeys(s,['source_id','sha256','revision','sensitive','state'])&&ids.includes(s.source_id)&&hash(s.sha256)&&Number.isSafeInteger(s.revision)&&s.revision>0&&typeof s.sensitive==='boolean'&&s.state==='active'))return false;
  const limits=p.budget;
  if(!exactKeys(limits,['outbound_body_bytes','outbound_body_bytes_limit','response_body_bytes_limit','requested_max_output_tokens','input_token_count','monetary_limit','pricing_verified','timeout_seconds','absolute_deadline'])||!Number.isSafeInteger(limits.outbound_body_bytes)||limits.outbound_body_bytes<1||limits.outbound_body_bytes>32768||limits.outbound_body_bytes_limit!==32768||limits.response_body_bytes_limit!==8192||limits.requested_max_output_tokens!==requested||limits.input_token_count!==null||limits.monetary_limit!==null||limits.pricing_verified!==false||limits.timeout_seconds!==10||limits.absolute_deadline!==false)return false;
  const b=p.egress_payload;
  return exactKeys(b,['model','messages','temperature','max_tokens'])&&typeof b.model==='string'&&b.model.length>0&&b.model.length<=128&&b.temperature===0&&b.max_tokens===requested&&Array.isArray(b.messages)&&b.messages.length>=1&&b.messages.length<=8&&b.messages.every(m=>exactKeys(m,['role','content'])&&['system','user','assistant'].includes(m.role)&&typeof m.content==='string')&&new TextEncoder().encode(JSON.stringify(b)).length<=32768;
}
const blank = (key, error = '') => ({ ownerKey: key, error, busy: false, notice: '', ready: false,
  initialized: null, records: [], trash: [], selected: null, preview: null, action: null,
  filter: 'all', next: null, trashNext: null, uncertain: false, projectStatus: null, binding: null, projectKey: null, listConsent: null, trashConsent: null, sources: [], sourceNext: null, selectedSource: null, lastSource: null, recallSettings: null, captureSettings: null, capturedTurns: [], captureNext: null, curationStatus: null, curationPreview: null, organizerPreview: null, curationJobs: [], curationJobsNext: null, selectedJob: null, acceptedProposal: null, importReceipts: [], importNext: null, selectedImport: null, folderStatus: null });
const projectKey = (binding, status) => JSON.stringify([binding?.selected_project_id, binding?.project_binding_revision, status?.consent_revision, status?.consent_granted, status?.project_read_authorized, status?.consent_version, status?.context_key]);
const matchingBinding = (binding, status) => binding?.selected_project_id === status?.selected_project_id && binding?.project_binding_revision === status?.project_binding_revision && typeof status?.context_key === 'string' && !!status.context_key;

/** Ephemeral UI state only. The host, never a caller-supplied scope, authorizes each request. */
export function createReviewController(host, epoch = () => 0, lane = 'private') {
  if (!['private', 'project'].includes(lane)) throw new Error('Unsupported review lane');
  let identity = reviewIdentity(host, epoch), state = blank(identity.key, identity.error);
  let generation = 0, disposed = false;
  const listeners = new Set(), subscriptions = [];
  const publish = patch => { state = { ...state, ...patch }; for (const fn of listeners) fn(); };
  function sync() {
    const next = reviewIdentity(host, epoch);
    if (next.key !== identity.key) {
      identity = next; generation++; state = blank(next.key, next.error);
      for (const fn of listeners) fn();
    }
    return next;
  }
  for (const atom of Object.values(host?.state || {})) {
    if (typeof atom?.subscribe === 'function') subscriptions.push(atom.subscribe(sync));
  }
  async function operation(fn, mutation = false, guard = true, readError = null) {
    const current = sync();
    if (disposed || state.busy || current.error || (mutation && state.uncertain)) return;
    const stamp = ++generation, socket = host.getGateway?.(), expectedProject = state.projectKey, expectedConsent = state.projectStatus?.consent_revision, expectedContext = state.projectStatus?.context_key;
    const valid = () => !disposed && sync().key === current.key && generation === stamp &&
      (!host.getGateway || host.getGateway() === socket);
    const rpc = async (method, params = {}) => {
      if (!valid()) throw new Error('context changed');
      const reply = await host.request('plugin.elm.' + ((method.startsWith('workspace.') || method.startsWith('chat_folders.')) ? method : lane + '.' + method), { ...params, session_id: current.session });
      if (!valid()) throw new Error('context changed');
      if (lane === 'project' && guard && ['list', 'get', 'trash', 'delete_preview'].includes(method) && (reply.consent_revision !== expectedConsent || reply.context_key !== expectedContext)) throw new Error('Consent changed during read');
      return reply;
    };
    publish({ busy: true, error: '', notice: '', action: null, preview: null });
    try {
      if (lane === 'project' && guard) {
        const binding = await rpc('workspace.status'), status = await rpc('status');
        if (!matchingBinding(binding, status) || !expectedProject || projectKey(binding, status) !== expectedProject || status.project_read_authorized !== true || status.consent_version !== 2) {
          publish({ records: [], trash: [], selected: null, projectStatus: null, projectKey: null, ready: false });
          throw new Error('Project snapshot changed');
        }
      }
      const patch = await fn(rpc);
      if (valid()) publish({ ...patch, busy: false });
    } catch {
      if (valid()) publish({ busy: false, selected: null, selectedSource: null, recallSettings: null, captureSettings: null, capturedTurns: [], captureNext: null, curationStatus: null, curationPreview: null, organizerPreview: null, curationJobs: [], curationJobsNext: null, selectedJob: null, importReceipts: [], importNext: null, selectedImport: null, folderStatus: null, preview: null, action: null,
        ...(lane === 'project' ? { records: [], trash: [], projectStatus: null, projectKey: null, ready: false } : {}),
        uncertain: mutation || state.uncertain,
        error: mutation ? 'The outcome is uncertain. Do not repeat the action. Refresh records and trash to inspect what happened.'
          : readError || 'Memory could not be read. Check host support and ownership, then refresh. No automatic retry.' });
    }
  }
  const api = {
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    getSnapshot: () => state,
    currentKey: () => reviewIdentity(host, epoch).key,
    sync,
    dispose() { disposed = true; generation++; for (const stop of subscriptions) stop(); listeners.clear(); state = blank('disposed'); },
    refresh() {
      if (lane === 'project') {
        sync(); if (state.busy) return;
        publish({ records: [], trash: [], selected: null, preview: null, action: null, projectStatus: null, projectKey: null, ready: false });
        return operation(async rpc => {
          const binding = await rpc('workspace.status');
          let status;
          try { status = await rpc('status'); } catch {
            return { binding, ready: true, initialized: false, projectStatus: null, projectKey: null,
              error: 'Project consent is unavailable. If the binding was archived or deleted, explicitly unbind first, refresh, then review revocation. No access was enabled.' };
          }
          if (!matchingBinding(binding, status)) throw new Error('Project binding changed during refresh');
          const base = { binding, projectStatus: status, projectKey: projectKey(binding, status), ready: true,
            initialized: status.initialized, selected: null, uncertain: false };
          if (status.project_read_authorized !== true || status.consent_version !== 2) return { ...base, records: [], trash: [], next: null, trashNext: null,
            notice: 'No effective project access. Binding and stored consent are not permission by themselves.' };
          const [list, trash] = await Promise.all([rpc('list', { state: state.filter }), rpc('trash')]);
          if (list.consent_revision !== status.consent_revision || trash.consent_revision !== status.consent_revision || list.context_key !== status.context_key || trash.context_key !== status.context_key) throw new Error('Consent changed during refresh');
          return { ...base, records: list.records, next: list.next_before, listConsent: list.consent_revision, trash: trash.items, trashNext: trash.next_before, trashConsent: trash.consent_revision,
            notice: 'Project snapshot refreshed. Independently consenting chats of this principal share this project pool.' };
        }, false, false);
      }
      return operation(async rpc => {
        const status = await rpc('status');
        if (!status.initialized) return { ...blank(identity.key), ready: true, initialized: false };
        const [list, trash] = await Promise.all([rpc('list', { state: state.filter }), rpc('trash')]);
        return { ready: true, initialized: true, selectedSource: null, records: list.records, next: list.next_before,
          trash: trash.items, trashNext: trash.next_before, selected: null, uncertain: false,
          notice: 'Current chat refreshed. Source labels are declared provenance, not verified truth.' };
      });
    },
    refreshChatFolders(ownerKey = state.ownerKey) {
      if (lane !== 'private' || sync().key !== ownerKey) return;
      return operation(async rpc => ({ folderStatus: await rpc('chat_folders.status'), uncertain:false }));
    },
    stageChatFolder(kind, payload, ownerKey = state.ownerKey, renderedStatus = state.folderStatus) {
      sync(); const status=state.folderStatus;
      if (lane !== 'private' || ownerKey!==identity.key || identity.error || state.busy || state.uncertain || !status || renderedStatus!==status || !['create','file','undo','rename','remove'].includes(kind)) return;
      if (kind==='create' && (typeof payload!=='string' || !payload.trim() || [...payload].length>80)) return;
      if (kind==='file' && payload!==null && !status.folders.some(folder=>folder.id===payload)) return;
      if (kind==='undo' && !status.undo_available) return;
      if (kind==='rename' && (!payload || typeof payload!=='object' || !status.folders.some(folder=>folder.id===payload.folder_id) || typeof payload.label!=='string' || !payload.label.trim() || payload.label!==payload.label.trim() || [...payload.label].length>80)) return;
      if (kind==='remove' && !status.folders.some(folder=>folder.id===payload && folder.removable===true)) return;
      if (kind==='rename') payload={folder_id:payload.folder_id,label:payload.label};
      publish({ action: {kind:'folder_'+kind,ownerKey:identity.key,payload,target:{revision:status.revision,context_key:status.context_key,current_session_id:status.current_session_id}, label:kind==='rename'?`${status.folders.find(folder=>folder.id===payload.folder_id).label} → ${payload.label}`:['file','remove'].includes(kind)?(status.folders.find(folder=>folder.id===payload)?.label || 'Unfiled'):payload},preview:null });
    },
    chatFolderSnapshot() {
      const current=sync(), status=state.folderStatus, owner=read(host.state?.focusedSessionOwner);
      if (lane!=='private' || current.error || !status || state.busy || state.uncertain || !owner) return null;
      return { owner:{connectionId:owner.connectionId,profile:owner.profile,storedSessionId:read(host.state.focusedStoredSessionId),runtimeSessionId:current.session,epoch:epoch()},context_key:status.context_key,revision:status.revision,folders:structuredClone(status.folders),members:structuredClone(status.members) };
    },
    previewImport(exportText, ownershipDeclared, ownerKey = state.ownerKey) {
      if (lane !== 'private' || sync().key !== ownerKey || ownershipDeclared !== true || typeof exportText !== 'string' || !exportText || new TextEncoder().encode(exportText).length > 65536) return;
      return operation(async rpc => ({ preview: await rpc('import.preview', { export_text: exportText, ownership_declared: true }),
        action: { kind: 'import_copy', ownerKey: identity.key, payload: { export_text: exportText, ownership_declared: true } } }));
    },
    refreshImports(before = null, ownerKey = state.ownerKey) {
      if (lane !== 'private' || sync().key !== ownerKey) return;
      return operation(async rpc => {
        const reply = await rpc('import.list', before ? { before } : {});
        return { importReceipts: before ? [...state.importReceipts, ...reply.receipts] : reply.receipts, importNext: reply.next_before, selectedImport: null };
      });
    },
    inspectImport(batchId, ownerKey = state.ownerKey) {
      if (lane !== 'private' || sync().key !== ownerKey) return;
      return operation(async rpc => ({ selectedImport: (await rpc('import.get', { batch_id: batchId })).receipt }));
    },
    refreshJobs(before = null, ownerKey = state.ownerKey) {
      if (lane !== 'private' || sync().key !== ownerKey) return;
      return operation(async rpc => {
        const reply = await rpc('curation.jobs.list', before ? { before } : {});
        return { curationJobs: before ? [...state.curationJobs, ...reply.jobs] : reply.jobs, curationJobsNext: reply.next_before, selectedJob: null };
      });
    },
    inspectJob(jobId, ownerKey = state.ownerKey) {
      if (lane !== 'private' || sync().key !== ownerKey) return;
      return operation(async rpc => ({ selectedJob: (await rpc('curation.jobs.get', { job_id: jobId })).job }));
    },
    stageProposal(index, ownerKey = state.ownerKey, renderedJob = state.selectedJob) {
      sync();
      const job = state.selectedJob;
      if (lane !== 'private' || ownerKey !== identity.key || identity.error || state.busy || state.uncertain || !job || job !== renderedJob || job.state !== 'ready' || !Number.isInteger(index) || index < 0 || !job.proposals?.[index] || job.accepted_indexes.includes(index)) return;
      publish({ action: { kind: 'proposal_accept', ownerKey, target: { job_id: job.job_id, revision: job.revision, index }, payload: structuredClone(job.proposals[index]) }, preview: null });
    },
    refreshCuration(ownerKey = state.ownerKey) {
      if (lane !== 'private' || sync().key !== ownerKey) return;
      return operation(async rpc => {
        const status = await rpc('curation.status');
        if (status.dispatch_supported !== false || status.external_egress_enabled !== false) throw new Error('Unsupported curation contract');
        return { curationStatus: status, curationPreview: null };
      });
    },
    previewCuration(sourceIds, ownerKey = state.ownerKey, renderedStatus = state.curationStatus) {
      if (lane !== 'private' || sync().key !== ownerKey || !renderedStatus || renderedStatus !== state.curationStatus) return;
      if (!Array.isArray(sourceIds) || sourceIds.length < 1 || sourceIds.length > 4 || new Set(sourceIds).size !== sourceIds.length || sourceIds.some(id => typeof id !== 'string' || !id || id !== id.trim())) return;
      const ids = [...sourceIds];
      return operation(async rpc => {
        const preview = await rpc('curation.preview', { source_ids: ids });
        if (preview.dispatch_supported !== false || preview.consent_granted !== false || preview.payload_kind !== 'local_candidate_not_dispatchable' || (preview.external_egress_enabled !== undefined && preview.external_egress_enabled !== false) || !preview.destination || Object.values(preview.destination).some(value => value !== null)) throw new Error('Unsupported destination contract');
        return { curationPreview: preview };
      });
    },
    prepareOrganizer(sourceIds, ownerKey = state.ownerKey, maxOutputTokens=512) {
      if (lane !== 'private' || sync().key !== ownerKey || state.busy || !Number.isInteger(maxOutputTokens)||maxOutputTokens<1||maxOutputTokens>512|| !Array.isArray(sourceIds) || sourceIds.length<1 || sourceIds.length>4 || new Set(sourceIds).size!==sourceIds.length || sourceIds.some(id=>typeof id!=='string'||!id||id!==id.trim())) return;
      const ids=[...sourceIds], previous=state.organizerPreview;
      publish({organizerPreview:null});
      return operation(async rpc=>{
        if(previous) await rpc('curation.organizer.cancel',{preview_token:previous.preview_token});
        const result=await rpc('curation.organizer.preview',{source_ids:ids,max_output_tokens:maxOutputTokens});
        if(!validOrganizerPreview(result,ids,maxOutputTokens))throw new Error('Unsupported organizer preparation');
        return {organizerPreview:result};
      });
    },
    executeOrganizer(accepted, ownerKey=state.ownerKey, renderedPreview=state.organizerPreview) {
      if(lane!=='private'||sync().key!==ownerKey||state.busy||state.uncertain||accepted!==true||!renderedPreview||renderedPreview!==state.organizerPreview||renderedPreview.production_dispatch_supported!==true)return;
      publish({organizerPreview:null});
      return operation(async rpc=>{
        const job=await rpc('curation.organizer.execute',{preview_token:renderedPreview.preview_token,payload_sha256:renderedPreview.payload_sha256,confirm:true,accept_unknown_cost:true});
        if(job?.job_id!==renderedPreview.job_id||job.state!=='ready')throw new Error('Organizer outcome unconfirmed');
        return {notice:'Organizer result retained. Review the job and each proposal separately; no memory was approved automatically.'};
      },true);
    },
    cancelOrganizer(ownerKey=state.ownerKey, renderedPreview=state.organizerPreview) {
      if(lane!=='private'||sync().key!==ownerKey||state.busy||!renderedPreview||renderedPreview!==state.organizerPreview)return;
      publish({organizerPreview:null});
      return operation(async rpc=>{const reply=await rpc('curation.organizer.cancel',{preview_token:renderedPreview.preview_token});if(reply?.cancelled!==true)throw new Error('Cancellation unconfirmed');return {notice:'Prepared organizer preview cancelled. Nothing was sent.'};});
    },
    refreshCaptureSettings(ownerKey = state.ownerKey) {
      if (lane !== 'private' || sync().key !== ownerKey) return;
      return operation(async rpc => ({ captureSettings: await rpc('capture_settings.status') }));
    },
    previewCaptureSettings(payload, ownerKey = state.ownerKey, renderedSettings = state.captureSettings) {
      if (lane !== 'private' || sync().key !== ownerKey || !renderedSettings || renderedSettings !== state.captureSettings || state.uncertain) return;
      const captured = structuredClone(payload);
      if (typeof captured.enabled !== 'boolean' || !Number.isInteger(captured.max_turns) || captured.max_turns < 1 || captured.max_turns > 32 || !Number.isInteger(captured.max_utf8_bytes) || captured.max_utf8_bytes < 2048 || captured.max_utf8_bytes > 32768 || (captured.enabled && !renderedSettings.host_supported)) return;
      return operation(async rpc => ({ preview: await rpc('capture_settings.preview', captured),
        action: { kind: 'capture_settings', payload: captured, ownerKey: identity.key } }));
    },
    refreshCapturedTurns(before = null, ownerKey = state.ownerKey) {
      if (lane !== 'private' || sync().key !== ownerKey) return;
      return operation(async rpc => {
        const reply = await rpc('capture.list', before ? { before } : {});
        return { capturedTurns: before ? [...state.capturedTurns, ...reply.turns] : reply.turns, captureNext: reply.next_before };
      });
    },
    refreshRecall(ownerKey = state.ownerKey) {
      if (lane !== 'private' || sync().key !== ownerKey) return;
      return operation(async rpc => ({ recallSettings: await rpc('recall_settings.status') }));
    },
    previewRecall(payload, ownerKey = state.ownerKey, renderedSettings = state.recallSettings) {
      if (lane !== 'private' || sync().key !== ownerKey || !renderedSettings || renderedSettings !== state.recallSettings || state.uncertain) return;
      const captured = structuredClone(payload);
      if (typeof captured.enabled !== 'boolean' || !Number.isInteger(captured.max_records) || captured.max_records < 1 || captured.max_records > 8 || !Number.isInteger(captured.max_utf8_bytes) || captured.max_utf8_bytes < 512 || captured.max_utf8_bytes > 16384 || (captured.enabled && !renderedSettings.host_supported)) return;
      return operation(async rpc => ({ preview: await rpc('recall_settings.preview', captured),
        action: { kind: 'recall_settings', payload: captured, ownerKey: identity.key } }));
    },
    previewConsent(action, ownerKey = state.ownerKey) {
      if (lane !== 'project' || sync().key !== ownerKey || !['grant', 'revoke'].includes(action)) return;
      return operation(async rpc => ({ preview: await rpc('consent.preview', { action }),
        action: { kind: 'consent', payload: action, ownerKey: identity.key } }), false, false);
    },
    previewBinding(projectId, ownerKey = state.ownerKey) {
      if (lane !== 'project' || sync().key !== ownerKey) return;
      if (projectId !== null && (typeof projectId !== 'string' || !projectId.trim() || projectId !== projectId.trim())) return;
      return operation(async rpc => ({ preview: await rpc('workspace.project.preview', { project_id: projectId }),
        action: { kind: 'binding', payload: projectId, ownerKey: identity.key } }), false, false);
    },
    filter(filter) { if (!states.includes(filter) || state.busy) return; publish({ filter, selected: null, action: null }); return api.refresh(); },
    more(trash = false, ownerKey = state.ownerKey) {
      if (sync().key !== ownerKey) return;
      const cursor = trash ? state.trashNext : state.next;
      if (!cursor) return;
      return operation(async rpc => {
        const reply = await rpc(trash ? 'trash' : 'list', { before: cursor, ...(trash ? {} : { state: state.filter }) });
        return trash ? { trash: [...state.trash, ...reply.items], trashNext: reply.next_before, trashConsent: reply.consent_revision }
          : { records: [...state.records, ...reply.records], next: reply.next_before, listConsent: reply.consent_revision };
      });
    },
    inspect(id, ownerKey = state.ownerKey) { if (sync().key !== ownerKey) return; return operation(async rpc => ({ selected: await rpc('get', { record_id: id }) })); },
    stage(kind, payload = null, ownerKey = state.ownerKey, target = state.selected?.record, renderedProjectKey = state.projectKey) {
      sync(); if (ownerKey !== identity.key || (lane === 'project' && renderedProjectKey !== state.projectKey) || state.busy || state.uncertain || identity.error) return;
      if (['approve', 'correct'].includes(kind) && (!target || !state.selected ||
          target.id !== state.selected.record.id || target.revision !== state.selected.record.revision)) return;
      if (kind === 'restore' && !state.trash.some(item => item.recovery_id === payload)) return;
      if (kind === 'setup' && (lane !== 'private' || state.initialized !== false)) return;
      if (kind === 'create' && (!state.ready || !state.initialized)) return;
      if (kind === 'create' && lane === 'project' && payload?.sources?.some(source => !manualSourceAllowed(source.ref, true))) {
        publish({ action: null, preview: null, error: 'Private snapshot references cannot be used as project source authority. Use a declared external reference; nothing is copied or shared.' }); return;
      }
      if (kind === 'source_withdraw') {
        const source = state.selectedSource?.source;
        if (lane !== 'private' || !source || !target || target.source_id !== source.source_id || target.revision !== source.revision) return;
      }
      if (lane === 'project' && (state.projectStatus?.project_read_authorized !== true || state.projectStatus?.consent_version !== 2)) return;
      const stagedPayload = payload && typeof payload === 'object' ? structuredClone(payload) : payload;
      publish({ action: { kind, payload: stagedPayload, ownerKey: identity.key, projectKey: state.projectKey, consentRevision: kind === 'create' ? state.projectStatus?.consent_revision : kind === 'restore' ? state.trashConsent : state.selected?.consent_revision, target: target && { id: target.id, source_id: target.source_id, revision: target.revision, sha256: target.sha256, title: target.title } }, preview: null });
    },
    refreshSources(before = null, ownerKey = state.ownerKey) {
      if (lane !== 'private' || sync().key !== ownerKey || !state.initialized) return;
      return operation(async rpc => {
        const reply = await rpc('source.list', before ? { before } : {});
        return { sources: before ? [...state.sources, ...reply.sources] : reply.sources,
          sourceNext: reply.next_before, selectedSource: null };
      });
    },
    inspectSource(sourceId, ownerKey = state.ownerKey) {
      if (lane !== 'private' || sync().key !== ownerKey || !state.initialized) return;
      return operation(async rpc => ({ selectedSource: await rpc('source.get', { source_id: sourceId }) }));
    },
    previewSource(payload, ownerKey = state.ownerKey) {
      if (lane !== 'private' || sync().key !== ownerKey || !state.ready || !state.initialized) return;
      const captured = structuredClone(payload);
      return operation(async rpc => ({ preview: await rpc('source.preview', captured),
        action: { kind: 'source_capture', payload: captured, ownerKey: identity.key } }));
    },
    previewExcerpt(payload, ownerKey = state.ownerKey, source = state.selectedSource?.source) {
      if (lane !== 'private' || sync().key !== ownerKey || !source || source.state !== 'active') return;
      const selected = state.selectedSource?.source;
      if (!selected || source.source_id !== selected.source_id || source.revision !== selected.revision || source.sha256 !== selected.sha256) return;
      const captured = structuredClone(payload), target = { source_id: source.source_id, revision: source.revision, sha256: source.sha256 };
      return operation(async rpc => {
        const preview = await rpc('excerpt.preview', { ...captured, source_id: target.source_id });
        if (preview.source_id !== target.source_id || preview.source_revision !== target.revision || preview.sha256 !== target.sha256) throw new Error('Source snapshot changed');
        return { preview, action: { kind: 'excerpt', payload: captured, target, ownerKey: identity.key } };
      }, false, true, 'Exact excerpt preview is unavailable. Check the source state and exact quote. Repeated matches require an explicit occurrence; no match is chosen automatically.');
    },
    cancel() { publish({ action: null, preview: null }); },
    previewDelete(ownerKey = state.ownerKey, target = state.selected?.record) {
      if (sync().key !== ownerKey) return;
      const record = state.selected?.record;
      if (!record || !target || target.id !== record.id || target.revision !== record.revision) return;
      return operation(async rpc => ({ preview: await rpc('delete_preview', { record_id: record.id }),
        action: { kind: 'delete', payload: null, ownerKey: identity.key, projectKey: state.projectKey } }));
    },
    confirm(expectedAction = state.action) {
      sync(); const action = state.action, record = state.selected?.record, preview = state.preview;
      if (!action || action !== expectedAction || action.ownerKey !== identity.key) return;
      if (lane === 'project' && ['create', 'approve', 'correct', 'delete', 'restore'].includes(action.kind) && action.projectKey !== state.projectKey) return;
      if (action.kind.startsWith('folder_') && (lane!=='private' || !state.folderStatus || state.folderStatus.revision!==action.target.revision || state.folderStatus.context_key!==action.target.context_key)) { publish({action:null}); return; }
      if (action.kind === 'proposal_accept' && (lane !== 'private' || !state.selectedJob || state.selectedJob.job_id !== action.target.job_id || state.selectedJob.revision !== action.target.revision || state.selectedJob.accepted_indexes.includes(action.target.index))) { publish({ action: null }); return; }
      if (['source_withdraw', 'excerpt'].includes(action.kind)) {
        const source = state.selectedSource?.source;
        if (!source || source.source_id !== action.target?.source_id || source.revision !== action.target?.revision) { publish({ action: null, preview: null }); return; }
      }
      if (['approve', 'correct'].includes(action.kind) && (!record || record.id !== action.target?.id || record.revision !== action.target?.revision)) { publish({ action: null }); return; }
      return operation(async rpc => {
        const routes = {
          folder_create: ['chat_folders.create', {label:action.payload,expected_revision:action.target?.revision,expected_context:action.target?.context_key,confirm:true}],
          folder_file: ['chat_folders.file', {folder_id:action.payload,expected_revision:action.target?.revision,expected_context:action.target?.context_key,confirm:true}],
          folder_rename: ['chat_folders.rename', {folder_id:action.payload?.folder_id,label:action.payload?.label,expected_revision:action.target?.revision,expected_context:action.target?.context_key,confirm:true}],
          folder_remove: ['chat_folders.remove', {folder_id:action.payload,expected_revision:action.target?.revision,expected_context:action.target?.context_key,confirm:true}],
          folder_undo: ['chat_folders.undo', {expected_revision:action.target?.revision,expected_context:action.target?.context_key,confirm:true}],
          import_copy: ['import.apply', { preview_token: preview?.preview_token, confirm: true }],
          proposal_accept: ['curation.jobs.accept', { job_id: action.target?.job_id, proposal_index: action.target?.index, expected_revision: action.target?.revision, confirm: true }],
          capture_settings: ['capture_settings.apply', { preview_token: preview?.preview_token, confirm: true }],
          recall_settings: ['recall_settings.apply', { preview_token: preview?.preview_token, confirm: true }],
          setup: ['setup', { confirm: true }],
          create: ['create', action.payload],
          source_capture: ['source.apply', { preview_token: preview?.preview_token, confirm: true }],
          excerpt: ['excerpt.apply', { preview_token: preview?.preview_token, confirm: true }],
          source_withdraw: ['source.withdraw', { source_id: action.target?.source_id, expected_revision: action.target?.revision, confirm: true }],
          consent: ['consent.apply', { preview_token: preview?.preview_token, confirm: true }],
          binding: ['workspace.project.apply', { preview_token: preview?.preview_token, confirm: true }],
          approve: ['approve', { record_id: record?.id, expected_revision: record?.revision, confirm: true }],
          correct: ['correct', { record_id: record?.id, expected_revision: record?.revision, changes: action.payload, confirm: true }],
          delete: ['delete', { record_id: preview?.record_id, expected_revision: preview?.expected_revision,
            preview_token: preview?.preview_token, confirm: true }],
          restore: ['restore', { recovery_id: action.payload, confirm: true }],
        };
        const configured = routes[action.kind];
        const route = configured && [configured[0], { ...configured[1] }]; if (!route) throw new Error('unsupported action');
        if (lane === 'project' && ['create', 'approve', 'correct', 'delete', 'restore'].includes(action.kind)) {
          route[1].expected_consent_revision = action.kind === 'delete' ? preview?.consent_revision : action.consentRevision;
          if (!Number.isSafeInteger(route[1].expected_consent_revision)) throw new Error('Missing staged consent revision');
        }
        const result = await rpc(...route);
        if (action.kind.startsWith('folder_')) return {folderStatus:result,notice:'Chat-folder metadata updated. Working directory, native projects and memory permissions are unchanged.'};
        if (action.kind === 'import_copy') return { selectedImport: result.receipt, importReceipts: [], importNext: null, notice: result.already_imported ? 'This exact canonical batch was already copied. Receipt shown; no duplicate records created.' : 'Selected records copied as pending and sensitive. Originals unchanged. Receipt shown; separate record approval remains required.' };
        if (action.kind === 'proposal_accept') return { acceptedProposal: { record_id: result.record.id, state: result.record.state, sensitive: result.record.sensitive }, selectedJob: null, curationJobs: [], curationJobsNext: null, notice: 'Proposal saved as pending, not approved. Refresh jobs and private records to reconcile. Sensitivity is preserved.' };
        if (action.kind === 'capture_settings') return { captureSettings: result, notice: 'Local capture settings updated. No model egress, extraction or approval was enabled.' };
        if (action.kind === 'recall_settings') return { recallSettings: result, notice: 'Recall settings updated. This does not approve records or select the native ELM memory provider.' };
        if (action.kind === 'source_capture') return { lastSource: result, selectedSource: null, sources: [], sourceNext: null,
          notice: 'Source snapshot saved. Refresh source snapshots to reconcile and reveal it. No record was extracted or approved.' };
        if (action.kind === 'source_withdraw') return { selectedSource: null, sources: [], sourceNext: null, selected: null, records: [], next: null,
          notice: 'Source withdrawal completed. Snapshot bytes remain retained. Refresh records and sources to inspect their state.' };
        // Do not replay a mutation if a subsequent read fails. Human refresh reconciles.
        return { selected: null, selectedSource: null, sources: [], sourceNext: null, records: [], trash: [], ready: false, initialized: null,
          next: null, trashNext: null, projectStatus: null, projectKey: null, binding: null, notice: 'Action completed. Refresh to inspect the current records and trash.' };
      }, true, !['consent', 'binding'].includes(action.kind));
    },
  };
  return api;
}

const Button = SDK.Button || 'button', Input = SDK.Input || 'input', Textarea = SDK.Textarea || 'textarea';
const sectionStyle = { paddingBlock: '1rem', borderTop: '1px solid var(--ui-stroke-secondary)' };
const rowStyle = { display: 'flex', flexWrap: 'wrap', gap: '.75rem', alignItems: 'center' };
const proseStyle = { whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' };
const button = (label, onClick, disabled = false) => h(Button, { type: 'button', variant: 'outline', disabled, onClick }, label);
const evidenceKinds = {
  reference: ['source_document'], explicit_fact: ['explicit_statement', 'source_document'],
  preference: ['explicit_statement'], observation: ['direct_observation'], interpretation: ['inference'],
  summary: ['source_document', 'inference'], procedure: ['source_document', 'inference'],
};
function SelectedImportForm({ controller, state: s }) {
  const [text, setText] = useState(''), [declared, setDeclared] = useState(false);
  const valid = declared && text && new TextEncoder().encode(text).length <= 65536;
  return h('section', null,
    h('label', null, 'Paste selected-record export JSON (maximum 64 KiB)', h(Textarea, { value: text, rows: 8, disabled: s.busy, onChange: e => setText(e.target.value) })),
    h('p', null, 'Required format: elm-selected-records-v1 with 1–8 records; each has id, title, text and sources. Unsupported dependencies, record links and private snapshot references are rejected, not silently discarded.'),
    h('label', null, h('input', { type: 'checkbox', checked: declared, disabled: s.busy, onChange: e => setDeclared(e.target.checked) }), 'I declare that I have the right to copy every supplied record. This declaration does not verify ownership or authorship.'),
    button('Review exact selected-record copy', () => controller.previewImport(text, declared, s.ownerKey), s.busy || s.uncertain || !valid));
}
function SelectedImportPanel({ controller, state: s }) {
  return h('section', { style: sectionStyle }, h('h2', null, 'Reviewed copy from a supplied export'),
    h('p', null, 'No legacy folders or global memory are browsed. Paste only the records you intend to copy. This is a declared copy, not verified ownership or automatic migration. Original data is not read, changed, overwritten or deleted.'),
    h('p', null, 'New records are private to this authenticated chat, pending and sensitive. Old approval, scope and classification remain unverified metadata, not new authority. No project adoption or model call is performed. Only the exact ordered canonical batch is deduplicated; edited, subset or reordered exports can create duplicate copies.'),
    h(SelectedImportForm, { key: s.ownerKey, controller, state: s }),
    button('Refresh copy receipts', () => controller.refreshImports(null, s.ownerKey), s.busy),
    h('ul', null, ...(s.importReceipts || []).map(receipt => h('li', { key: receipt.batch_id }, `${receipt.batch_id} · ${receipt.created_at} · ${receipt.record_ids.length} copied record(s) `,
      button('Reveal copy receipt', () => controller.inspectImport(receipt.batch_id, s.ownerKey), s.busy)))),
    s.importNext && button('Load more copy receipts', () => controller.refreshImports(s.importNext, s.ownerKey), s.busy),
    s.selectedImport && h('section', null, h('h3', null, 'Copy receipt and original-to-new mapping'),
      h('p', null, 'Original claims and new record IDs correspond by array index. A receipt records the copy, not current approval. After a lost response, inspect receipts rather than repeating the action.'),
      h('pre', { style: proseStyle }, JSON.stringify(s.selectedImport, null, 2))));
}
export function historicalJobReceipt(job) {
  const recipient = job?.recipient;
  if (!recipient || typeof recipient !== 'object') return null;
  const text = (value, limit) => typeof value === 'string' && value.length <= limit ? value : null;
  return { provider: text(recipient.provider, 64), endpoint: text(recipient.endpoint, 2048), model: text(job.model, 128),
    credential_mode: text(recipient.credential_mode, 64), credential_slot: text(recipient.credential_slot, 64),
    credential_version: Number.isSafeInteger(recipient.credential_version) && recipient.credential_version > 0 ? recipient.credential_version : null,
    payload_sha256: typeof job.payload_sha256 === 'string' && /^[a-f0-9]{64}$/.test(job.payload_sha256) ? job.payload_sha256 : null };
}
function JobReceipt({ job }) {
  const receipt = historicalJobReceipt(job);
  return receipt && h('section', null, h('h4', null, 'Historical recipient receipt, not active configuration'),
    h('p', null, 'Synthetic/local qualification only in this checkpoint. A receipt records the attempted destination; it does not prove delivery, actual provider model execution or an active production route. Slot/version are identifiers, never the credential itself.'),
    h('pre', { style: proseStyle }, JSON.stringify(receipt, null, 2)));
}
function CurationJobsPanel({ controller, state: s }) {
  const job = s.selectedJob;
  return h('section', { style: sectionStyle }, h('h2', null, 'Review retained extraction results'),
    h('p', null, 'Production extraction remains unavailable. This checkpoint is qualified only with synthetic loopback tests; live dispatch is gated pending provider compatibility checks. A job marked attempted does not prove that a request was sent or an answer received.'),
    h('p', null, 'Results and source-bound proposals are retained locally as plaintext; there is no result purge here. Inspection may reveal sensitive text. Accepting one proposal creates a pending record, never final approval or permission to send data.'),
    button('Refresh retained jobs', () => controller.refreshJobs(null, s.ownerKey), s.busy),
    !(s.curationJobs || []).length && h('p', null, 'No jobs loaded. Refresh to inspect available results; no example jobs are created.'),
    h('ul', null, ...(s.curationJobs || []).map(item => h('li', { key: item.job_id }, `${item.job_id} · ${item.state} · revision ${item.revision} · ${item.proposal_count} proposal(s) `,
      button('Reveal job proposals', () => controller.inspectJob(item.job_id, s.ownerKey), s.busy)))),
    s.curationJobsNext && button('Load more retained jobs', () => controller.refreshJobs(s.curationJobsNext, s.ownerKey), s.busy),
    s.acceptedProposal && h('p', { role: 'status' }, `Last accepted proposal: ${s.acceptedProposal.record_id} · ${s.acceptedProposal.state} · ${s.acceptedProposal.sensitive ? 'sensitive' : 'nonsensitive'}. Not approved.`),
    job && h('section', null, h('h3', null, `Job ${job.job_id} · revision ${job.revision} · ${job.state}`), h(JobReceipt, { job }),
      h('p', null, 'Untrusted model proposals: exact source references do not prove the proposed title or interpretation true. Source withdrawal or revision changes can block acceptance.'),
      ...(job.proposals || []).map((proposal, index) => h('section', { key: index, style: sectionStyle }, h('h4', null, `Proposal ${index + 1}: ${proposal.title}`),
        h('pre', { style: proseStyle }, JSON.stringify(proposal, null, 2)),
        job.accepted_indexes.includes(index) ? h('p', null, 'Already accepted; inspect the record separately. Recorded ID: ', job.accepted_records?.[String(index)] || 'Refresh this job to reconcile the record ID.') : button('Review saving this proposal as pending', () => controller.stageProposal(index, s.ownerKey, job), s.busy || s.uncertain || job.state !== 'ready')))));
}
export function CurationPreviewForm({ controller, state: s }) {
  const [ids, setIds] = useState('');
  const [tokens,setTokens]=useState('512');
  const requested=Number(tokens), validTokens=/^[0-9]+$/.test(tokens)&&Number.isInteger(requested)&&requested>=1&&requested<=512;
  const edit=(update)=>{if(controller.currentKey()!==s.ownerKey||controller.getSnapshot()!==s||s.busy)return;if(s.organizerPreview)controller.cancelOrganizer(s.ownerKey,s.organizerPreview);update()};
  const chosen = ids.split('\n').map(value => value.trim()).filter(Boolean);
  const valid = chosen.length >= 1 && chosen.length <= 4 && new Set(chosen).size === chosen.length;
  return h('div', null,
    h('label', null, 'Exact private source IDs, one per line (1–4)', h(Textarea, { value: ids, rows: 4, disabled: s.busy, onChange: e => edit(()=>setIds(e.target.value)) })),
    h('p', null, 'Explicitly revealing a payload can display complete sensitive source text here. Only active sources in this authenticated chat are eligible. This is local inspection, not consent to send.'),
    button('Reveal exact local payload preview', () => controller.previewCuration(chosen, s.ownerKey, s.curationStatus), s.busy || !valid),
    h('label',null,'Requested maximum output tokens (1–512)',h(Input,{type:'number',min:1,max:512,step:1,value:tokens,disabled:s.busy,onChange:e=>edit(()=>setTokens(e.target.value))})),
    h('p',null,'This is a request to the provider, not a measured token count, provider-compliance guarantee or billing limit. Editing sources or this request discards the prepared preview.'),
    button('Prepare exact organizer payload (not sent)',()=>controller.prepareOrganizer(chosen,s.ownerKey,requested),s.busy||!valid||!validTokens));
}
function OrganizerPreview({controller,state:s}) {
  const p=s.organizerPreview;
  const [accepted,setAccepted]=useState(false);
  return h('section',{style:sectionStyle},h('h3',null,'Prepared organizer payload · NOT SENT'),
    h('p',null,p.production_dispatch_supported?'Sending transmits the complete payload below to the exact recipient. Price is unknown; limits are NOT a monetary spending cap. Provider API compatibility has not been certified.':'This host cannot send organizer requests. Nothing was sent.'),
    h('p',null,'This preview expires after 300 seconds. The reserved job ID is not a completed job or proof of a request: ',p.job_id),
    h('p',null,'Requested maximum output tokens: ',String(p.max_output_tokens),'. Provider compliance and billed usage are not guaranteed. Input token count and price are unknown.'),
    h('p',null,'Local transport limits: outbound body ',String(p.budget.outbound_body_bytes),' / 32768 bytes; response body at most 8192 bytes. Bytes are not tokens. Socket timeout: 10 seconds, NOT an absolute end-to-end deadline. No monetary limit is enforced.'),
    h('h4',null,'Exact recipient and nonsecret credential binding'),h('pre',{style:proseStyle},JSON.stringify(p.recipient,null,2)),
    h('h4',null,'Selected source pins and sensitivity'),h('pre',{style:proseStyle},JSON.stringify(p.source_pins,null,2)),
    h('p',null,'Payload SHA-256: ',p.payload_sha256),
    h('h4',null,'Full prepared payload including model (untrusted text)'),h('pre',{style:proseStyle},JSON.stringify(p.egress_payload,null,2)),
    h('label',null,h('input',{type:'checkbox',checked:accepted,disabled:s.busy||!p.production_dispatch_supported,onChange:e=>setAccepted(e.target.checked)}),' I approve sending this complete payload, including any sensitive source data, to the displayed recipient and accept unknown provider charges without an enforced monetary cap.'),
    button('Send reviewed payload once',()=>controller.executeOrganizer(accepted,s.ownerKey,p),s.busy||s.uncertain||!accepted||!p.production_dispatch_supported),
    button('Cancel prepared organizer preview',()=>controller.cancelOrganizer(s.ownerKey,p),s.busy));
}
function CurationPanel({ controller, state: s }) {
  return h('section', { style: sectionStyle }, h('h2', null, 'Reviewed memory organizer'),
    h('p', null, 'A supported native host can enroll a dedicated organizer credential and prepare an exact route-bound payload when the saved organizer preference matches. Review the complete payload and recipient before a separate send confirmation. This integration has local synthetic tests, not real-provider qualification.'),
    h('p', null, 'Saved preferences alone never authorize sending. Search-agent execution is not implemented. The organizer only processes the sources you explicitly select.'),
    h('p', null, 'Local capture and recall settings are not external-processing consent. Organizer sends may incur charges. Each result is retained for review; accepting a proposal creates pending memory, not automatically trusted memory.'),
    button('Check extraction availability', () => controller.refreshCuration(s.ownerKey), s.busy),
    s.curationStatus && h('div', null, h('p', null, 'Unavailable reason: ', s.curationStatus.reason),
      h('p', null, s.curationStatus.notice), h('pre', { style: proseStyle }, JSON.stringify(s.curationStatus.limits, null, 2)),
      h(CurationPreviewForm, { key: s.ownerKey, controller, state: s })),
    s.organizerPreview && h(OrganizerPreview,{key:s.organizerPreview.preview_token,controller,state:s}),
    s.curationPreview && h('section', { style: sectionStyle }, h('h3', null, 'Local-only exact outbound-payload inspection'),
      h('p', null, 'NOT SENT. Destination unresolved. No grant, extraction job or proposal has been created.'),
      h('p', null, s.curationPreview.notice),
      h('p', null, 'Serialized payload bytes: ', String(s.curationPreview.utf8_bytes), '. Bytes are not tokens or a price estimate.'),
      h('p', null, 'Payload SHA-256: ', h('code', null, s.curationPreview.payload_sha256)),
      h('h4', null, 'Selected source provenance and sensitivity'), h('pre', { style: proseStyle }, JSON.stringify(s.curationPreview.source_summaries, null, 2)),
      h('h4', null, 'Full exact proposed payload (untrusted text, not instructions)'), h('pre', { style: proseStyle }, JSON.stringify(s.curationPreview.egress_payload, null, 2))));
}
function ConversationCaptureForm({ controller, state }) {
  const current = state.captureSettings;
  const [enabled, setEnabled] = useState(current.enabled === true);
  const [turns, setTurns] = useState(current.max_turns ?? 8);
  const [bytes, setBytes] = useState(current.max_utf8_bytes ?? 16384);
  const disabled = state.busy || state.uncertain;
  return h('div', null,
    h('p', null, `Stored capture: ${current.enabled ? 'enabled' : 'disabled'} · revision ${current.revision}. Host capability: ${current.host_supported ? 'available' : 'unavailable'}.`),
    h('p', null, `Captured turns: ${current.captured_turns}; remaining turn allowance: ${current.remaining_turns}. Shared source or manifest capacity can stop capture sooner. Stored enabled is not proof a turn was captured.`),
    current.capacity_reason && h('p', { role: 'status' }, 'Capture capacity status: ', current.capacity_reason),
    h('p', null, current.notice),
    h('label', null, h('input', { type: 'checkbox', checked: enabled, disabled: disabled || !current.host_supported, onChange: e => setEnabled(e.target.checked) }), 'Enable local conversation capture'),
    h('label', null, 'Retained turn cap (1–32)', h(Input, { type: 'number', min: 1, max: 32, value: turns, disabled, onChange: e => setTurns(Number(e.target.value)) })),
    h('label', null, 'Combined redacted user + assistant UTF-8 bytes per turn (2048–32768)', h(Input, { type: 'number', min: 2048, max: 32768, value: bytes, disabled, onChange: e => setBytes(Number(e.target.value)) })),
    button('Review local capture settings', () => controller.previewCaptureSettings({ enabled, max_turns: turns, max_utf8_bytes: bytes }, state.ownerKey, current), disabled),
    current.enabled && button('Review disabling local capture', () => controller.previewCaptureSettings({ enabled: false, max_turns: current.max_turns, max_utf8_bytes: current.max_utf8_bytes }, state.ownerKey, current), disabled));
}
function ConversationCapturePanel({ controller, state: s }) {
  return h('section', { style: sectionStyle }, h('h2', null, 'Optional local conversation capture'),
    h('p', null, 'Separate local-storage consent, off by default. This does not authorize sending captured text to a model, enable recall, extract records or approve anything. No external model or paid API call is made by capture controls.'),
    h('p', null, 'Only qualified future native turns are captured. Enabling or changing settings excludes already queued or in-flight admissions. Captured user and assistant snapshots are forced sensitive. Native text is secret-redacted, not a complete transcript or proof of delivery.'),
    h('p', null, 'The cap stops new capture; it does not expire or erase old text. Withdrawn snapshots still count and retain bytes. Disabling affects future capture, not existing snapshots, outputs, transcripts or backups. There is no rolling retention or permanent purge here.'),
    button('Refresh local capture settings', () => controller.refreshCaptureSettings(s.ownerKey), s.busy),
    s.captureSettings && h(ConversationCaptureForm, { key: s.ownerKey + ':' + s.captureSettings.revision, controller, state: s }),
    button('Refresh captured turns', () => controller.refreshCapturedTurns(null, s.ownerKey), s.busy),
    h('ul', null, ...(s.capturedTurns || []).map(turn => h('li', { key: turn.capture_id },
      h('p', null, `${turn.capture_id} · ${turn.created_at} · ${turn.phase}`),
      h('p', null, `User: ${turn.user_utf8_bytes} bytes; assistant: ${turn.assistant_utf8_bytes} bytes. Finalized before delivery is not a delivery receipt.`),
      button('Reveal captured user source', () => controller.inspectSource(turn.user_source_id, s.ownerKey), s.busy || !s.initialized),
      button('Reveal captured assistant source', () => controller.inspectSource(turn.assistant_source_id, s.ownerKey), s.busy || !s.initialized)))),
    s.captureNext && button('Load more captured turns', () => controller.refreshCapturedTurns(s.captureNext, s.ownerKey), s.busy),
    h('p', null, 'First refresh the private review at the top to verify the initialized store. Revealed text then appears in Private source snapshots above, with native role/admission metadata. Exact excerpts require separate review and remain pending and sensitive; withdrawal is not erasure.'));
}
function RecallSettingsForm({ controller, state }) {
  const current = state.recallSettings;
  const [enabled, setEnabled] = useState(current.enabled === true);
  const [records, setRecords] = useState(current.max_records ?? 4);
  const [bytes, setBytes] = useState(current.max_utf8_bytes ?? 8192);
  const disabled = state.busy || state.uncertain;
  return h('div', null,
    h('p', null, `Saved setting: ${current.enabled ? 'enabled' : 'disabled'} · revision ${current.revision}. Host capability: ${current.host_supported ? 'available' : 'unavailable'}. Stored settings do not prove active injection.`),
    h('p', null, current.notice),
    h('label', null, h('input', { type: 'checkbox', checked: enabled, disabled: disabled || !current.host_supported, onChange: e => setEnabled(e.target.checked) }), 'Enable private-chat automatic recall'),
    h('label', null, 'Maximum records (1–8)', h(Input, { type: 'number', min: 1, max: 8, value: records, disabled, onChange: e => setRecords(Number(e.target.value)) })),
    h('label', null, 'Maximum UTF-8 bytes (512–16384)', h(Input, { type: 'number', min: 512, max: 16384, value: bytes, disabled, onChange: e => setBytes(Number(e.target.value)) })),
    button('Review recall settings', () => controller.previewRecall({ enabled, max_records: records, max_utf8_bytes: bytes }, state.ownerKey, current), disabled),
    current.enabled && button('Review disabling recall', () => controller.previewRecall({ enabled: false, max_records: current.max_records, max_utf8_bytes: current.max_utf8_bytes }, state.ownerKey, current), disabled));
}
function RecallSettingsPanel({ controller, state }) {
  return h('section', { style: sectionStyle }, h('h2', null, 'Optional private-chat automatic recall'),
    h('p', null, 'Off by default. Requires explicit private setup, an approving human, a supported host, and separate native ELM provider selection. Project automatic recall is not supported.'),
    h('p', null, 'Requires the patched host, ELM selected as native provider, the supported primary ChatCompletions api_mode, a known context window and an explicit positive max_tokens output cap. With the default unset max_tokens, recall is safely omitted even when saved as enabled. These controls do not change provider or output settings.'),
    h('p', null, 'Uses the newest approved, nonsensitive private records, not semantic search. No retrieval model or API calls are made, but memory added to an existing paid chat can increase input costs. UTF-8 bytes are not tokens.'),
    h('p', null, 'Disabling blocks future request builds, not requests already dispatched, provider retries, prior output, transcripts or logs. An archived or deleted selected project may require explicit unbinding before these settings can be read or changed.'),
    button('Refresh recall settings', () => controller.refreshRecall(state.ownerKey), state.busy),
    state.recallSettings && h(RecallSettingsForm, { key: state.ownerKey + ':' + state.recallSettings.revision, controller, state }));
}
function CreateRecordForm({ controller, disabled, ownerKey, project, projectKey: renderedProjectKey }) {
  const [title, setTitle] = useState(''), [text, setText] = useState('');
  const [reference, setReference] = useState(''), [quote, setQuote] = useState('');
  const [domain, setDomain] = useState('work'), [kind, setKind] = useState('reference');
  const [basis, setBasis] = useState('source_document'), [topic, setTopic] = useState('facts');
  const [sensitive, setSensitive] = useState(false);
  const sourceAllowed = manualSourceAllowed(reference, project);
  const valid = sourceAllowed && title.trim() && text.trim() && reference.trim() && topic.trim() &&
    new TextEncoder().encode(title).length <= 512 && new TextEncoder().encode(text).length <= 8192 &&
    !(domain === 'user' && sensitive && basis !== 'explicit_statement');
  const field = (label, value, change, maxLength) => h('label', null, label, h(Input, { value, maxLength, disabled, onChange: e => change(e.target.value) }));
  const select = (label, value, options, change) => h('label', null, label, h('select', { value, disabled, onChange: e => change(e.target.value) },
    ...options.map(option => h('option', { key: option, value: option }, option))));
  function review() {
    const source = { ref: reference }; if (quote) source.quote = quote;
    controller.stage('create', { title, text, sources: [source], domain, kind, basis, topic, sensitive }, ownerKey, null, renderedProjectKey);
  }
  return h('details', { style: sectionStyle }, h('summary', null, 'Add a pending record manually'),
    h('p', null, project ? 'This record goes into the currently consented project pool, not your private chat. It may later be reviewed by independently consenting chats of this principal.' : 'This record stays in this authenticated private chat. No project sharing is enabled.'),
    field('Title', title, setTitle, 512), h('label', null, 'Record text', h(Textarea, { value: text, rows: 5, maxLength: 8192, disabled, onChange: e => setText(e.target.value) })),
    field('Declared source reference (not fetched)', reference, setReference, 2048),
    !sourceAllowed && h('p', { role: 'alert' }, 'Private elm-snapshot-v1 references are not project source authority. This form does not copy private snapshots into projects.'),
    h('label', null, 'Optional declared source quote', h(Textarea, { value: quote, rows: 3, maxLength: 4000, disabled, onChange: e => setQuote(e.target.value) })),
    h('div', { style: rowStyle }, select('Domain', domain, ['user', 'work', 'reference'], setDomain),
      select('Evidence kind', kind, Object.keys(evidenceKinds), value => { setKind(value); setBasis(evidenceKinds[value][0]); }),
      select('Evidence basis', basis, evidenceKinds[kind], setBasis)),
    field('Topic', topic, setTopic, 128), h('label', null, h('input', { type: 'checkbox', checked: sensitive, disabled, onChange: e => setSensitive(e.target.checked) }), ' Sensitive: exclude from model recall'),
    h('p', null, 'A manually entered reference or quote is not verified. No URL is fetched. Sensitive user facts require explicit-statement evidence. Storage byte limits are checked again by the backend.'),
    button('Review new pending record', review, disabled || !valid));
}
function SourceCaptureForm({ controller, ownerKey, disabled }) {
  const [title, setTitle] = useState(''), [text, setText] = useState(''), [reference, setReference] = useState(''), [author, setAuthor] = useState('');
  const [sensitive, setSensitive] = useState(true);
  const bytes = value => new TextEncoder().encode(value).length;
  const valid = title.trim() && text.length > 0 && bytes(title) <= 512 && bytes(text) <= 65536 && bytes(reference) <= 2048 && bytes(author) <= 512;
  const field = (label, value, change, maxLength) => h('label', null, label, h(Input, { value, maxLength, disabled, onChange: e => change(e.target.value) }));
  return h('details', null, h('summary', null, 'Capture pasted source text'),
    h('p', null, 'Private chat only. Store an exact snapshot of text you supply; no URL or file is fetched and no AI extraction runs.'),
    field('Snapshot title', title, setTitle, 512),
    h('label', null, 'Exact source text (up to 64 KiB UTF-8)', h(Textarea, { value: text, rows: 8, maxLength: 65536, disabled, onChange: e => setText(e.target.value) })),
    field('Optional declared reference (not fetched)', reference, setReference, 2048), field('Optional declared author (not verified)', author, setAuthor, 512),
    h('label', null, h('input', { type: 'checkbox', checked: sensitive, disabled, onChange: e => setSensitive(e.target.checked) }), ' Sensitive source — inherited by extracted records'),
    h('p', null, 'Sensitive is on by default. This is your declaration, not an automated privacy detector. Exact excerpts inherit the flag; record approval does not remove recall exclusions.'),
    button('Preview source snapshot', () => controller.previewSource({ title, text, reference, author, sensitive }, ownerKey), disabled || !valid));
}
function ExcerptForm({ source, controller, ownerKey, disabled }) {
  const [quote, setQuote] = useState(''), [occurrence, setOccurrence] = useState(''), [title, setTitle] = useState('');
  const number = Number(occurrence), validOccurrence = occurrence === '' || Number.isSafeInteger(number) && number >= 1;
  const valid = quote.length > 0 && new TextEncoder().encode(quote).length <= 8192 && new TextEncoder().encode(title).length <= 512 && validOccurrence;
  function preview() {
    const payload = { quote }; if (title) payload.title = title; if (occurrence !== '') payload.occurrence = number;
    controller.previewExcerpt(payload, ownerKey, source);
  }
  return h('section', { style: sectionStyle }, h('h3', null, 'Review an exact excerpt'),
    h('label', null, 'Exact quote (not trimmed or normalized)', h(Textarea, { value: quote, rows: 4, maxLength: 8192, disabled, onChange: e => setQuote(e.target.value) })),
    h('label', null, 'Occurrence, starting at 1 (blank requires a unique match)', h(Input, { value: occurrence, type: 'number', min: 1, step: 1, disabled, onChange: e => setOccurrence(e.target.value) })),
    h('label', null, 'Optional record title', h(Input, { value: title, maxLength: 512, disabled, onChange: e => setTitle(e.target.value) })),
    h('p', null, 'The backend finds the exact quote and reports Unicode code-point offsets. The browser never calculates or submits character offsets. Ambiguous matches require an explicit occurrence.'),
    button('Preview exact excerpt', preview, disabled || !valid));
}
function SourcePanel({ state: s, controller, disabled }) {
  const source = s.selectedSource?.source;
  return h('section', { style: sectionStyle, 'aria-label': 'Private source snapshots' }, h('h2', null, 'Private source snapshots'),
    h('p', null, 'Captured-text identity is not factual truth, verified authorship, or project sharing. Withdrawal retains snapshot bytes; no permanent source purge is provided.'),
    s.lastSource && h('p', { role: 'status' }, 'Last saved source: ', h('code', null, s.lastSource.source_id)),
    button('Refresh source snapshots', () => controller.refreshSources(null, s.ownerKey), s.busy),
    h('ul', null, ...(s.sources || []).map(item => h('li', { key: item.source_id }, `${item.title} · ${item.state} · revision ${item.revision} · ${item.sensitive ? 'sensitive' : 'declared non-sensitive'} `,
      button('Reveal source snapshot', () => controller.inspectSource(item.source_id, s.ownerKey), s.busy)))),
    s.sourceNext && button('Load more source snapshots', () => controller.refreshSources(s.sourceNext, s.ownerKey), s.busy),
    h(SourceCaptureForm, { key: s.ownerKey, controller, ownerKey: s.ownerKey, disabled }),
    source && h('section', { key: source.source_id + ':' + source.revision, style: sectionStyle },
      h('h3', null, source.title), h('p', null, `${source.state} · revision ${source.revision} · ${source.sensitive ? 'sensitive' : 'declared non-sensitive'}`),
      source.native_capture && h('div', null, h('h4', null, 'Native capture receipt (not verified delivery)'), h('pre', { style: proseStyle }, JSON.stringify(source.native_capture, null, 2))),
      h('p', null, 'SHA-256: ', h('code', null, source.sha256)), h('pre', { style: proseStyle }, source.text),
      h('details', null, h('summary', null, 'Complete captured source metadata'), h('pre', { style: proseStyle }, JSON.stringify(source, null, 2))),
      source.state === 'active' && h(ExcerptForm, { source, controller, ownerKey: s.ownerKey, disabled }),
      source.state === 'active' && button('Review source withdrawal', () => controller.stage('source_withdraw', null, s.ownerKey, source), disabled)));
}
function RecordEditor({ record, controller, disabled, ownerKey, projectKey: renderedProjectKey }) {
  const [title, setTitle] = useState(record.title), [text, setText] = useState(record.text);
  return h('section', { style: sectionStyle }, h('h3', null, 'Propose a correction'),
    h('label', null, 'Title', h(Input, { value: title, maxLength: 512, disabled, onChange: e => setTitle(e.target.value) })),
    h('label', null, 'Text', h(Textarea, { value: text, rows: 6, maxLength: 8192, disabled, onChange: e => setText(e.target.value) })),
    h('p', null, 'Correction replaces the current text, returns this record to pending, and invalidates dependent evidence. No version history is retained.'),
    button('Review correction', () => controller.stage('correct', { title, text }, ownerKey, record, renderedProjectKey), disabled || !title.trim() || !text.trim()));
}
function RecordDetail({ detail, controller, disabled, ownerKey, projectKey: renderedProjectKey }) {
  const r = detail.record;
  return h('section', { style: sectionStyle, 'aria-label': 'Selected memory record' },
    h('h2', null, r.title), h('p', null, `${r.state} · revision ${r.revision} · ${r.domain} / ${r.kind}`),
    r.sensitive && h('p', null, 'Sensitive record: visible for your review, excluded from model recall.'),
    h('p', null, detail.recall_eligible ? 'Eligible for explicit recall in this reviewed scope.' : 'Not eligible for model recall.'),
    h('p', { style: proseStyle }, r.text), h('h3', null, 'Declared sources'),
    h('ul', null, ...r.sources.map((source, index) => h('li', { key: index, style: proseStyle },
      h('code', null, source.ref), source.quote && h('blockquote', null, source.quote),
      source.sha256 && h('p', null, 'SHA-256: ', h('code', null, source.sha256)),
      source.revision != null && h('p', null, 'Source revision: ' + source.revision)))),
    h('details', null, h('summary', null, 'Full record and provenance metadata'),
      h('pre', { style: proseStyle }, JSON.stringify(r, null, 2))),
    h('p', null, 'Sources are displayed as text. They are not executed or opened automatically.'),
    h('div', { style: rowStyle }, r.state === 'pending' && button('Review approval', () => controller.stage('approve', null, ownerKey, r, renderedProjectKey), disabled),
      button('Preview deletion', () => controller.previewDelete(ownerKey, r), disabled)),
    h(RecordEditor, { key: r.id + ':' + r.revision, record: r, controller, disabled, ownerKey, projectKey: renderedProjectKey }));
}
function Confirmation({ state, controller }) {
  const kind = state.action.kind, detail = state.selected?.record;
  const descriptions = {
    folder_create: 'Create this metadata-only chat folder? Creating a folder does not file the current chat.',
    folder_file: 'Change only the current chat’s folder membership? Working directory, native project and memory permissions stay unchanged.',
    folder_rename: 'Rename this metadata-only chat folder for your chats? Membership, working directories and memory permissions remain unchanged. This clears the prior filing undo.',
    folder_remove: 'Remove this empty folder label? No chats or messages are deleted. Any saved membership, including one not currently visible, blocks removal. The same label can be created again; prior filing undo is cleared.',
    folder_undo: 'Undo the latest filing change only if its reviewed revision still matches? Intervening changes refuse; no previous state is forced.',
    import_copy: 'Copy this exact reviewed batch into the current private chat as new pending, sensitive records? Original claims are unverified. No originals are changed or overwritten; this does not approve records.',
    proposal_accept: 'Save this exact source-bound proposal as a pending private record? It remains unapproved and preserves source sensitivity. This is not external-processing consent.',
    capture_settings: 'Change local-storage consent for this private chat? Review the capture caps. No model egress, recall or automatic approval is authorized.',
    recall_settings: 'Change automatic recall for this private chat? Review the server settings and limits. No record is approved and no native provider is selected by this action.',
    source_capture: 'Retain this exact pasted source snapshot in the current private chat? Bytes are stored locally; no URL is fetched, no record is extracted, and nothing is approved.',
    excerpt: 'Create the exact reviewed excerpt as a pending private record? The hash and quote establish captured-text identity, not truth or authorship. No approval or project sharing is performed.',
    source_withdraw: 'Withdraw this snapshot from future extraction and invalidate linked evidence? Source bytes remain retained; this is not erasure.',
    create: 'Save this manually authored record as pending? It will not be approved or recalled automatically. Source labels are declared provenance, not independently verified evidence.',
    setup: 'Create a fresh private store for this authenticated principal. No legacy data will be adopted.',
    approve: `Approve revision ${detail?.revision} of “${detail?.title}”? Sensitive and inferred-user exclusions still apply.`,
    correct: 'Save this correction as pending? The previous text is replaced; dependent evidence is invalidated.',
    delete: 'Remove these records from recall? Full bodies remain in private trash indefinitely. This is NOT permanent erasure.',
    restore: 'Restore this retained group as pending? No approvals are restored. Dependencies may need later repair.',
    consent: 'Change this chat’s project memory permissions? Review the exact project and permissions below.',
    binding: 'Change this chat’s explicit ELM project binding? This does not grant project memory access.',
  };
  return h('section', { style: sectionStyle, 'aria-label': 'Confirm memory change' }, h('h2', null, 'Review before changing memory'),
    h('p', null, descriptions[kind]),
    ['recall_settings', 'capture_settings'].includes(kind) && h('div', null, h('pre', { style: proseStyle }, JSON.stringify(state.preview?.settings, null, 2)), h('p', null, state.preview?.notice)),
    kind.startsWith('folder_') && h('div', null,h('p',null,`Current chat: ${state.action.target.current_session_id}; reviewed revision ${state.action.target.revision}`),h('p',null,`Selection: ${state.action.label ?? 'Latest reversible filing'}`)),
    kind === 'import_copy' && h('div', null, h('h3', null, 'Exact supplied export'), h('pre', { style: proseStyle }, state.action.payload.export_text), h('h3', null, 'Destination, source hashes, original claims and full normalized candidates'), h('pre', { style: proseStyle }, JSON.stringify({ destination: state.preview?.destination, batch_id: state.preview?.batch_id, export_sha256: state.preview?.export_sha256, canonical_sha256: state.preview?.canonical_sha256, original_claims: state.preview?.original_claims, candidates: state.preview?.candidates, already_imported: state.preview?.already_imported, existing_receipt: state.preview?.existing_receipt }, null, 2)), h('p', null, state.preview?.notice)),
    kind === 'proposal_accept' && h('div', null, h('p', null, `Job ${state.action.target.job_id}, revision ${state.action.target.revision}, proposal ${state.action.target.index + 1}`), h('pre', { style: proseStyle }, JSON.stringify(state.action.payload, null, 2))),
    kind === 'create' && h('pre', { style: proseStyle }, JSON.stringify(state.action.payload, null, 2)),
    kind === 'source_capture' && h('div', null, h('h3', null, state.action.payload.title), h('pre', { style: proseStyle }, state.action.payload.text),
      h('p', null, 'Declared reference: ' + state.action.payload.reference), h('p', null, 'Declared author: ' + state.action.payload.author),
      h('p', null, 'Sensitive snapshot: ' + (state.action.payload.sensitive !== false ? 'yes' : 'declared non-sensitive'))),
    kind === 'source_withdraw' && h('div', null, h('p', null, state.action.target.title),
      h('p', null, `Source ${state.action.target.source_id}, revision ${state.action.target.revision}`), h('code', null, state.action.target.sha256)), kind === 'correct' && h('div', null, h('strong', null, state.action.payload.title), h('blockquote', { style: proseStyle }, state.action.payload.text)),
    state.preview && ['source_capture', 'excerpt'].includes(kind) && h('div', null,
      h('p', null, state.preview.notice), h('p', null, 'Captured SHA-256: ', h('code', null, state.preview.sha256)),
      kind === 'source_capture' && h('p', null, `${state.preview.utf8_bytes} UTF-8 bytes; ${state.preview.codepoints} Unicode code points`),
      kind === 'excerpt' && h('div', null, h('p', null, `Source ${state.preview.source_id}, revision ${state.preview.source_revision}; occurrence ${state.preview.occurrence}; ${state.preview.offset_unit} offsets ${state.preview.start}–${state.preview.end}`),
        h('pre', { style: proseStyle }, JSON.stringify(state.preview.candidate, null, 2)), h('blockquote', { style: proseStyle }, state.preview.quote))),
    state.preview?.affected_record_ids && h('div', null, h('p', null, `${state.preview.affected_record_ids.length} record(s) affected. ${state.preview.notice}`),
      h('details', null, h('summary', null, 'Affected record IDs'), h('pre', { style: proseStyle }, state.preview.affected_record_ids.join('\n')))),
    state.preview && ['consent', 'binding'].includes(kind) && h('div', null,
      kind === 'binding' && h('p', null, 'Current binding: ' + (state.preview.current_project_id ?? 'none')),
      h('p', null, 'Target project: ' + (state.preview.target_project_id ?? 'none')),
      h('p', null, state.preview.notice),
      state.preview.consent_revision != null && h('p', null, 'Consent revision: ' + state.preview.consent_revision),
      state.preview.initializes_store && h('p', null, 'This explicit grant creates a fresh project store. No existing private or legacy data is imported.')),
    h('div', { style: rowStyle }, button('Confirm ' + kind, () => controller.confirm(state.action), state.busy), button('Cancel', () => controller.cancel(), state.busy)));
}
function ProjectControls({ state: s, controller, disabled }) {
  const [projectId, setProjectId] = useState('');
  const status = s.projectStatus, binding = s.binding;
  return h('section', { style: sectionStyle, 'aria-label': 'Project binding and consent' },
    h('h2', null, 'Exact binding and consent'),
    h('p', null, 'Native sidebar project placement does not grant ELM access. A separate exact binding and explicit consent are required.'),
    h('p', null, 'Selected ELM project: ', h('code', null, binding?.selected_project_id ?? 'none / not checked')),
    binding && h('p', null, 'Binding revision: ' + binding.project_binding_revision),
    status && h('p', null, `Stored consent: ${status.consent_granted ? 'granted' : 'revoked'} · revision ${status.consent_revision} · policy ${status.consent_version ?? 'unavailable'}`),
    status && h('p', null, 'Effective project access: ' + (status.project_read_authorized ? 'authorized for the reported policy' : 'not authorized')),
    status?.reconsent_required && h('p', null, 'Your older consent does not allow human inspection or editing. Review the new permissions before continuing.'),
    h('div', { style: rowStyle },
      button('Preview project consent', () => controller.previewConsent('grant', s.ownerKey), disabled || !binding?.selected_project_id || !status),
      button('Preview revoke consent', () => controller.previewConsent('revoke', s.ownerKey), disabled || !status)),
    h('p', null, 'Opted-in chats of this same principal share a project pool. New consent includes inspection of pending and sensitive records and editing/deleting/restoring contributions from those chats. Revocation stops this chat’s access; it does not erase contributions.'),
    h('details', null, h('summary', null, 'Change the explicit ELM binding'),
      h('p', null, 'Use an existing exact Hermes project ID. No project is created or selected automatically. Archived/deleted bindings must be explicitly cleared before consent can be inspected or revoked.'),
      h('label', null, 'Existing project ID', h(Input, { value: projectId, maxLength: 256, disabled, onChange: e => setProjectId(e.target.value) })),
      button('Preview exact binding', () => controller.previewBinding(projectId, s.ownerKey), disabled || !projectId.trim() || projectId !== projectId.trim()),
      button('Preview unbind', () => controller.previewBinding(null, s.ownerKey), disabled || !binding?.selected_project_id),
      h('p', null, 'Unbind and revoke are separate confirmations. After unbinding, refresh and review revoke. Existing project records stay retained.')));
}
export function ReviewPage({ controller, project = false }) {
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  const activation = SDK.useGatewayActivationEpoch ? SDK.useGatewayActivationEpoch() : 0;
  useLayoutEffect(() => { controller.sync(); }, [controller, activation]);
  // Hide old content in render even before a layout-effect notification clears it.
  const s = state.ownerKey === controller.currentKey() ? state : blank('changed', 'Context changed. Refresh this chat.');
  const disabled = s.busy || s.uncertain;
  const inspectable = project ? s.projectStatus?.project_read_authorized === true && s.projectStatus?.consent_version === 2 : s.initialized;
  return h('main', { 'aria-label': project ? 'Consented project memory' : 'Current-chat private memory', style: { color: 'var(--ui-text-primary)',
    padding: '1.5rem', maxWidth: '64rem', lineHeight: 1.6, overflowWrap: 'anywhere' } },
    h('p', { style: { color: 'var(--ui-text-secondary)' } }, 'ELM / HUMAN REVIEW'),
    h('h1', null, project ? 'Consented project memory' : 'Current-chat private memory'),
    h('p', null, 'Review what this chat remembers. Project placement is organization, never permission to read another chat.'),
    h('div', { style: rowStyle }, button(s.busy ? 'Working…' : 'Refresh records and trash', () => controller.refresh(), s.busy),
      h('span', null, 'No automatic capture · No automatic approval')),
    s.error && h('p', { role: 'alert' }, s.error), s.notice && h('p', { role: 'status' }, s.notice),
    !s.ready && h('p', null, 'Refresh explicitly to inspect memory. These controls require the rebuilt authenticated host APIs.'),
    project && h(ProjectControls, { key: s.ownerKey, state: s, controller, disabled }),
    !project && s.ready && s.initialized === false && h('section', { style: sectionStyle }, h('h2', null, 'Start with a fresh private store'),
      h('p', null, 'Existing global or project memory is not imported.'), button('Review fresh setup', () => controller.stage('setup', null, s.ownerKey), disabled)),
    inspectable && h(CreateRecordForm, { key: s.ownerKey + ':' + (s.projectKey ?? 'private'), controller, disabled, ownerKey: s.ownerKey, project, projectKey: s.projectKey }),
    inspectable && h('section', { style: sectionStyle }, h('h2', null, 'Records'),
      h('nav', { 'aria-label': 'Record state', style: rowStyle }, ...states.map(filter => button(filter,
        () => controller.filter(filter), s.busy || filter === s.filter))),
      !s.records.length && h('p', null, 'No records in this view.'),
      h('ul', null, ...s.records.map(r => h('li', { key: r.id, style: { paddingBlock: '.5rem' } },
        h('strong', null, r.title), ` · ${r.state} · ${r.sensitive ? 'Sensitive' : r.domain} `,
        button(r.sensitive ? 'Reveal sensitive record' : 'Inspect record', () => controller.inspect(r.id, s.ownerKey), s.busy)))),
      s.next && button('Load more records', () => controller.more(false, s.ownerKey), s.busy)),
    !project && inspectable && h(SourcePanel, { key: s.ownerKey, state: s, controller, disabled }),
    s.selected && (!project || inspectable) && h(RecordDetail, { key: s.ownerKey, detail: s.selected, controller, disabled, ownerKey: s.ownerKey, projectKey: s.projectKey }),
    inspectable && h('section', { style: sectionStyle }, h('h2', null, project ? 'Project trash' : 'Private trash'),
      h('p', null, 'Deleted bodies remain on disk until restoration. No permanent purge is provided. Transcripts, exports and backups are separate.'),
      !s.trash.length && h('p', null, 'No retained groups in this chat.'),
      h('ul', null, ...s.trash.map(item => h('li', { key: item.recovery_id }, `${item.record_count} record(s) · ${item.deleted_at} `,
        button('Review restore', () => controller.stage('restore', item.recovery_id, s.ownerKey, null, s.projectKey), disabled)))),
      s.trashNext && button('Load more retained groups', () => controller.more(true, s.ownerKey), s.busy)),
    !project && h(SelectedImportPanel, { controller, state: s }),
    !project && h(CurationJobsPanel, { controller, state: s }),
    !project && h(CurationPanel, { controller, state: s }),
    !project && h(ConversationCapturePanel, { controller, state: s }),
    !project && h(RecallSettingsPanel, { controller, state: s }),
    s.action && h(Confirmation, { state: s, controller }),
    h('footer', { style: sectionStyle }, project ? 'Experimental project review. A refreshed snapshot, not a live authorization indicator. External binding or consent changes are checked before the next operation. No automatic assistant recall or privacy erasure.' : 'Experimental private-chat review. Optional private automatic recall is separate and off by default. Not project automatic recall or privacy erasure.'));
}

// Adapted strict document validation and Markdown export from recovered MIT Rich Answers 0.1.1.
const richCategories = { progress: 'Progress', answer: 'Answer', question: 'Question', final: 'Final answer' };
const lengths = { title: 180, summary: 1800, sectionTitle: 160, body: 30000, note: 2000 };
export function safeUrl(value) {
  if (
    typeof value !== "string" ||
    [...value].length > 4096 ||
    !/^https?:\/\//i.test(value) ||
    /[\s\\\u0000-\u001f\u007f-\u009f]/.test(value)
  )
    return null;
  try {
    const parsed = new URL(value);
    return ["http:", "https:"].includes(parsed.protocol) &&
      parsed.hostname &&
      !parsed.username &&
      !parsed.password
      ? value
      : null;
  } catch {
    return null;
  }
}

function sourceUrl(value) {
  // Source metadata and the browser's ability to open a link are separate.
  // The Python store can retain HTTP(S) URIs rejected by WHATWG URL parsing.
  // Keep those sources inspectable, but never turn them into an OS action.
  const url = text(value, 4096, true);
  const authority = /^https?:\/\/([^/?#]+)/i.exec(url)?.[1];
  if (!authority || /[\\\p{White_Space}]/u.test(url) || authority.includes("@"))
    throw new Error("Invalid source URL");
  return url;
}

function object(value, required, optional) {
  if (
    !value ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    required.some((key) => !Object.hasOwn(value, key)) ||
    Object.keys(value).some(
      (key) => !required.includes(key) && !optional.includes(key),
    )
  )
    throw new Error("Invalid answer fields");
}

function text(value, limit, nonempty = false) {
  if (
    typeof value !== "string" ||
    [...value].length > limit ||
    (nonempty && !value.trim()) ||
    /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f\ud800-\udfff]/u.test(
      value,
    )
  )
    throw new Error("Invalid answer text");
  return value;
}

export function normalizeDocument(raw) {
  object(raw, ["title", "summary", "sections"], ["sources", "note", "category"]);
  if (raw.category !== undefined && !Object.hasOwn(richCategories, raw.category)) throw new Error("Invalid answer category");
  const doc = {
    category: raw.category || "answer",
    title: text(raw.title, lengths.title, true),
    summary: text(raw.summary, lengths.summary),
    sections: [],
    sources: [],
    note: text(raw.note === undefined ? "" : raw.note, lengths.note),
  };
  if (!Array.isArray(raw.sections) || raw.sections.length > 24)
    throw new Error("Invalid sections");
  doc.sections = raw.sections.map((section) => {
    object(section, ["title", "body"], ["detail"]);
    if (section.detail !== undefined && typeof section.detail !== "boolean")
      throw new Error("Invalid section");
    return {
      title: text(section.title, lengths.sectionTitle, true),
      body: text(section.body, lengths.body),
      detail: section.detail === true,
    };
  });
  if (
    raw.sources !== undefined &&
    (!Array.isArray(raw.sources) || raw.sources.length > 32)
  )
    throw new Error("Invalid sources");
  const ids = new Set();
  doc.sources = (raw.sources || []).map((source) => {
    object(source, ["id", "title", "url"], ["note"]);
    const id = text(source.id, 64);
    if (
      !/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$/.test(id) ||
      ids.has(id)
    )
      throw new Error("Invalid source");
    ids.add(id);
    return {
      id,
      title: text(source.title, 300, true),
      url: sourceUrl(source.url),
      note: text(source.note === undefined ? "" : source.note, 2000),
    };
  });
  if (new TextEncoder().encode(JSON.stringify(doc)).length > 100000)
    throw new Error("Answer too large");
  return doc;
}

function markdownPlain(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replace(/[\\`*_{}\[\]()#+.!|=~\-]/g, "\\$&")
    .replace(/(^|\n)([ \t]+)/g, (_, prefix, indent) =>
      prefix + [...indent].map((char) => char === "\t" ? "&#9;" : "&#32;").join(""),
    )
    .replaceAll("\n", "  \n");
}

function markdownLabel(value) {
  return markdownPlain(value.replace(/[\n\t]/g, " "));
}

function markdownUrl(value) {
  return [...new TextEncoder().encode(value)]
    .map((byte) => {
      const char = String.fromCharCode(byte);
      return /[A-Za-z0-9_./:#?&=@\[\]!$%*+,;~\-]/.test(char)
        ? char
        : `%${byte.toString(16).toUpperCase().padStart(2, "0")}`;
    })
    .join("");
}

export function toMarkdown(doc) {
  const parts = [`# ${markdownLabel(doc.title)}`, `Presentation label: ${richCategories[doc.category || "answer"]} (self-declared)`, markdownPlain(doc.summary)];
  for (const section of doc.sections)
    parts.push(`## ${markdownLabel(section.title)}`, section.body);
  if (doc.sources.length) {
    parts.push("## Sources");
    for (const source of doc.sources)
      parts.push(
        `- [${markdownLabel(source.id)}] [${markdownLabel(source.title)}](${markdownUrl(source.url)})${source.note ? ` — ${markdownLabel(source.note)}` : ""}`,
      );
  }
  if (doc.note) parts.push("## Note", markdownPlain(doc.note));
  return parts.join("\n\n") + "\n";
}


export function richMarkdownComponents(ctx) {
  return {
    a: ({ href, children }) => { const url = safeUrl(href); return url ? h(Button, { type: 'button', variant: 'link', onClick: () => ctx.os?.openExternal?.(url) }, children) : h('span', null, children); },
    img: ({ alt }) => h('span', null, `Image: ${alt || 'unnamed'} (not loaded automatically)`),
    pre: ({ children }) => h('pre', { tabIndex: 0, style: { overflowX: 'auto' } }, children),
    table: ({ children }) => h('div', { role: 'region', 'aria-label': 'Scrollable comparison table', tabIndex: 0, style: { overflowX: 'auto' } }, h('table', null, children)),
    input: ({ checked }) => h('span', { role: 'img', 'aria-label': checked ? 'Checked' : 'Unchecked' }, checked ? '☑' : '☐'),
    h1: ({ children }) => h('h4', null, children), h2: ({ children }) => h('h4', null, children), h3: ({ children }) => h('h4', null, children),
  };
}
export function RichAnswerReader({ document, ctx = {}, enabled = true, density = 'comfortable' }) {
  const [plain, setPlain] = useState(false), [status, setStatus] = useState('');
  let doc; try { doc = normalizeDocument(document); } catch { return h('p', { role: 'note' }, 'Invalid rich answer. Use the ordinary answer fallback.'); }
  const markdown = toMarkdown(doc);
  const body = value => SDK.Streamdown ? h(SDK.Streamdown, { mode: 'static', skipHtml: true, controls: false, components: richMarkdownComponents(ctx) }, value) : h('pre', { style: proseStyle }, value);
  if (!enabled) return h('pre', { style: proseStyle }, markdown);
  return h('article', { 'aria-label': 'ELM rich answer', style: { border: '1px solid var(--ui-stroke-secondary)', borderRadius: '12px', padding: density === 'compact' ? '.75rem' : '1.5rem', maxWidth: '76ch', marginInline: 'auto', overflowWrap: 'anywhere' } },
    h('p', null, h('strong', null, richCategories[doc.category]), ' · self-declared presentation, not verified completion'),
    h('h2', null, doc.title), h('p', { style: proseStyle }, doc.summary),
    doc.note && h('aside', { style: sectionStyle }, h('strong', null, 'Important context'), h('p', { style: proseStyle }, doc.note)),
    h('div', { style: rowStyle }, button(plain ? 'Formatted view' : 'Markdown text', () => setPlain(!plain)),
      button('Copy full answer', async () => { try { if (!ctx.os?.writeClipboard || !(await ctx.os.writeClipboard(markdown))) throw Error(); setStatus('Copied'); } catch { setStatus('Copy unavailable; use Markdown text.'); } })),
    status && h('p', { role: 'status' }, status),
    plain ? h('pre', { style: proseStyle }, markdown) : h('div', null,
      ...doc.sections.map((section, index) => section.detail ? h('details', { key: index, style: sectionStyle }, h('summary', null, section.title), body(section.body)) : h('section', { key: index, style: sectionStyle }, h('h3', null, section.title), body(section.body))),
      doc.sources.length > 0 && h('section', { style: sectionStyle }, h('h3', null, 'Sources'), h('p', null, 'Links open only when you choose them. Source labels are not independent verification.'),
        h('ol', null, ...doc.sources.map(source => h('li', { key: source.id }, h('span', null, `[${source.id}] `), button(source.title, () => ctx.os?.openExternal?.(safeUrl(source.url)), !safeUrl(source.url)), h('p', { style: proseStyle }, source.url), source.note && h('p', null, source.note)))))));
}

export function parseRichDirective(attrs) {
  if (!attrs || typeof attrs !== 'object' || Array.isArray(attrs) || Object.keys(attrs).some(key => !['category', 'title', 'text'].includes(key)) || Object.values(attrs).some(value => typeof value !== 'string') || JSON.stringify(attrs).length > 2048) throw new Error('Invalid inline answer');
  const category = attrs.category || 'answer';
  if (!Object.hasOwn(richCategories, category)) throw new Error('Invalid category');
  return { category, title: text(attrs.title || richCategories[category], 180, true), summary: text(attrs.text || '', 1200), sections: [], sources: [] };
}
export function createRichPreferences(ctx) {
  const normalize = raw => ({ enabled: raw?.enabled !== false, density: raw?.density === 'compact' ? 'compact' : 'comfortable' });
  let state; try { state = normalize(ctx.storage?.get?.('rich-reading.v1', {})); } catch { state = { ...normalize({}), save_error: 'Saved reading preferences unavailable; using temporary defaults.' }; }
  const listeners = new Set();
  return { getSnapshot: () => state, subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    set(patch) { const next = normalize({ ...state, ...patch }); try { if (!ctx.storage?.set) throw Error(); ctx.storage.set('rich-reading.v1', next); state = next; } catch { state = { ...next, save_error: 'Reading preference changed for this session only; saving is unavailable.' }; } for (const fn of listeners) fn(); },
    dispose() { listeners.clear(); } };
}
export function RichInlineAnswer({ attrs, source = '', streaming = false, preferences, ctx }) {
  const prefs = useSyncExternalStore(preferences.subscribe, preferences.getSnapshot, preferences.getSnapshot);
  let doc; try { doc = parseRichDirective(attrs); } catch { return h('span', { style: proseStyle }, source); }
  // No data fetch or storage. Disabled/streaming displays the complete bounded text.
  if (!prefs.enabled || streaming) return h('div', { style: proseStyle }, `${richCategories[doc.category]} (self-declared): ${doc.title}${doc.summary ? '\n' + doc.summary : ''}`);
  return h(RichAnswerReader, { document: doc, ctx, enabled: true, density: prefs.density });
}
export function RichSettingsPage({ preferences, ctx }) {
  const prefs = useSyncExternalStore(preferences.subscribe, preferences.getSnapshot, preferences.getSnapshot);
  return h('main', { style: { padding: '1.5rem', maxWidth: '80ch', margin: 'auto' } }, h('h1', null, 'Rich answer reading'),
    h('p', null, 'Frontend-only presentation. Ordinary messages remain native Markdown. Only explicit elm-answer directives receive a bounded card; categories are self-declared, not verified progress or completion.'),
    h('label', null, h('input', { type: 'checkbox', checked: prefs.enabled, onChange: e => preferences.set({ enabled: e.target.checked }) }), 'Enable rich answer formatting'),
    h('label', null, 'Reading spacing', h('select', { value: prefs.density, onChange: e => preferences.set({ density: e.target.value }) }, h('option', { value: 'comfortable' }, 'Comfortable'), h('option', { value: 'compact' }, 'Compact'))),
    h('p', null, 'Preferences are local to this ELM desktop plugin, shared across profiles. Only display preferences are stored, never answer bodies. Disabling formatting retains the inline text and does not enable or disable memory, external processing or the plugin itself.'),
    prefs.save_error && h('p', { role: 'status' }, prefs.save_error),
    h('h2', null, 'Author syntax'), h('pre', { style: proseStyle }, '::elm-answer{category="answer" title="A clear plan" text="Start with the door."}'),
    h('p', null, 'Categories: progress, answer, question, final. Optional title ≤180 Unicode characters; optional plain text ≤1200. Total attributes must fit the native 2048-character directive cap. Use ordinary Markdown after the directive for longer answers. No saved-document publish tool or legacy answer store is enabled.'),
    h('h2', null, 'Synthetic component examples, not a native screenshot'),
    ...Object.keys(richCategories).map(category => h(RichInlineAnswer, { key: category, attrs: { category, title: `${richCategories[category]} example`, text: 'Synthetic presentation example. No request, result or completion is implied.' }, source: '', streaming: false, preferences, ctx })));
}
function registerRichPresentation(ctx) {
  if (typeof SDK.TRANSCRIPT_DIRECTIVE_AREA !== 'string') return;
  const preferences = createRichPreferences(ctx); ctx.onDispose(() => preferences.dispose());
  ctx.register({ id: 'rich-inline-answer', area: SDK.TRANSCRIPT_DIRECTIVE_AREA, data: { name: 'elm-answer', render: props => h(RichInlineAnswer, { ...props, preferences, ctx }) } });
  ctx.registerSettingsPage?.({ id: 'rich-reading', title: 'Rich answer reading', render: () => h(RichSettingsPage, { preferences, ctx }) });
}

// Whole-message presentation is distinct from inline rich-answer cards.
export const messageTypes = { progress: 'Progress', update: 'Update', answer: 'Answer', final: 'Final', question: 'Question' };
const messageAccents = ['theme','blue','green','amber','violet','rose'];
const messageDefaults = type => ({ enabled: true, label: messageTypes[type], showLabel: true, accent: 'theme', background: 'subtle', border: 'side' });
function normalizeMessagePreferences(raw = {}) {
  const types = {};
  for (const type of Object.keys(messageTypes)) {
    const defaults = messageDefaults(type), item = raw?.types?.[type] || {};
    const label = typeof item.label === 'string' && item.label.trim() && item.label.length <= 24 && !/[\p{Cc}\p{Cf}\p{Cs}]/u.test(item.label) ? item.label.trim() : defaults.label;
    types[type] = { enabled: item.enabled !== false, label, showLabel: item.showLabel !== false,
      accent: messageAccents.includes(item.accent) ? item.accent : defaults.accent,
      background: ['none','subtle'].includes(item.background) ? item.background : defaults.background,
      border: ['none','side','outline'].includes(item.border) ? item.border : defaults.border };
  }
  return { enabled: raw?.enabled === true, types };
}
export function classifyMessagePresentation({role,textPrefix,streaming}, preferences) {
  if (role !== 'assistant' || typeof textPrefix !== 'string' || !preferences?.enabled) return null;
  let prefix = textPrefix.slice(0,8192);
  if (textPrefix.length > 8192 || (streaming && !prefix.endsWith('\n'))) prefix = prefix.slice(0,prefix.lastIndexOf('\n')+1);
  let fence = null, previousBlank = true;
  for (const line of prefix.split(/\r?\n/)) {
    const canStart = previousBlank; previousBlank = !line.trim();
    const marker = /^ {0,3}(`{3,}|~{3,})(.*)$/.exec(line);
    if (marker) { if (!fence) fence = {char:marker[1][0],length:marker[1].length}; else if(marker[1][0]===fence.char && marker[1].length>=fence.length && !marker[2].trim()) fence=null; continue; }
    if (fence) continue;
    const match = /^ {0,3}::elm-message\{type="(progress|update|answer|final|question)"\}[ \t]*$/.exec(line);
    if (match && canStart) { const item=preferences.types[match[1]]; if(!item?.enabled)return null; const {enabled,...style}=item; return {type:match[1],...style}; }
  }
  return null;
}
export function createMessagePresentationPreferences(ctx) {
  let state; try { state=normalizeMessagePreferences(ctx.storage?.get?.('message-presentation.v1',{})); } catch { state={...normalizeMessagePreferences(),save_error:'Saved display preferences unavailable; whole-message styling stays off.'}; }
  const listeners=new Set();
  const save=raw=>{const next=normalizeMessagePreferences(raw);try{if(!ctx.storage?.set)throw Error();ctx.storage.set('message-presentation.v1',next);state=next;}catch{state={...next,save_error:'Changed for this session only; saving is unavailable.'};}for(const f of listeners)f();};
  return {getSnapshot:()=>state,subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn);},setEnabled(enabled){save({...state,enabled:enabled===true});},setType(type,patch){if(Object.hasOwn(messageTypes,type))save({...state,types:{...state.types,[type]:{...state.types[type],...patch}}});},reset(){save({});},dispose(){listeners.clear();}};
}
export function MessagePresentationSettings({preferences,supported}) {
  const prefs=useSyncExternalStore(preferences.subscribe,preferences.getSnapshot,preferences.getSnapshot);
  const select=(label,value,options,onChange)=>h('label',null,label,' ',h('select',{value,onChange:e=>onChange(e.target.value)},...options.map(x=>h('option',{key:x,value:x},x))));
  return h('main',{style:{maxWidth:'76ch',padding:'1.5rem',margin:'auto'}},h('h1',null,'Message bubble types'),
    h('p',null,'Style the whole assistant message, not just an inline answer card. Types are author-declared presentation, never verified progress, completion, correctness or authority.'),
    h('label',null,h('input',{type:'checkbox',checked:prefs.enabled,disabled:!supported,onChange:e=>preferences.setEnabled(e.target.checked)}),'Enable whole-message type styling'),
    !supported&&h('p',{role:'note'},'This host lacks native whole-message presentation support. No bubble styling is emulated.'),
    h('p',null,'Off by default. These display settings are local to this Desktop installation and shared across ELM profiles. No message contents are stored by these preferences. Disabling removes the style policy; native messages remain unchanged.'),
    prefs.save_error&&h('p',{role:'status'},prefs.save_error),
    h('h2',null,'Author syntax'),h('pre',{style:proseStyle},'::elm-message{type="question"}\nWhat should we do next?'),
    h('p',null,'Place one marker at the start of the message or after a blank line, on its own line outside quoted, fenced or indented code, within the first 8192 characters. Mixed tool/reasoning messages and text-fragment boundaries without a real newline are conservatively left unstyled. The first recognized marker controls this message. During streaming, the marker line must end with a newline. The marker remains visible in ordinary Markdown and copy output: this feature does not remove or rewrite source text. It does not instruct a model to generate markers automatically.'),
    ...Object.keys(messageTypes).map(type=>{const p=prefs.types[type];return h('fieldset',{key:type,style:sectionStyle},h('legend',null,messageTypes[type]),
      h('label',null,h('input',{type:'checkbox',checked:p.enabled,onChange:e=>preferences.setType(type,{enabled:e.target.checked})}),'Style this type'),
      h('label',null,'Short label ',h('input',{value:p.label,maxLength:24,onChange:e=>preferences.setType(type,{label:e.target.value})})),
      h('label',null,h('input',{type:'checkbox',checked:p.showLabel,onChange:e=>preferences.setType(type,{showLabel:e.target.checked})}),'Show type label'),
      select('Accent',p.accent,messageAccents,accent=>preferences.setType(type,{accent})),
      select('Background',p.background,['none','subtle'],background=>preferences.setType(type,{background})),
      select('Border',p.border,['none','side','outline'],border=>preferences.setType(type,{border})));}),
    h('button',{type:'button',onClick:()=>preferences.reset()},'Reset display defaults'));
}
export function registerMessagePresentation(ctx) {
  const supported=typeof SDK.TRANSCRIPT_PRESENTATION_AREA==='string',preferences=createMessagePresentationPreferences(ctx);let unregister=null;
  const sync=()=>{if(unregister){unregister();unregister=null;}const snapshot=preferences.getSnapshot();if(supported&&snapshot.enabled)unregister=ctx.register({id:'message-bubble-types',area:SDK.TRANSCRIPT_PRESENTATION_AREA,data:{classify:input=>classifyMessagePresentation(input,snapshot)}});};
  ctx.registerSettingsPage?.({id:'message-bubble-types',title:'Message bubble types',render:()=>h(MessagePresentationSettings,{preferences,supported})});
  const stop=preferences.subscribe(sync);sync();ctx.onDispose(()=>{stop();if(unregister)unregister();unregister=null;preferences.dispose();});return preferences;
}

const importanceLabels = { important: 'Important', decision: 'Decision', question: 'Question', warning: 'Warning', result: 'Result' };
export function classifyImportantMessage({ role, textPrefix }) {
  if (!['user', 'assistant'].includes(role) || typeof textPrefix !== 'string') return null;
  const prefix = textPrefix.slice(0, 8192), lines = prefix.split(/\r?\n/);
  // Never classify a potentially cut final line from a bounded prefix.
  if (prefix.length >= 8192) lines.pop();
  let fence = null;
  for (const line of lines) {
    const marker = /^ {0,3}(`{3,}|~{3,})(.*)$/.exec(line);
    if (marker) {
      if (!fence) fence = { char: marker[1][0], length: marker[1].length };
      else if (marker[1][0] === fence.char && marker[1].length >= fence.length && !marker[2].trim()) fence = null;
      continue;
    }
    if (fence) continue;
    const match = /^ {0,3}::elm-important\{kind="(important|decision|question|warning|result)"\}[ \t]*$/.exec(line);
    if (match) return { label: importanceLabels[match[1]] };
  }
  return null;
}
export function createImportancePreferences(ctx) {
  let state; try { state = { enabled: ctx.storage?.get?.('importance.v1', {})?.enabled === true }; }
  catch { state = { enabled: false, save_error: 'Importance preference unavailable; highlighting stays off.' }; }
  const listeners = new Set();
  return { getSnapshot: () => state, subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    set(enabled) { const next = { enabled: enabled === true }; try { if (!ctx.storage?.set) throw Error(); ctx.storage.set('importance.v1', next); state = next; } catch { state = { ...next, save_error: 'Changed for this session only; saving is unavailable.' }; } for (const fn of listeners) fn(); },
    dispose() { listeners.clear(); } };
}
export function ImportanceSettingsPage({ preferences, supported }) {
  const prefs = useSyncExternalStore(preferences.subscribe, preferences.getSnapshot, preferences.getSnapshot);
  return h('main', { style: { maxWidth: '76ch', padding: '1.5rem', margin: 'auto' } }, h('h1', null, 'Important messages'),
    h('p', null, 'Explicit message markers, not automatic judgments. A marked decision or result is self-declared and does not verify correctness, completion or authority.'),
    h('label', null, h('input', { type: 'checkbox', checked: prefs.enabled, disabled: !supported, onChange: e => preferences.set(e.target.checked) }), 'Highlight marked messages and show clickable timeline markers'),
    !supported && h('p', { role: 'note' }, 'This host lacks the native importance contribution. No timeline or navigation is emulated.'),
    prefs.save_error && h('p', { role: 'status' }, prefs.save_error),
    h('p', null, 'Off by default. This local display preference is shared across ELM Desktop profiles; no message bodies or marker identities are saved. Disabling unregisters the importance policy. The host retains ownership of message IDs, session scope and navigation.'),
    h('h2', null, 'Mark a message'), h('pre', { style: proseStyle }, '::elm-important{kind="decision"}'),
    h('p', null, 'Place the marker on its own line outside fenced or indented code. Supported kinds: important, decision, question, warning, result. Only the first recognized marker in the first 8192 characters is used. Markers in fenced-code examples are ignored.'),
    h('p', null, 'Loaded messages only. Existing native user ticks can be decorated; marked loaded assistant messages get host-owned ticks. No extra assistant-history bodies are fetched. A marker click uses native scoped navigation, not a plugin-generated destination.'),
    h('h2', null, 'Synthetic marker labels, not a timeline screenshot'),
    h('div', { style: rowStyle }, ...Object.values(importanceLabels).map(label => h('span', { key: label, style: { padding: '.4rem .6rem', borderInlineStart: '3px solid var(--ui-text-primary)' } }, label))),
    h('p', null, 'The samples above demonstrate labels only. They are not clickable timeline markers and do not claim native visual acceptance.'));
}
export function ImportantMarker({ attrs, source = '' }) {
  if (!attrs || Object.keys(attrs).length !== 1 || typeof attrs.kind !== 'string' || !Object.hasOwn(importanceLabels, attrs.kind)) return h('span', { style: proseStyle }, source);
  return h('span', { role: 'note' }, `${importanceLabels[attrs.kind]} · marked by author, not verified`);
}
export function registerImportancePresentation(ctx) {
  const supported = typeof SDK.TRANSCRIPT_IMPORTANCE_AREA === 'string';
  const preferences = createImportancePreferences(ctx); let unregister = null;
  if (typeof SDK.TRANSCRIPT_DIRECTIVE_AREA === 'string') ctx.register({ id: 'important-message-label', area: SDK.TRANSCRIPT_DIRECTIVE_AREA, data: { name: 'elm-important', render: props => h(ImportantMarker, props) } });
  const sync = () => {
    if (unregister) { unregister(); unregister = null; }
    if (supported && preferences.getSnapshot().enabled) unregister = ctx.register({ id: 'explicit-important-messages', area: SDK.TRANSCRIPT_IMPORTANCE_AREA, data: { classify: classifyImportantMessage } });
  };
  // Settings remain available on older hosts, but unsupported navigation is never invented.
  ctx.registerSettingsPage?.({ id: 'important-messages', title: 'Important messages', render: () => h(ImportanceSettingsPage, { preferences, supported }) });
  const stop = preferences.subscribe(sync); sync();
  ctx.onDispose(() => { stop(); if (unregister) unregister(); unregister = null; preferences.dispose(); });
  return preferences;
}

export function createChatFolderPreferences(ctx) {
  let state;try{state={enabled:ctx.storage?.get?.('chat-folders.v1',{})?.enabled===true};}catch{state={enabled:false,save_error:'Display preference unavailable; folder section stays off.'};}
  const listeners=new Set();return{getSnapshot:()=>state,subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn);},set(enabled){const next={enabled:enabled===true};try{if(!ctx.storage?.set)throw Error();ctx.storage.set('chat-folders.v1',next);state=next;}catch{state={...next,save_error:'Display changed for this session only; saving unavailable.'};}for(const fn of listeners)fn();},dispose(){listeners.clear();}};
}
function ChatFolderRow({folder,status,controller,ownerKey,disabled}) {
  const [editing,setEditing]=useState(false), [label,setLabel]=useState(folder.label);
  return h('li',{style:{padding:'0.75rem 0',borderBottom:'1px solid #9994'}},
    h('strong',null,folder.label+' '),
    button('File current chat here',()=>controller.stageChatFolder('file',folder.id,ownerKey,status),disabled||status.current_folder_id===folder.id),
    button(editing?'Cancel rename':'Rename',()=>{setEditing(!editing);setLabel(folder.label);controller.cancel();},disabled),
    editing&&h('div',null,h('label',null,'New name for '+folder.label,h(Input,{value:label,maxLength:80,disabled,onChange:e=>{setLabel(e.target.value);controller.cancel();}})),
      button('Review rename',()=>controller.stageChatFolder('rename',{folder_id:folder.id,label},ownerKey,status),disabled||!label.trim()||label!==label.trim()||label===folder.label)),
    button('Review removing empty folder',()=>controller.stageChatFolder('remove',folder.id,ownerKey,status),disabled||folder.removable!==true),
    folder.removable!==true&&h('small',null,' Removal unavailable: this folder has saved memberships, or empty status has not been verified. Unfile its chats first.'));
}
export function ChatFoldersPage({controller,preferences,supported}) {
  const observed=useSyncExternalStore(controller.subscribe,controller.getSnapshot,controller.getSnapshot), prefs=useSyncExternalStore(preferences.subscribe,preferences.getSnapshot,preferences.getSnapshot);
  const state=observed.ownerKey===controller.currentKey()?observed:blank(controller.currentKey());
  const [label,setLabel]=useState(''); useLayoutEffect(()=>{setLabel('');},[state.ownerKey]); const status=state.folderStatus, disabled=state.busy||state.uncertain||!!state.error;
  return h('main',{style:{padding:'1.5rem',maxWidth:'76ch',margin:'auto'}},h('h1',null,'Folders for chats'),
    h('p',null,'Metadata-only filing, not filesystem folders or native project moves. No working-directory, git, native project or ELM memory-permission changes.'),
    h('label',null,h('input',{type:'checkbox',checked:prefs.enabled,disabled:!supported,onChange:e=>preferences.set(e.target.checked)}),'Show chat folders in the native sidebar'),
    !supported&&h('p',{role:'note'},'This host lacks the native chat-folder section; no sidebar is emulated.'),prefs.save_error&&h('p',{role:'status'},prefs.save_error),
    h('p',null,'Off by default. Display preference is local/shared across profiles; folder membership is authenticated host metadata. Refresh is explicit. Only already-loaded, exact-owner native chat rows are shown; unavailable or unloaded rows do not imply empty folders. Recents, Projects and search remain unchanged.'),
    button('Refresh current-chat folders',()=>controller.refreshChatFolders(state.ownerKey),state.busy),state.error&&h('p',{role:'alert'},state.error),state.notice&&h('p',{role:'status'},state.notice),
    state.uncertain&&h('p',null,'Outcome uncertain: inspect current folders before another intentional action; never replay automatically.'),
    status&&h('section',{key:state.ownerKey},h('p',null,`Current chat ${status.current_session_id} · revision ${status.revision} · ${status.unavailable_members || 0} unavailable saved membership(s) · folder ${status.folders.find(f=>f.id===status.current_folder_id)?.label||'Unfiled'}`),
      h('label',null,'New folder label',h(Input,{value:label,maxLength:80,disabled,onChange:e=>setLabel(e.target.value)})),button('Review creating folder',()=>controller.stageChatFolder('create',label,state.ownerKey,status),disabled||!label.trim()),
      h('ul',null,...status.folders.map(folder=>h(ChatFolderRow,{key:state.ownerKey+':'+status.revision+':'+folder.id,folder,status,controller,ownerKey:state.ownerKey,disabled}))),
      button('Review unfiling current chat',()=>controller.stageChatFolder('file',null,state.ownerKey,status),disabled||!status.current_folder_id),
      button('Review undoing latest filing',()=>controller.stageChatFolder('undo',null,state.ownerKey,status),disabled||!status.undo_available)),
    state.action?.kind.startsWith('folder_')&&h(Confirmation,{state,controller}),
    h('p',null,'Flat chat folders support create, rename, removal when no saved memberships remain, current-chat file/unfile and revision-safe filing undo. Folder management clears prior filing undo. Nesting, drag-and-drop and full-history folder loading are not implemented. No chats are deleted and no synthetic rows are inserted.'));
}
export function bindNativeChatFolders(ctx,controller,preferences,supported) {
  let unregister=null;
  const sync=()=>{if(unregister){unregister();unregister=null;}if(supported&&preferences.getSnapshot().enabled){const snapshot=controller.chatFolderSnapshot();if(snapshot)unregister=ctx.register({id:'native-chat-folders',area:SDK.CHAT_FOLDERS_AREA,data:snapshot});}};
  const stopController=controller.subscribe(sync),stopPreferences=preferences.subscribe(sync);sync();
  return()=>{stopController();stopPreferences();if(unregister)unregister();unregister=null;};
}

export function createUpdateController(host, epoch=()=>0) {
  const identify=()=>{const s=host?.state||{},profile=read(s.profile),connection=read(s.connectionId),gateway=read(s.gateway);return {profile,key:JSON.stringify([profile,connection,gateway,epoch()]),error:!profile||!connection||gateway!=='open'?'Connect the intended profile before refreshing update policy.':''};};
  let identity=identify(),generation=0,disposed=false;
  const empty=()=>({ownerKey:identity.key,status:null,action:null,busy:false,uncertain:false,error:identity.error});
  let state=empty();const listeners=new Set(),stops=[];
  const publish=patch=>{state={...state,...patch};for(const fn of listeners)fn();};
  const sync=()=>{const next=identify();if(next.key!==identity.key){identity=next;generation++;state=empty();for(const fn of listeners)fn();}return next;};
  for(const atom of Object.values(host?.state||{}))if(atom?.subscribe)stops.push(atom.subscribe(sync));
  const validStatus=s=>s?.name==='elm'&&['inherit','enabled','disabled'].includes(s.mode)&&Number.isSafeInteger(s.revision)&&s.revision>=0&&typeof s.source_fingerprint==='string'&&typeof s.eligible==='boolean'&&typeof s.effective_auto_apply==='boolean';
  async function run(action) {
    const current=sync();if(disposed||current.error||state.busy)return;
    if(action&&(action!==state.action||action.ownerKey!==current.key||state.uncertain))return;
    const stamp=++generation,socket=host.getGateway?.();
    const valid=()=>!disposed&&sync().key===current.key&&generation===stamp&&(!host.getGateway||host.getGateway()===socket);
    publish({busy:true,error:'',action:null,status:null});
    try{
      const result=await host.request('plugins.manage',{action:'auto_update_plugin',name:'elm',profile:current.profile,...(action?{enable:action.enable,expected_revision:action.status.revision,expected_source:action.status.source_fingerprint,confirm:true}:{})});
      if(!valid())return;if(!validStatus(result))throw Error('Unsupported update-policy response. Refresh after checking host compatibility.');
      publish({status:result,busy:false,uncertain:false});
    }catch(error){if(valid())publish({status:null,busy:false,uncertain:!!action,error:action?'Policy change was not confirmed. An admitted update may still be running. Refresh to reconcile; nothing is retried automatically.':'Could not read local update policy. Check the host connection and compatibility, then refresh.'});}
  }
  return {getSnapshot:()=>state,subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn);},currentKey:()=>identify().key,refresh:()=>run(null),stage(enable,ownerKey=state.ownerKey,status=state.status){const current=sync();if(disposed||current.error||current.key!==ownerKey||state.busy||state.uncertain||!status||status!==state.status||typeof enable!=='boolean'||(enable&&!status.eligible))return;publish({action:Object.freeze({enable,ownerKey,status:JSON.parse(JSON.stringify(status))})});},confirm:(action=state.action)=>action?run(action):undefined,cancel(){publish({action:null});},dispose(){disposed=true;generation++;for(const stop of stops)stop();listeners.clear();}};
}
export function safeUpdateSource(source) {
  if(!source)return null;
  const result={};for(const key of ['catalog_name','subdir','tier','installed_revision'])result[key]=typeof source[key]==='string'?source[key].slice(0,512):'not reported';
  try{const u=new URL(source.repo);result.repo=!['https:','http:'].includes(u.protocol)||u.username||u.password||u.search||u.hash?'Source URL withheld; unsupported or contains private components':u.origin+u.pathname;}catch{result.repo='Source URL unavailable';}
  return result;
}
export function UpdatePolicyPage({controller}) {
  const state=useSyncExternalStore(controller.subscribe,controller.getSnapshot,controller.getSnapshot);
  if(state.ownerKey!==controller.currentKey())return h('p',null,'Profile changed. Refresh update policy in the intended profile.');
  const status=state.status,action=state.action,source=safeUpdateSource((action?.status||status)?.source);
  return h('section',{style:{padding:'1rem',maxWidth:900}},h('h1',null,'ELM automatic updates'),
    h('p',null,'Local policy inspection only. Refresh does not fetch updates or install code. No host upgrade is performed.'),
    h('button',{disabled:state.busy,onClick:()=>controller.refresh()},state.busy?'Waiting for host…':'Refresh local update policy'),
    state.error&&h('p',{role:'alert'},state.error),
    status&&h('div',null,h('p',null,`Policy: ${status.mode}. Effective automatic application: ${status.effective_auto_apply?'on':'off'}.`),
      h('p',null,'Inherited policy follows the existing profile-wide host setting; it is not necessarily off. Explicit Off blocks automatic application for ELM, not every native update check.'),
      h('p',null,'Eligibility: '+(status.eligible?'recognized catalog source':String(status.reason||'unavailable'))),
      h('p',null,`Startup check policy: ${status.startup_check===true?'enabled':'not enabled'}. Interval: ${Number.isFinite(status.check_hours)?status.check_hours:'not reported'} hours. A check may contact the approved source; policy refresh above is local only.`),
      h('p',null,'Updates run during gateway housekeeping when due, not necessarily when the Desktop opens. Updated code loads in new sessions. Disabling cannot cancel an already admitted operation.'),
      h('button',{disabled:state.busy||state.uncertain||!status.eligible,onClick:()=>controller.stage(true,state.ownerKey,status)},'Review enabling automatic updates'),
      h('button',{disabled:state.busy||state.uncertain,onClick:()=>controller.stage(false,state.ownerKey,status)},'Review turning automatic updates off'),
      status.last_result==='updated_needs_restart'&&h('p',{role:'status'},'Files were updated, but activation was not confirmed. Further automatic application is disabled. Inspect the result, restart as needed, then review consent again; do not replay the update.'),
      h('p',null,'Attempted or outcome_unconfirmed does not prove an update completed. No per-plugin last-check timestamp is provided by this host contract.'),
      h('p',null,'Last result: '+(status.last_result==null?'No result reported':['configured','current','updated','updated_needs_restart','needs_review','outcome_unconfirmed','attempted'].includes(typeof status.last_result==='string'?status.last_result:status.last_result.status)?(typeof status.last_result==='string'?status.last_result:status.last_result.status):'Host result available; unrecognized details withheld'))),
    source&&h('dl',null,...['catalog_name','repo','subdir','tier','installed_revision'].map(key=>h('div',{key},h('dt',null,key),h('dd',{style:proseStyle},String(source[key]??'not reported'))))),
    action&&h('div',{role:'region','aria-label':'Update policy confirmation'},h('h2',null,action.enable?'Enable future ELM code updates?':'Turn automatic ELM updates off?'),
      h('p',null,'This changes only the ELM policy in the currently selected profile. Enabling authorizes scheduled checks contacting the reviewed source and future code execution from the reviewed recognized catalog source, not cryptographic publisher verification. New capabilities or unsafe updates still require native review. Manual-copy installations cannot be enabled here.'),
      h('p',null,`Reviewed policy revision: ${action.status.revision}`),
      h('button',{disabled:state.busy,onClick:()=>controller.confirm(action)},'Confirm policy change'),h('button',{disabled:state.busy,onClick:()=>controller.cancel()},'Cancel')));
}

export function createWikiController(host,epoch=()=>0){
 let identity=reviewIdentity(host,epoch),generation=0,disposed=false,lane=null;
 const empty=()=>({ownerKey:identity.key,lane,records:[],snapshot:null,next:null,page:null,evidence:null,busy:false,error:identity.error});let state=empty();const listeners=new Set(),stops=[];
 const publish=patch=>{state={...state,...patch};for(const fn of listeners)fn();};
 const sync=()=>{const next=reviewIdentity(host,epoch);if(next.key!==identity.key){identity=next;generation++;lane=null;state=empty();for(const fn of listeners)fn();}return next;};
 for(const atom of Object.values(host?.state||{}))if(atom?.subscribe)stops.push(atom.subscribe(sync));
 const rowValid=r=>r&&typeof r.id==='string'&&r.id.length>0&&r.id.length<=512&&Number.isSafeInteger(r.revision)&&r.revision>0&&['title','domain','kind','basis','topic','updated_at'].every(k=>typeof r[k]==='string'&&r[k].length<=512)&&typeof r.sensitive==='boolean';
 const responseValid=(r,scope,snapshot)=>r?.lane===scope&&r.inspection_only===true&&r.content_role==='untrusted_memory_data'&&typeof r.snapshot_key==='string'&&/^[a-f0-9]{64}$/.test(r.snapshot_key)&&(!snapshot||r.snapshot_key===snapshot);
 async function request(kind,ownerKey,expectedState,record){const current=sync();if(disposed||current.error||current.key!==ownerKey||state!==expectedState||state.busy||!lane)return;
  const scope=lane,snapshot=kind==='index'?null:state.snapshot,stamp=++generation,socket=host.getGateway?.(),oldRecords=state.records;
  if(kind==='more'&&!state.next||['page','evidence'].includes(kind)&&(!record||!snapshot))return;
  if(kind==='page'&&!state.records.some(r=>r.id===record.id&&r.revision===record.revision))return;
  if(kind==='evidence'&&(state.page?.id!==record.id||state.page?.revision!==record.revision))return;
  const params=kind==='index'?{limit:16}:kind==='more'?{limit:16,before:state.next,expected_snapshot:snapshot}:{record_id:record.id,expected_snapshot:snapshot};
  const valid=()=>!disposed&&sync().key===current.key&&lane===scope&&generation===stamp&&(!host.getGateway||host.getGateway()===socket);
  publish({busy:true,error:'',page:kind==='evidence'?state.page:null,evidence:null,...(kind==='index'?{records:[],snapshot:null,next:null}:{})});
  try{const r=await host.request(`plugin.elm.wiki.${scope}.${kind==='more'?'index':kind}`,{...params,session_id:current.session});if(!valid())return;
   if(!responseValid(r,scope,snapshot))throw Error('snapshot');
   if(kind==='index'||kind==='more'){if(!Array.isArray(r.records)||r.records.length>32||!r.records.every(rowValid)||(r.next_before!=null&&(typeof r.next_before!=='string'||r.next_before.length>512)))throw Error('index');publish({records:kind==='more'?[...oldRecords,...r.records]:r.records,snapshot:r.snapshot_key,next:r.next_before||null,busy:false});}
   else if(kind==='page'){if(!Number.isSafeInteger(r.source_count)||r.source_count<0||r.source_count>64||!rowValid(r.record)||typeof r.record.text!=='string'||r.record.text.length>65536||r.record?.id!==record.id||r.record.revision!==record.revision||r.record.state!=='approved'||Object.hasOwn(r.record,'sources'))throw Error('page');publish({page:{...r.record,source_count:r.source_count},busy:false});}
   else{if(r.record_id!==record.id||r.record_revision!==record.revision||r.source_content!=='citation_quotes_only'||!Array.isArray(r.sources)||r.sources.length>64||!r.sources.every(source=>source&&typeof source==='object'&&!Array.isArray(source)&&Object.keys(source).every(k=>['ref','quote','sha256','revision'].includes(k))&&typeof source.ref==='string'&&source.ref.length<=2048&&(!Object.hasOwn(source,'quote')||(typeof source.quote==='string'&&source.quote.length<=16384))&&(!Object.hasOwn(source,'sha256')||(typeof source.sha256==='string'&&/^[a-f0-9]{64}$/i.test(source.sha256)))&&(!Object.hasOwn(source,'revision')||(Number.isSafeInteger(source.revision)&&source.revision>0))))throw Error('evidence');publish({evidence:r.sources,busy:false});}
  }catch{if(valid())publish({records:[],snapshot:null,next:null,page:null,evidence:null,busy:false,error:'This approved-memory snapshot is unavailable or changed. Refresh explicitly. Project reading requires current consent; no automatic retry.'});}
 }
 return{getSnapshot:()=>state,subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn);},currentKey:()=>reviewIdentity(host,epoch).key,select(scope,ownerKey=state.ownerKey){const current=sync();if(disposed||ownerKey!==current.key||!['private','project'].includes(scope))return;generation++;lane=scope;state=empty();for(const fn of listeners)fn();},refresh:(owner=state.ownerKey,rendered=state)=>request('index',owner,rendered),more:(owner=state.ownerKey,rendered=state)=>request('more',owner,rendered),open:(record,owner=state.ownerKey,rendered=state)=>request('page',owner,rendered,record),loadEvidence:(record,owner=state.ownerKey,rendered=state)=>request('evidence',owner,rendered,record),dispose(){disposed=true;generation++;for(const stop of stops)stop();listeners.clear();}};
}
export function WikiPage({controller,drafts}){
 const s=useSyncExternalStore(controller.subscribe,controller.getSnapshot,controller.getSnapshot),[filter,setFilter]=useState('');
 useLayoutEffect(()=>setFilter(''),[s.ownerKey,s.lane]);
 if(s.ownerKey!==controller.currentKey())return h('p',null,'Chat ownership changed. Select a scope again.');
 const query=filter.toLocaleLowerCase(),records=s.records.filter(r=>[r.title,r.domain,r.topic].some(v=>String(v||'').toLocaleLowerCase().includes(query)));
 return h('section',{style:{padding:'1rem',maxWidth:960}},h('h1',null,'Approved memory wiki'),h('p',null,'Read-only human inspection, not model recall. Approval is a workflow state, not proof of truth. Refreshing may reveal sensitive approved titles and metadata. Full bodies require selecting a record; citation evidence requires a separate click.'),
  h('div',{style:rowStyle},...['private','project'].map(lane=>h('button',{key:lane,'aria-pressed':s.lane===lane,onClick:()=>controller.select(lane,s.ownerKey)},lane==='private'?'Current-chat private memory':'Consented project memory'))),
  h('p',null,s.lane?`Selected scope: ${s.lane}. Nothing is fetched until Refresh.`:'Select a scope; no catalog or bodies have been fetched.'),
  h('button',{disabled:!s.lane||s.busy,onClick:()=>controller.refresh(s.ownerKey,s)},s.busy?'Reading…':'Refresh approved index'),
  s.error&&h('p',{role:'alert'},s.error),s.snapshot&&h('div',null,h('label',null,'Filter loaded titles, domains and topics ',h('input',{value:filter,onChange:e=>setFilter(e.target.value)})),h('p',null,'This filter searches only loaded metadata, not every record or full text.'),
   h('ul',null,...records.map(r=>h('li',{key:r.id},h('button',{disabled:s.busy,onClick:()=>controller.open(r,s.ownerKey,s)},r.title||r.id),h('span',null,` · ${r.domain||'unclassified'} / ${r.topic||'no topic'}${r.sensitive?' · Sensitive':''}`)))),
   s.next&&h('button',{disabled:s.busy,onClick:()=>controller.more(s.ownerKey,s)},'Load next metadata page')),
  s.page&&h('article',null,h('h2',null,s.page.title),h('p',null,`Approved · revision ${s.page.revision}${s.page.sensitive?' · Sensitive: human inspection only':''}`),h('pre',{style:proseStyle},s.page.text),
   h('p',null,`${s.page.source_count??0} declared source references. Sources are not automatically opened or fetched.`),h('button',{disabled:s.busy,onClick:()=>controller.loadEvidence(s.page,s.ownerKey,s)},'Read bound citation evidence')),
  drafts&&s.lane&&h(DraftRecipePanel,{controller:drafts,selected:s.page}),
  s.evidence&&h('section',{'aria-label':'Bound citation evidence'},h('h2',null,'Declared citation evidence'),h('p',null,'Citation quotes and recorded digests only, not full source snapshots. A digest can establish captured-text identity, not factual truth. Links are inert text.'),h('pre',{style:proseStyle},JSON.stringify(s.evidence,null,2))));
}

export function createDraftController(host,wiki){
 const context=()=>{const w=wiki.getSnapshot();return{key:JSON.stringify([wiki.currentKey(),w.ownerKey,w.lane,w.snapshot,w.page?.id,w.page?.revision]),valid:w.ownerKey===wiki.currentKey()&&['private','project'].includes(w.lane),lane:w.lane,snapshot:w.snapshot,page:w.page,session:read(host?.state?.focusedSessionId)};};
 let identity=context(),generation=0,disposed=false;const listeners=new Set();
 const empty=()=>({contextKey:identity.key,busy:false,error:'',uncertain:false,preview:null,drafts:[],selected:null,saved:null,attemptedId:null});let state=empty();
 const publish=patch=>{state={...state,...patch};for(const fn of listeners)fn();};
 const sync=()=>{const next=context();if(next.key!==identity.key){identity=next;generation++;state=empty();for(const fn of listeners)fn();}return next;};const stop=wiki.subscribe(sync);
 const summaryValid=d=>d&&typeof d.id==='string'&&d.id.length>0&&d.id.length<=128&&typeof d.title==='string'&&new TextEncoder().encode(d.title).length<=120&&typeof d.created_at==='string'&&d.created_at.length<=128&&Array.isArray(d.record_ids)&&d.record_ids.length>=1&&d.record_ids.length<=4&&d.record_ids.every(v=>typeof v==='string'&&v.length>0&&v.length<=512)&&new Set(d.record_ids).size===d.record_ids.length&&typeof d.include_evidence==='boolean'&&typeof d.sensitive==='boolean';
 async function run(kind,payload,rendered=state,expected=context().key){const c=sync();if(disposed||!c.valid||c.key!==expected||rendered!==state||state.busy)return;
  if(kind==='preview'&&(!c.page||!c.snapshot||typeof payload.title!=='string'||new TextEncoder().encode(payload.title).length>120||!payload.title.trim()||typeof payload.include_evidence!=='boolean'))return;
  if(kind==='save'&&(state.uncertain||payload!==state.preview))return;
  const stamp=++generation,socket=host.getGateway?.();const valid=()=>!disposed&&sync().key===c.key&&generation===stamp&&(!host.getGateway||host.getGateway()===socket);
  const params=kind==='preview'?{record_ids:[c.page.id],expected_snapshot:c.snapshot,title:payload.title,include_evidence:payload.include_evidence}:kind==='save'?{preview_token:payload.preview_token,confirm:true}:kind==='get'?{draft_id:payload.id}:{};
  if(kind==='get'&&!state.drafts.some(d=>d===payload))return;
  publish({busy:true,error:'',preview:null,selected:null,saved:null,...(kind==='save'?{attemptedId:payload.draft_id}:{}),...(kind==='list'?{drafts:[]}: {})});
  try{const r=await host.request(`plugin.elm.draft.${c.lane}.${kind}`,{...params,session_id:c.session});if(!valid())return;
   if(kind==='preview'){if(!Number.isSafeInteger(r.expires_in_seconds)||r.expires_in_seconds<1||r.expires_in_seconds>300||r.lane!==c.lane||r.installable!==false||r.retains_body!==false||typeof r.draft_id!=='string'||!r.draft_id||r.draft_id.length>128||typeof r.preview_token!=='string'||!r.preview_token||r.preview_token.length>128||typeof r.markdown!=='string'||r.markdown.length>65536||!/^[a-f0-9]{64}$/.test(r.sha256)||typeof r.sensitive!=='boolean'||r.include_evidence!==payload.include_evidence||JSON.stringify(r.record_ids)!==JSON.stringify([c.page.id]))throw Error('preview');publish({preview:r,busy:false});}
   else if(kind==='save'){if(r.saved!==true||!summaryValid(r.draft)||r.draft.id!==payload.draft_id||JSON.stringify(r.draft.record_ids)!==JSON.stringify(payload.record_ids)||r.draft.include_evidence!==payload.include_evidence||r.draft.sensitive!==payload.sensitive)throw Error('save');publish({saved:r.draft,busy:false,uncertain:false});}
   else if(kind==='list'){if(r.lane!==c.lane||!Array.isArray(r.drafts)||r.drafts.length>16||!r.drafts.every(summaryValid))throw Error('list');publish({drafts:r.drafts,busy:false,uncertain:false});}
   else{if(!summaryValid(r.draft)||r.draft.id!==payload.id||typeof r.available!=='boolean'||(!r.available&&(Object.hasOwn(r,'markdown')||Object.hasOwn(r,'sha256')))||(r.available&&(typeof r.markdown!=='string'||r.markdown.length>65536||!/^[a-f0-9]{64}$/.test(r.sha256))))throw Error('get');publish({selected:r,busy:false});}
  }catch{if(valid())publish({busy:false,preview:null,selected:null,saved:null,uncertain:kind==='save'||state.uncertain,error:kind==='save'?'Save outcome is uncertain. Refresh saved recipes to reconcile; do not repeat the save.':'Draft is unavailable or its source changed. Review and request again explicitly.'});}
 }
 return{getSnapshot:()=>state,subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn);},currentKey:()=>context().key,preview:(title,include_evidence,rendered=state,key=context().key)=>run('preview',{title,include_evidence},rendered,key),save:(preview=state.preview,rendered=state,key=context().key)=>preview?run('save',preview,rendered,key):undefined,list:(rendered=state,key=context().key)=>run('list',{},rendered,key),get:(draft,rendered=state,key=context().key)=>run('get',draft,rendered,key),cancel(){publish({preview:null});},dispose(){disposed=true;generation++;stop();listeners.clear();}};
}
export function DraftRecipePanel({controller,selected}){
 const s=useSyncExternalStore(controller.subscribe,controller.getSnapshot,controller.getSnapshot),[title,setTitle]=useState(''),[evidence,setEvidence]=useState(false);
 useLayoutEffect(()=>{setTitle('');setEvidence(false);},[s.contextKey]);
 if(s.contextKey!==controller.currentKey())return h('p',null,'Source selection changed. Review again.');
 return h('section',{'aria-label':'Memory-based reference draft'},h('h2',null,'Reference draft from memory'),
 h('p',null,'Deterministic reference document, not AI-generated expertise or an installed skill. Saving keeps a recipe: selected IDs, title and source pins, not the generated body. Recipes are retained indefinitely; no purge control exists here.'),
 selected&&h('div',null,h('p',null,`Selected approved source: ${selected.title}${selected.sensitive?' · Sensitive':''}`),h('label',null,'Draft title ',h('input',{value:title,onChange:e=>setTitle(e.target.value)})),h('label',null,h('input',{type:'checkbox',checked:evidence,onChange:e=>setEvidence(e.target.checked)}),'Include declared citation evidence (may contain sensitive quotes; off by default)'),h('button',{disabled:s.busy||!title.trim(),onClick:()=>controller.preview(title,evidence,s,s.contextKey)},'Preview reference draft')),
 h('button',{disabled:s.busy,onClick:()=>controller.list(s,s.contextKey)},'Refresh saved recipes'),s.error&&h('p',{role:'alert'},s.error),
 s.preview&&h('div',null,h('h3',null,'Review before saving recipe'),h('p',null,s.preview.sensitive?'Contains sensitive material. Human preview only, not permission for model use or sharing.':'Human preview only; no installation or model call.'),h('pre',{style:proseStyle},s.preview.markdown),h('p',null,'Recipe ID: '+s.preview.draft_id),h('p',null,'Generated text SHA-256: '+s.preview.sha256),h('p',null,'Saving retains the recipe, not this body. Later reads regenerate only while the exact approved source pins remain valid.'),h('button',{disabled:s.busy||s.uncertain,onClick:()=>controller.save(s.preview,s,s.contextKey)},'Confirm saving recipe'),h('button',{disabled:s.busy,onClick:()=>controller.cancel()},'Cancel')),
 s.attemptedId&&h('p',null,'Last attempted recipe ID: '+s.attemptedId+'. Match this exact ID after refreshing saved recipes; do not infer success from similar titles.'),s.saved&&h('p',{role:'status'},'Recipe saved: '+s.saved.id),h('ul',null,...s.drafts.map(d=>h('li',{key:d.id},h('button',{disabled:s.busy,onClick:()=>controller.get(d,s,s.contextKey)},d.title+' · '+d.id+(d.sensitive?' · Sensitive':''))))),
 s.selected&&h('div',null,h('h3',null,s.selected.draft.title),s.selected.available?h('pre',{style:proseStyle},s.selected.markdown):h('p',null,'Unavailable: current approved source pins no longer permit regeneration. No retained body is shown.')));
}

const routingBlockerLabels={credential_route_dispatch_binding_unavailable:'Enrolled credentials are not connected to production dispatch.',production_pinned_dispatch_unavailable:'Production dispatch bound to the reviewed destination is unavailable.',explicit_egress_execution_unavailable:'An explicit, one-use external-processing consent and execution flow is unavailable.',provider_compatibility_unverified:'Provider compatibility has not been verified.',enforceable_cost_bound_unavailable:'An enforceable spending bound is unavailable.',search_result_contract_unavailable:'The model-assisted search result contract is not implemented.'};
export function createModelPreferencesController(host,epoch=()=>0){
 let identity=reviewIdentity(host,epoch),generation=0,disposed=false;const listeners=new Set(),stops=[];
 const empty=()=>({ownerKey:identity.key,status:null,preview:null,busy:false,error:identity.error,uncertain:false});let state=empty();
 const publish=p=>{state={...state,...p};for(const fn of listeners)fn();};
 const sync=()=>{const next=reviewIdentity(host,epoch);if(next.key!==identity.key){identity=next;generation++;state=empty();for(const fn of listeners)fn();}return next;};
 for(const atom of Object.values(host?.state||{}))if(atom?.subscribe)stops.push(atom.subscribe(sync));
 const selectionValid=v=>{if(v===null)return true;if(!v||typeof v!=='object'||Object.keys(v).length!==3||!['provider','model','endpoint'].every(k=>typeof v[k]==='string')||!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/.test(v.provider)||!/^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$/.test(v.model)||v.endpoint.length>256||/[^\x21-\x7e]|[\\%]/.test(v.endpoint))return false;try{const u=new URL(v.endpoint);return u.protocol==='https:'&&!u.username&&!u.password&&!u.search&&!u.hash&&!u.hostname.includes(':')&&['/v1/chat/completions','/chat/completions','/api/v1/chat/completions','/openai/v1/chat/completions'].includes(u.pathname);}catch{return false;}};
 const sameSelection=(a,b)=>a===null||b===null?a===b:selectionValid(a)&&selectionValid(b)&&a.provider===b.provider&&a.model===b.model&&new URL(a.endpoint).href===new URL(b.endpoint).href;
 const disabled=r=>r?.dispatch_supported===false&&r.external_egress_enabled===false;
 const readinessValid=r=>r.routing_readiness===undefined||(['search','organizer'].every(role=>{const v=r.routing_readiness?.[role];return v&&typeof v.selection_saved==='boolean'&&v.selection_saved===(r.roles?.[role]!==null)&&v.dispatch_supported===false&&Array.isArray(v.blockers)&&v.blockers.length<=6&&v.blockers.every(code=>Object.hasOwn(routingBlockerLabels,code));}));
 const statusValid=r=>disabled(r)&&readinessValid(r)&&r.scope==='current_chat'&&Number.isSafeInteger(r.revision)&&r.revision>=0&&typeof r.context_key==='string'&&/^[a-f0-9]{64}$/.test(r.context_key)&&typeof r.initialized==='boolean'&&typeof r.setup_required==='boolean'&&r.roles&&selectionValid(r.roles.search)&&selectionValid(r.roles.organizer);
 async function run(kind,payload,rendered=state,ownerKey=state.ownerKey){const c=sync();if(disposed||c.error||ownerKey!==c.key||rendered!==state||state.busy)return;
  if(kind==='preview'&&!selectionValid(payload.selection)){publish({error:'Use bounded provider/model identifiers and a credential-free HTTPS chat-completions endpoint; do not enter secrets.'});return;}
  if(kind==='preview'&&(!state.status||!state.status.initialized||state.status.setup_required||state.uncertain||!['search','organizer'].includes(payload.role)||!selectionValid(payload.selection)))return;
  if(kind==='apply'&&(!payload||payload!==state.preview||state.uncertain))return;
  const stamp=++generation,socket=host.getGateway?.(),oldStatus=state.status;const valid=()=>!disposed&&sync().key===c.key&&generation===stamp&&(!host.getGateway||host.getGateway()===socket);
  const params=kind==='status'?{}:kind==='preview'?{role:payload.role,selection:payload.selection,expected_revision:oldStatus.revision,expected_context:oldStatus.context_key}:{preview_token:payload.preview_token,confirm:true};
  publish({busy:true,error:'',preview:null,...(kind==='status'||kind==='apply'?{status:null}:{})});
  try{const r=await host.request('plugin.elm.model_preferences.'+kind,{...params,session_id:c.session});if(!valid())return;
   if(kind==='preview'){if(!disabled(r)||r.role!==payload.role||!selectionValid(r.selection)||!sameSelection(r.selection,payload.selection)||!selectionValid(r.previous_selection)||!sameSelection(r.previous_selection,oldStatus.roles[payload.role])||typeof r.preview_token!=='string'||!r.preview_token||r.preview_token.length>128||!Number.isSafeInteger(r.expires_in_seconds)||r.expires_in_seconds<1||r.expires_in_seconds>300)throw Error('preview');publish({preview:r,busy:false});}
   else{const status=kind==='status'?r:r.status;if(kind==='apply'&&(r.saved!==true||!statusValid(status)||!sameSelection(status.roles[payload.role],payload.selection)||status.revision<=oldStatus.revision)||!statusValid(status))throw Error('status');publish({status,busy:false,uncertain:false});}
  }catch{if(valid())publish({status:null,preview:null,busy:false,uncertain:kind==='apply'||state.uncertain,error:kind==='apply'?'Preference save outcome is uncertain. Refresh to reconcile; do not repeat the action.':'Preferences unavailable or changed. Refresh explicitly; no model request was made.'});}
 }
 return{getSnapshot:()=>state,subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn);},currentKey:()=>reviewIdentity(host,epoch).key,refresh:(s=state,key=state.ownerKey)=>run('status',null,s,key),preview:(role,selection,s=state,key=state.ownerKey)=>run('preview',{role,selection},s,key),apply:(p=state.preview,s=state,key=state.ownerKey)=>p?run('apply',p,s,key):undefined,cancel(){publish({preview:null});},dispose(){disposed=true;generation++;for(const stop of stops)stop();listeners.clear();}};
}
export function ModelPreferencesPage({controller}){
 const s=useSyncExternalStore(controller.subscribe,controller.getSnapshot,controller.getSnapshot),[role,setRole]=useState('search'),[provider,setProvider]=useState(''),[model,setModel]=useState(''),[endpoint,setEndpoint]=useState('');
 useLayoutEffect(()=>{setRole('search');setProvider('');setModel('');setEndpoint('');},[s.ownerKey]);
 if(s.ownerKey!==controller.currentKey())return h('p',null,'Chat ownership changed. Refresh preferences.');
 const status=s.status,blocked=s.busy||s.uncertain||!status?.initialized||status?.setup_required;
 return h('section',{style:{padding:'1rem',maxWidth:900}},h('h1',null,'Memory model preferences'),h('p',{role:'note'},'Routing unavailable. Search and organizer selections are saved intentions only, not active models. No execution, external processing, catalog lookup or connection test occurs. Saving is not consent to send memory.'),
 h('button',{disabled:s.busy,onClick:()=>controller.refresh(s,s.ownerKey)},s.busy?'Waiting…':'Refresh saved preferences'),s.error&&h('p',{role:'alert'},s.error),
 status&&h('div',null,h('p',null,'Scope: this chat only. Current chat model and existing recall/capture settings are unchanged.'),status.setup_required&&h('p',null,'First initialize private memory through its separate explicit setup action. This page does not create a store.'),
 h('h2',null,'Saved intentions'),...['search','organizer'].map(key=>h('div',{key},h('h3',null,key==='search'?'Memory search':'Memory organizer'),h('pre',{style:proseStyle},status.roles[key]?JSON.stringify(status.roles[key],null,2):'Not selected'),status.routing_readiness?.[key]?h('div',null,h('p',null,(status.routing_readiness[key].selection_saved?'Preference saved':'No preference saved')+' · execution unavailable'),h('ul',null,...status.routing_readiness[key].blockers.map(code=>h('li',{key:code},routingBlockerLabels[code])))):h('p',null,'Role-specific readiness is not reported by this host. Execution remains unavailable.'))),
 h('label',null,'Role ',h('select',{value:role,onChange:e=>setRole(e.target.value)},h('option',{value:'search'},'Memory search'),h('option',{value:'organizer'},'Memory organizer'))),
 ...[['Provider identifier',provider,setProvider],['Model identifier',model,setModel],['HTTPS chat-completions endpoint',endpoint,setEndpoint]].map(([label,value,set])=>h('label',{key:label,style:{display:'block'}},label,h('input',{value,onChange:e=>set(e.target.value),autoComplete:'off'}))),
 h('p',null,'No model calls or charges occur now. Future execution requires separately reviewed pricing, spending limits, recipient and exact data consent; no cost is estimated here.'),
 h('p',null,'Declared values are unverified: availability, credentials, capability, cost and suitability are not checked. Do not paste keys or secrets. No reasoning-effort support is assumed. Endpoint must be an allowed HTTPS chat-completions path without username, password, query or fragment.'),
 h('button',{disabled:blocked||!provider||!model||!endpoint,onClick:()=>controller.preview(role,{provider,model,endpoint},s,s.ownerKey)},'Review preference'),h('button',{disabled:blocked,onClick:()=>controller.preview(role,null,s,s.ownerKey)},'Review clearing selected role')),
 s.preview&&h('div',{'aria-label':'Preference confirmation'},h('h2',null,'Confirm '+s.preview.role+' preference'),h('h3',null,'Previous'),h('pre',{style:proseStyle},JSON.stringify(s.preview.previous_selection,null,2)),h('h3',null,'Proposed'),h('pre',{style:proseStyle},JSON.stringify(s.preview.selection,null,2)),h('p',null,'Save this intention locally for this chat. It does not configure a working route, authorize model calls, or enable a fallback.'),h('button',{disabled:s.busy||s.uncertain,onClick:()=>controller.apply(s.preview,s,s.ownerKey)},'Confirm saving preference'),h('button',{disabled:s.busy,onClick:()=>controller.cancel()},'Cancel')));
}

export default {
  id: 'elm', name: 'ELM private review', defaultEnabled: false,
  register(ctx) {
    const updates=createUpdateController(SDK.host,SDK.gatewayActivationEpoch||(()=>0));
    ctx.onDispose(()=>updates.dispose());
    ctx.registerSettingsPage?.({id:"automatic-updates",title:"ELM automatic updates",render:()=>h(UpdatePolicyPage,{controller:updates})});
    const wiki=createWikiController(SDK.host,SDK.gatewayActivationEpoch||(()=>0));
    const drafts=createDraftController(SDK.host,wiki);
    ctx.onDispose(()=>{drafts.dispose();wiki.dispose();});
    ctx.registerSettingsPage?.({id:"approved-wiki",title:"Approved memory wiki",render:()=>h(WikiPage,{controller:wiki,drafts})});
    const modelPreferences=createModelPreferencesController(SDK.host,SDK.gatewayActivationEpoch||(()=>0));
    ctx.onDispose(()=>modelPreferences.dispose());
    ctx.registerSettingsPage?.({id:"memory-model-preferences",title:"Memory model preferences",render:()=>h(ModelPreferencesPage,{controller:modelPreferences})});
    const lexicalSearch=createLexicalSearchController(SDK.host,SDK.gatewayActivationEpoch||(()=>0));
    ctx.onDispose(()=>lexicalSearch.dispose());
    ctx.registerSettingsPage?.({id:'scoped-lexical-search',title:'Scoped lexical search',render:()=>h(LexicalSearchPage,{controller:lexicalSearch})});
    registerRichPresentation(ctx);
    registerImportancePresentation(ctx);
    registerMessagePresentation(ctx);
    const controller = createReviewController(SDK.host, SDK.gatewayActivationEpoch || (() => 0));
    ctx.onDispose(() => controller.dispose());
    const render = () => h(ReviewPage, { controller });
    const folderPreferences=createChatFolderPreferences(ctx), folderSupported=typeof SDK.CHAT_FOLDERS_AREA==='string';
    const unbindFolders=bindNativeChatFolders(ctx,controller,folderPreferences,folderSupported);
    ctx.onDispose(()=>{unbindFolders();folderPreferences.dispose();});
    ctx.registerSettingsPage?.({id:'chat-folders',title:'Folders for chats',render:()=>h(ChatFoldersPage,{key:controller.currentKey(),controller,preferences:folderPreferences,supported:folderSupported})});
    const projectController = createReviewController(SDK.host, SDK.gatewayActivationEpoch || (() => 0), 'project');
    ctx.onDispose(() => projectController.dispose());
    const renderProject = () => h(ReviewPage, { controller: projectController, project: true });
    if (SDK.ROUTES_AREA && SDK.SIDEBAR_NAV_AREA) {
      ctx.register({ id: 'project-review-page', area: SDK.ROUTES_AREA, data: { path: '/elm-project-review' }, render: renderProject });
      ctx.register({ id: 'project-review-nav', area: SDK.SIDEBAR_NAV_AREA, data: { path: '/elm-project-review', label: 'Project memory', codicon: 'folder' } });
      ctx.register({ id: 'private-review-page', area: SDK.ROUTES_AREA, data: { path: '/elm-private-review' }, render });
      ctx.register({ id: 'private-review-nav', area: SDK.SIDEBAR_NAV_AREA,
        data: { path: '/elm-private-review', label: 'Private memory', codicon: 'book' } });
    } else if (typeof ctx.registerSettingsPage === 'function') {
      ctx.registerSettingsPage({ id: 'project-review', title: 'Project memory', icon: 'folder', render: renderProject });
      ctx.registerSettingsPage({ id: 'private-review', title: 'Private memory', icon: 'book', render });
    }
  },
};

/** Explicit user-invoked lookup; never automatic recall or model execution. */
export function createLexicalSearchController(host,epoch=()=>0){
 let identity=reviewIdentity(host,epoch),generation=0,disposed=false;
 const empty=()=>({ownerKey:identity.key,lane:null,query:'',result:null,packet:null,busy:false,error:identity.error});let state=empty();const listeners=new Set(),stops=[];
 const publish=patch=>{state={...state,...patch};for(const f of listeners)f()};
 const sync=()=>{const next=reviewIdentity(host,epoch);if(next.key!==identity.key){identity=next;generation++;state=empty();for(const f of listeners)f()}return next};
 for(const atom of Object.values(host?.state||{}))if(atom?.subscribe)stops.push(atom.subscribe(sync));
 function edit(patch,rendered){sync();if(disposed||state!==rendered||identity.error)return;generation++;publish({...patch,result:null,packet:null,busy:false,error:''})}
 return {getSnapshot:()=>state,subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn)},currentKey:()=>reviewIdentity(host,epoch).key,
  select(lane,rendered=state){if(['private','project'].includes(lane))edit({lane},rendered)},
  setQuery(query,rendered=state){if(typeof query==='string')edit({query},rendered)},
  async search(rendered=state){const owner=sync();if(disposed||owner.error||state!==rendered||state.busy||!state.lane)return;const query=state.query,lane=state.lane;if(!query||new TextEncoder().encode(query).length>512){publish({error:'Enter a query of 1–512 UTF-8 bytes. Punctuation-only queries are unsupported.',result:null,packet:null});return}
   const stamp=++generation,socket=host.getGateway?.();const valid=()=>!disposed&&sync().key===owner.key&&generation===stamp&&state.lane===lane&&state.query===query&&(!host.getGateway||host.getGateway()===socket);
   publish({busy:true,error:'',result:null,packet:null});
   try{const packet=await host.request(`plugin.elm.search.${lane}.query`,{session_id:owner.session,query});if(!valid())return;
    if(typeof packet!=='string'||new TextEncoder().encode(packet).length>131072)throw Error();const r=JSON.parse(packet);
    if(!exactKeys(r,['schema','lane','algorithm','tokenizer','token_limit','snapshot_key','status','eligible_count','matched_count','omitted_count','records'])||r.schema!==1||r.lane!==lane||r.algorithm!=='literal_overlap_v1'||r.tokenizer!=='o200k_base'||r.token_limit!==700||typeof r.snapshot_key!=='string'||!/^[a-f0-9]{64}$/.test(r.snapshot_key)||!['matched','partial','evidence_exceeds_budget','no_match'].includes(r.status)||!['eligible_count','matched_count','omitted_count'].every(k=>Number.isSafeInteger(r[k])&&r[k]>=0)||r.matched_count>r.eligible_count||r.omitted_count>r.matched_count||!Array.isArray(r.records)||r.records.length>r.matched_count||!r.records.every(row=>row&&typeof row.id==='string'&&typeof row.title==='string'&&typeof row.text==='string'&&row.state==='approved'&&row.sensitive===false&&Array.isArray(row.sources)))throw Error();
    if(r.omitted_count!==r.matched_count-r.records.length||(r.status==='matched'&&(!r.records.length||r.omitted_count))||(r.status==='partial'&&(!r.records.length||!r.omitted_count)))throw Error();
    if((r.status==='no_match'&&(r.records.length||r.matched_count))||(r.status==='evidence_exceeds_budget'&&(r.records.length||!r.matched_count)))throw Error();
    publish({busy:false,result:r,packet});
   }catch{if(valid())publish({busy:false,result:null,packet:null,error:'Search unavailable or rejected. Check current authorization, project consent and pinned tokenizer installation. No fallback, automatic download or retry; this is not a no-match result.'})}
  },dispose(){disposed=true;generation++;for(const stop of stops)stop();state=empty();listeners.clear()}
 };
}
export function LexicalSearchPage({controller}){
 const s=useSyncExternalStore(controller.subscribe,controller.getSnapshot,controller.getSnapshot);
 if(s.ownerKey!==controller.currentKey())return h('p',null,'Current chat changed. Search again in the intended scope.');
 const labels={matched:'Literal matches delivered.',partial:'Some matching records could not fit intact.',evidence_exceeds_budget:'Matching evidence exists, but no whole matching record fits this packet budget.',no_match:'No literal matches. This does not prove the answer is absent.'};
 return h('section',{style:sectionStyle},h('h2',null,'Scoped lexical search'),
  h('p',null,'Literal matches may not answer your question. There is no semantic abstention: irrelevant matches can still be returned when no answer exists. This is user-invoked search, not automatic model memory. Sensitive and ineligible records are excluded; project access requires existing consent.'),
  h('p',null,'Setup if unavailable: install the optional tiktoken==0.14.0 dependency and pinned official o200k_base vocabulary on the host; set the ELM plugin setting search_tokenizer_vocab to its absolute local file path, then reload the plugin. Missing or mismatched assets fail closed. The first search can be slower while the local tokenizer loads. This page does not install or download anything.'),
  button('Private',()=>controller.select('private',s),s.busy),button('Project',()=>controller.select('project',s),s.busy),h('p',null,'Selected scope: ',s.lane||'Choose explicitly'),
  h('label',null,'Literal query',h(Input,{value:s.query,onChange:e=>controller.setQuery(e.target.value,s)})),button('Search authorized records',()=>controller.search(s),s.busy||!s.lane),
  s.error&&h('p',{role:'alert'},s.error),
  s.result&&h('div',null,h('p',null,labels[s.result.status]),h('p',null,'Reference budget: 700 o200k_base tokens for the entire returned JSON memory packet. This is not provider framing, a full model prompt, billed tokens or a monetary limit.'),
   h('p',null,`Eligible: ${s.result.eligible_count}; literal matches: ${s.result.matched_count}; omitted: ${s.result.omitted_count}. Whole records and declared citations are not truncated. Dependency metadata does not guarantee all supporting dependency bodies are delivered.`),
   ...s.result.records.map(row=>h('article',{key:row.id,style:sectionStyle},h('h3',null,row.title),h('pre',{style:proseStyle},row.text),h('p',null,'Record ID: ',row.id),h('details',null,h('summary',null,'Declared citations · not independent verification'),h('pre',{style:proseStyle},JSON.stringify(row.sources,null,2))))),
   h('details',null,h('summary',null,'Exact returned packet · untrusted reference data'),h('pre',{style:proseStyle},s.packet))));
}
