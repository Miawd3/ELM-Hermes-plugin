import { host, useValue, ToggleRow, gatewayActivationEpoch, useGatewayActivationEpoch, TRANSCRIPT_DIRECTIVE_AREA, SESSION_ROW_AREAS, pluginSettingsHref } from '@hermes/plugin-sdk'
import { createElement as h, useEffect, useRef, useState } from 'react'

// BEGIN INLINED RICH HELPERS
// Untrusted presentation data only. No authority, HTML, URL or executable content.
function richData(attrs) {
  if (!attrs || typeof attrs !== 'object' || Array.isArray(attrs)) return null
  if (Object.keys(attrs).some(k => !['kind','title','text'].includes(k))) return null
  const labels = {progress:'Progress', update:'Update', answer:'Answer', final:'Final', question:'Question'}
  if (!Object.hasOwn(labels, attrs.kind)) return null
  if (typeof attrs.text !== 'string' || !attrs.text.trim() || attrs.text.length > 1200) return null
  if (attrs.title !== undefined && (typeof attrs.title !== 'string' || attrs.title.length > 100)) return null
  if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test((attrs.title || '') + attrs.text)) return null
  return {label: labels[attrs.kind], title: attrs.title || '', text: attrs.text}
}
function visualPrefs(value) {
  return {rich:value?.rich === true, shortcut:value?.shortcut !== false, style:value?.style === 'plain' ? 'plain' : 'accent'}
}
function ownedRow(row, focused, owner, connection, profile) {
  return typeof row === 'string' && !!row && row === focused && !!connection &&
    !!owner && owner.connectionId === connection && owner.profile === profile
}
// END INLINED RICH HELPERS

// BEGIN INLINED IDENTITY HELPERS
// Pure owner fence. Profile names and session IDs alone are not an identity.
function usableIdentity(value) {
  return !!value && typeof value.sid === 'string' && !!value.sid && value.sid !== 'new' &&
    typeof value.connectionId === 'string' && !!value.connectionId && !!value.gateway &&
    value.gatewayState === 'open' && value.owner?.connectionId === value.connectionId &&
    value.owner?.profile === value.profile
}
function sameIdentity(expected, actual) {
  return usableIdentity(expected) && usableIdentity(actual) &&
    expected.sid === actual.sid && expected.profile === actual.profile &&
    expected.connectionId === actual.connectionId && expected.gateway === actual.gateway &&
    expected.epoch === actual.epoch
}
function parseStatus(reply) {
  const raw = typeof reply === 'string' ? reply : reply?.output
  if (typeof raw !== 'string') throw new Error('Settings unavailable. Use /elm status in this chat.')
  let value
  try { value = JSON.parse(raw) } catch { throw new Error('Settings unavailable. Refresh or check the Hermes connection.') }
  if (value && typeof value.error === 'string') {
    const error = new Error('Settings unavailable.')
    error.code = value.error
    throw error
  }
  if (!value || typeof value !== 'object' || value.error || !Number.isInteger(value.revision)) {
    throw new Error('Settings unavailable. Use /elm status in this chat.')
  }
  for (const key of ['enabled', 'capture', 'agent', 'organizer', 'user_scope']) {
    if (value[key] !== 0 && value[key] !== 1) throw new Error('Invalid settings response.')
  }
  if (value.project !== null && typeof value.project !== 'string') throw new Error('Invalid project.')
  return value
}
function accessPresentation(code) {
  if (code === 'exact_session_cli_grant_required') return {kind:'locked', title:'Memory needs permission for this chat', text:'This chat has no active grant. It may be new, expired or revoked. Saved memories have not been deleted.'}
  if (code === 'local_grant_expired_or_changed') return {kind:'locked', title:'Memory permission changed or expired', text:'Renew the exact-chat grant from the correct Hermes profile, then refresh.'}
  if (code === 'enable_this_chat_with_slash_elm_on' || code === 'off') return {kind:'locked', title:'Memory is off for this chat', text:'Saved data is kept. Unified Desktop chats need the local grant command to enable access again.'}
  if (code === 'local_session_required') return {kind:'unsupported', title:'This session type is not supported', text:'ELM currently supports explicitly enrolled local chats. Memory access is not enabled for this session.'}
  return {kind:'unavailable', title:'Memory settings unavailable', text:'Check the Hermes connection and refresh. This is not a confirmed permission problem.'}
}
// END INLINED IDENTITY HELPERS

// BEGIN INLINED MANAGER HELPERS
// Pure helpers are inlined in the shipped ESM file (no relative imports).
function managerCommand(payload) {
  // POSIX shlex quoting, not JSON string quoting: preserves newlines and slashes.
  return "elm manager '" + JSON.stringify(payload).replaceAll("'", "'\\''") + "'"
}
function memoryDestination(kind, snapshot) {
  if (kind === 'user' && snapshot.user_scope === 1) return 'Shared user memory in this profile'
  if (kind === 'project' && snapshot.project) return 'Project: ' + snapshot.project
  return 'This chat only'
}
function parseManager(reply, listing=false) {
  const raw = typeof reply === 'string' ? reply : reply?.output
  let value
  try { value = JSON.parse(raw) } catch { throw new Error('Unexpected response. Refresh before trying again.') }
  if (!value || typeof value !== 'object' || value.error) throw new Error('Memory access or data changed. Refresh; renew this chat’s grant if needed.')
  if (listing && (!/^[a-f0-9]{32}$/.test(value.store_identity) || !Number.isInteger(value.revision) || !Array.isArray(value.records) || value.records.length > 12 || !['approved','pending','trash'].includes(value.status) || !Number.isInteger(value.offset) || ![0,1].includes(value.user_scope) || (value.project !== null && typeof value.project !== 'string') || (value.next_offset !== null && !Number.isInteger(value.next_offset)) || value.records.some(r => !r || !/^[a-f0-9]{64}$/.test(r.version) || !/^[a-f0-9]{32}$/.test(r.id) || !['user','project','reference','skill'].includes(r.kind) || typeof r.text !== 'string' || typeof r.destination !== 'string' || !Array.isArray(r.tags) || r.tags.some(t=>typeof t !== 'string')))) throw new Error('Unexpected memory list. Refresh before trying again.')
  return value
}
// END INLINED MANAGER HELPERS

const buttonStyle = { border: '1px solid var(--ui-border)', borderRadius: 6, padding: '6px 12px' }
const inputStyle = { ...buttonStyle, background: 'var(--ui-bg)', color: 'var(--ui-text)', width: '100%' }

function Settings() {
  const sid = useValue(host.state.focusedSessionId)
  const owner = useValue(host.state.focusedSessionOwner)
  const connectionId = useValue(host.state.connectionId)
  const gatewayState = useValue(host.state.gateway)
  const profile = useValue(host.state.profile)
  const [state, setState] = useState(null)
  const [stateOwner, setStateOwner] = useState(null)
  const [project, setProject] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [access, setAccess] = useState(null)
  const generation = useRef(0)
  const gateway = host.getGateway()
  const epoch = useGatewayActivationEpoch()
  const identity = { sid, profile, connectionId, gateway, gatewayState, owner, epoch }
  const valid = usableIdentity(identity)
  const visibleState = sameIdentity(stateOwner, identity) ? state : null
  const visibleAccess = sameIdentity(stateOwner, identity) ? access : null
  const current = () => sameIdentity(identity, {
    sid: host.state.focusedSessionId.get(), profile: host.state.profile.get(),
    connectionId: host.state.connectionId.get(), gateway: host.getGateway(),
    gatewayState: host.state.gateway.get(), owner: host.state.focusedSessionOwner.get(),
    epoch: gatewayActivationEpoch()
  })

  async function run(command = null) {
    if (!valid || !current()) return
    const token = ++generation.current
    setBusy(true); setError(''); setAccess(null)
    try {
      if (command) {
        // This is the public, authenticated slash-command route, not a direct database RPC.
        const reply = await gateway.request('slash.exec', { session_id: sid, profile, command: `elm ${command}` })
        const output = typeof reply === 'string' ? reply : reply?.output
        if (typeof output !== 'string' || output.includes('"error":')) throw new Error('Change failed. Check /elm status in this chat.')
      }
      if (!current() || token !== generation.current) return
      if (command === 'off') {
        setStateOwner(identity); setState(null); setAccess(accessPresentation('off')); setError('Memory is off for this chat. Saved data is kept.'); return
      }
      const reply = await gateway.request('slash.exec', { session_id: sid, profile, command: 'elm status' })
      if (!current() || token !== generation.current) return
      const next = parseStatus(reply)
      setStateOwner(identity); setState(next); setAccess(null); setProject(next.project || '')
    } catch (e) {
      if (current() && token === generation.current) { setStateOwner(identity); setState(null); setAccess(accessPresentation(e?.code)); setError('') }
    } finally {
      if (current() && token === generation.current) setBusy(false)
    }
  }

  useEffect(() => {
    ++generation.current; setState(null); setAccess(null); setProject(''); setError(''); setBusy(false)
    if (valid) run()
    return () => { ++generation.current }
  }, [sid, profile, connectionId, gatewayState, gateway, owner?.connectionId, owner?.profile, epoch])

  const toggle = (key, label, description, command) => h(ToggleRow, {
    key, label, description, checked: !!visibleState?.[key], disabled: busy || !visibleState || (visibleState.permissions_via_cli && (key !== 'enabled' || !visibleState.enabled)),
    onChange: on => { if (!busy && visibleState) run(`${command ? command + ' ' : ''}${on ? 'on' : 'off'}`) }
  })

  return h('section', { style: { display: 'grid', gap: 16, maxWidth: 720, padding: 16 } },
    h('h2', { style: { fontSize: 18, fontWeight: 600 } }, 'ELM · focused chat'),
    h(VisualSettings),
    h('p', null, valid ? 'Settings apply to the focused local chat, not every chat.' : 'Focus a saved local chat on the active connection to configure ELM.'),
    sameIdentity(stateOwner, identity) && error && h('p', { role: 'status' }, error),
    visibleAccess && h(AccessSetup, { access: visibleAccess, sid, profile }),
    visibleState?.permissions_via_cli && h('p', { style: { fontSize: 12, opacity: .75 } }, 'Permissions are set with the local grant command for this exact chat. Any authenticated client of this chat shares access. You can turn memory off here.'),
    valid && h('button', { style: buttonStyle, disabled: busy, onClick: () => run() }, busy ? 'Loading…' : 'Refresh'),
    visibleState?.enabled === 1 && h(MemoryManager,{key:[sid,profile,connectionId,epoch,visibleState.revision].join('|'),identity,current}),
    visibleState && h('div', { style: { display: 'grid', gap: 12 } },
      toggle('enabled', 'Memory', 'Approved recall joins your conversation and may reach its model provider.', ''),
      toggle('user_scope', 'Shared user facts', 'Use user facts from other local chats you explicitly enrolled.', 'user'),
      h('label', null, 'Project', h('input', { style: inputStyle, value: project, maxLength: 120, disabled: busy || visibleState.permissions_via_cli,
        placeholder: 'No shared project', onChange: e => setProject(e.target.value) })),
      h('button', { style: buttonStyle, disabled: busy || visibleState.permissions_via_cli, onClick: () => run(`project ${project.trim() ? JSON.stringify(project.trim()) : 'off'}`) }, 'Apply project'),
      toggle('capture', 'Save conversation sources', 'Store completed turns locally as plain text. Avoid secrets.', 'capture'),
      toggle('agent', 'Search agent', 'Explicit agent searches send the query to your selected model. Fees may apply.', 'agent'),
      toggle('organizer', 'Organizer', 'Explicit /elm organize sends the selected source for draft extraction. Review required; fees may apply.', 'organizer'),
      h('p', null, 'Models: Settings → Models → Auxiliary → ELM Search / ELM Organizer.'),
      h('p', null, 'Review: /elm pending · /elm approve <id>. Updates: use Hermes’s plugin manager.')
    )
  )
}

function MemoryManager({identity, current}) {
  const [snapshot,setSnapshot] = useState(null)
  const [error,setError] = useState('')
  const [busy,setBusy] = useState(false)
  const [kind,setKind] = useState('reference')
  const [text,setText] = useState('')
  const [confirm,setConfirm] = useState(null)
  const alive=useRef(true), flight=useRef(false), generation=useRef(0)
  const valid=()=>alive.current && current()
  async function load(status='approved',offset=0,mutation=null) {
    if (!valid() || flight.current) return
    setBusy(true);setError('');setConfirm(null)
    const token=++generation.current;flight.current=token
    const active=()=>valid() && token===generation.current
    try {
      if (mutation) {
        parseManager(await identity.gateway.request('slash.exec',{session_id:identity.sid,profile:identity.profile,command:managerCommand(mutation)}))
        if (!active()) return
        if (mutation.action==='save') setText('')
      }
      const reply=await identity.gateway.request('slash.exec',{session_id:identity.sid,profile:identity.profile,command:managerCommand({action:'list',status,offset})})
      if (!active()) return
      const next=parseManager(reply,true)
      if(next.status!==status || next.offset!==offset) throw new Error('Unexpected memory page. Refresh.')
      setSnapshot(next)
    } catch(e) {
      if(active()){setSnapshot(null);setError(e.message)}
    } finally {if(flight.current===token)flight.current=false;if(active())setBusy(false)}
  }
  useEffect(()=>{alive.current=true;load();return()=>{alive.current=false;flight.current=false;++generation.current}},[])
  const mutate=(action,record)=>{if(snapshot)load(snapshot.status,snapshot.offset,{action,id:record.id,version:record.version,revision:snapshot.revision,store_identity:snapshot.store_identity})}
  return h('section',{style:{display:'grid',gap:12,border:'1px solid var(--ui-border)',borderRadius:8,padding:16}},
    h('h3',null,'Memory in this chat'),
    h('p',null,'Shows this chat’s records and explicitly shared memory available to it. Kind describes the information; destination controls who can recall it.'),
    error && h('p',{role:'alert'},error),
    h('button',{style:buttonStyle,disabled:busy,onClick:()=>load(snapshot?.status||'approved',snapshot?.offset||0)},busy?'Loading…':'Refresh memory'),
    snapshot && h('div',{style:{display:'grid',gap:12}},
      h('p',null,'Available destinations: this chat',snapshot.user_scope===1?' · shared user memory in this profile':'',snapshot.project?' · project: '+snapshot.project:''),
      h('p',null,'Shared records can be reviewed or changed by other enrolled chats. No permissions are changed here. Approved records may be sent to your conversation’s model during recall.'),
      h('fieldset',{disabled:busy,style:{display:'grid',gap:8}},h('legend',null,'Save a memory'),
        h('label',null,'Kind ',h('select',{value:kind,onChange:e=>setKind(e.target.value)},...['reference','user','project','skill'].map(k=>h('option',{key:k,value:k},k==='user'?'User fact':k[0].toUpperCase()+k.slice(1))))),
        h('p',null,'Will save to: ',h('strong',null,memoryDestination(kind,snapshot))),
        h('textarea',{style:{...inputStyle,minHeight:90},value:text,maxLength:8000,'aria-label':'Memory text',placeholder:'Write the fact or note to remember. Avoid secrets.',onChange:e=>setText(e.target.value)}),
        h('small',null,'Saved immediately as approved. UTF-8 limit: 8,000 bytes. Skill notes are memory records, not installed executable skills.'),
        h('button',{style:buttonStyle,disabled:!text.trim()||new TextEncoder().encode(text).length>8000,onClick:()=>load('approved',0,{action:'save',revision:snapshot.revision,store_identity:snapshot.store_identity,kind,text})},'Save approved memory')),
      h('div',{role:'group','aria-label':'Record status'},...['approved','pending','trash'].map(status=>h('button',{key:status,style:buttonStyle,disabled:busy,'aria-pressed':snapshot.status===status,onClick:()=>load(status,0)},status==='pending'?'Needs review':status[0].toUpperCase()+status.slice(1)))),
      snapshot.records.length===0 && h('p',null,'No records on this page.'),
      ...snapshot.records.map(record=>h('article',{key:record.id,style:{border:'1px solid var(--ui-border)',borderRadius:6,padding:12,display:'grid',gap:8}},
        h('strong',null,record.kind+' · '+record.destination),
        h('p',{style:{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}},record.text),
        record.tags.length>0 && h('small',null,'Tags: '+record.tags.join(', ')),
        record.source_id && h('small',null,'Source-linked record'),
        snapshot.status==='pending' && h('button',{style:buttonStyle,disabled:busy,onClick:()=>mutate('approve',record)},'Approve for recall'),
        snapshot.status==='trash' ? h('button',{style:buttonStyle,disabled:busy,onClick:()=>mutate('restore',record)},'Restore to review') :
          confirm===record.id ? h('div',null,h('p',null,'Move this record to Trash? This affects its shared destination too. Existing copies are not removed.'),h('button',{style:buttonStyle,disabled:busy,onClick:()=>mutate('trash',record)},'Move to Trash'),h('button',{style:buttonStyle,disabled:busy,onClick:()=>setConfirm(null)},'Cancel')) : h('button',{style:buttonStyle,disabled:busy,onClick:()=>setConfirm(record.id)},'Trash…')
      )),
      h('div',null,h('button',{style:buttonStyle,disabled:busy||snapshot.offset===0,onClick:()=>load(snapshot.status,Math.max(0,snapshot.offset-12))},'Previous'),h('span',null,' Page '+(Math.floor(snapshot.offset/12)+1)+' '),h('button',{style:buttonStyle,disabled:busy||snapshot.next_offset===null,onClick:()=>load(snapshot.status,snapshot.next_offset)},'Next')),
      h('small',null,'Trash is recoverable; restore returns records to review. Existing model context and copied notes are not erased. Concurrent changes may shift pages; refresh to update.')
    )
  )
}

function AccessSetup({access, sid, profile}) {
  const locked = access.kind === 'locked'
  return h('div', {style:{display:'grid',gap:12,border:'1px solid var(--ui-border)',borderRadius:8,padding:16}},
    h('div', {role:'status'}, h('strong',null,access.title), h('p',null,access.text)),
    locked && h('div',null,
      h('p',null,'1. Open a terminal using this chat’s actual Hermes profile and Hermes Python environment.'),
      h('p',null,'2. Follow the setup guide: verify --show-home, then grant this exact session with --expect-home. Do not use the parent directory of a named profile.'),
      h('p',null,'3. Return here and select Refresh.'),
      h('p',null,'Selected profile label: ',h('code',null,typeof profile === 'string' ? profile : '(not available)')),
      h('p',null,'Focused runtime session ID: ',h('code',{style:{overflowWrap:'anywhere'}},sid)),
      h('small',null,'Verify the full ID with Hermes sessions list. A profile label is not a filesystem path. Grants expire after 24 hours by default; authenticated clients of this same session share access.'),
      h('p',null,h('a',{href:'https://github.com/Miawd3/ELM-Hermes-plugin/blob/main/stock-plugin/README.md',target:'_blank',rel:'noopener noreferrer'},'Open setup guide'))),
    locked && h('fieldset',{disabled:true,style:{display:'grid',gap:6,border:'1px solid var(--ui-border)',padding:12}},
      h('legend',null,'Memory controls · locked until access is granted'),
      ...['Memory recall','Shared user facts','Project memory','Conversation capture','Search agent','Organizer'].map(label=>h('label',{key:label},h('input',{type:'checkbox',disabled:true,checked:false,readOnly:true}), ' ',label)),
      h('small',null,'These are available features, not the saved settings for this chat. Sharing and model access require explicit grant options; they are not enabled automatically.')),
    h('p',{style:{fontSize:12,opacity:.75}},'Not included in this plugin: native chat folders, timeline markers and whole-message bubble styling. Inline answer cards above are a separate display feature.')
  )
}

let visualStorage = null
const visualListeners = new Set()
function readVisual() { try { return visualPrefs(visualStorage?.get('visual-v1', {})) } catch { return visualPrefs({}) } }
function useVisual() {
  const [prefs, setPrefs] = useState(readVisual)
  useEffect(() => { const changed = () => setPrefs(readVisual()); visualListeners.add(changed); return () => visualListeners.delete(changed) }, [])
  function change(patch) {
    const next = visualPrefs({...readVisual(), ...patch})
    try { visualStorage?.set('visual-v1', next); for (const notify of visualListeners) notify() } catch { /* Keep previous UI if saving fails. */ }
  }
  return [prefs, change]
}
function VisualSettings() {
  const [prefs, change] = useVisual()
  return h('div', {style:{display:'grid',gap:10}},
    h(ToggleRow,{label:'Inline answer cards',description:'App-wide display preference. Model labels are not proof of completion.',checked:prefs.rich,onChange:rich=>change({rich})}),
    prefs.rich && h('div',null,h('small',null,'Display example, not a conversation result'),h(RichAnswer,{attrs:{kind:'question',title:'Choose a direction',text:'Which approach should we explore?'},source:'',streaming:false})),
    h('label',null,'Card style ',h('select',{value:prefs.style,onChange:e=>change({style:e.target.value})},h('option',{value:'accent'},'Accent'),h('option',{value:'plain'},'Plain'))),
    h(ToggleRow,{label:'Chat settings shortcut',description:'ELM shortcut on the focused chat. Not a memory-status indicator.',checked:prefs.shortcut,onChange:shortcut=>change({shortcut})}))
}
function RichAnswer({attrs,source,streaming}) {
  const [prefs] = useVisual()
  const data = richData(attrs)
  if (!prefs.rich || !data) return h('span',null,typeof source === 'string' ? source : '')
  return h('span',{style:{display:'block',border:'1px solid currentColor',borderLeft:prefs.style==='accent'?'3px solid currentColor':'1px solid currentColor',borderRadius:6,padding:12,margin:'8px 0'},'aria-label':'Model-provided '+data.label},
    h('strong',null,data.label), streaming && h('span',null,' · still streaming'),
    h('span',{style:{display:'block',fontSize:11,opacity:.65}},'Model-provided label'),
    data.title && h('strong',{style:{display:'block',marginTop:6}},data.title),
    h('span',{style:{display:'block',whiteSpace:'pre-wrap',overflowWrap:'anywhere'}},data.text))
}
function ElmRowShortcut({sessionId}) {
  const [prefs] = useVisual()
  const focused=useValue(host.state.focusedStoredSessionId)
  const owner=useValue(host.state.focusedSessionOwner)
  const connection=useValue(host.state.connectionId)
  const profile=useValue(host.state.profile)
  if (!prefs.shortcut || !ownedRow(sessionId,focused,owner,connection,profile)) return null
  return h('button',{title:'Open ELM settings for focused chat; not memory status',style:{fontSize:10,padding:'1px 4px'},onClick:e=>{
    e.stopPropagation()
    if (ownedRow(sessionId,host.state.focusedStoredSessionId.get(),host.state.focusedSessionOwner.get(),host.state.connectionId.get(),host.state.profile.get())) host.navigate(pluginSettingsHref('elm:settings'))
  }},'ELM')
}

export default {
  id: 'elm', name: 'ELM',
  register(ctx) {
    visualStorage = ctx.storage
    ctx.register({id:'rich-answer',area:TRANSCRIPT_DIRECTIVE_AREA,data:{name:'elm-answer',render:props=>h(RichAnswer,props)}})
    ctx.register({id:'session-settings',area:SESSION_ROW_AREAS.trailing,data:{render:props=>h(ElmRowShortcut,props)}})
    ctx.registerSettingsPage({ id: 'settings', title: 'ELM', icon: 'database', render: () => h(Settings) })
  }
}
