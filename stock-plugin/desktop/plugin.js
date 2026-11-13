import { host, useValue, ToggleRow, gatewayActivationEpoch, useGatewayActivationEpoch } from '@hermes/plugin-sdk'
import { createElement as h, useEffect, useRef, useState } from 'react'

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
  const value = JSON.parse(raw)
  if (!value || typeof value !== 'object' || value.error || !Number.isInteger(value.revision)) {
    throw new Error('Settings unavailable. Use /elm status in this chat.')
  }
  for (const key of ['enabled', 'capture', 'agent', 'organizer', 'user_scope']) {
    if (value[key] !== 0 && value[key] !== 1) throw new Error('Invalid settings response.')
  }
  if (value.project !== null && typeof value.project !== 'string') throw new Error('Invalid project.')
  return value
}
// END INLINED IDENTITY HELPERS

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
  const generation = useRef(0)
  const gateway = host.getGateway()
  const epoch = useGatewayActivationEpoch()
  const identity = { sid, profile, connectionId, gateway, gatewayState, owner, epoch }
  const valid = usableIdentity(identity)
  const visibleState = sameIdentity(stateOwner, identity) ? state : null
  const current = () => sameIdentity(identity, {
    sid: host.state.focusedSessionId.get(), profile: host.state.profile.get(),
    connectionId: host.state.connectionId.get(), gateway: host.getGateway(),
    gatewayState: host.state.gateway.get(), owner: host.state.focusedSessionOwner.get(),
    epoch: gatewayActivationEpoch()
  })

  async function run(command = null) {
    if (!valid || !current()) return
    const token = ++generation.current
    setBusy(true); setError('')
    try {
      if (command) {
        // This is the public, authenticated slash-command route, not a direct database RPC.
        const reply = await gateway.request('slash.exec', { session_id: sid, profile, command: `elm ${command}` })
        const output = typeof reply === 'string' ? reply : reply?.output
        if (typeof output !== 'string' || output.includes('"error":')) throw new Error('Change failed. Check /elm status in this chat.')
      }
      if (!current() || token !== generation.current) return
      if (command === 'off') {
        setState(null); setError('Memory is off for this chat. Saved data is kept. Use the local grant command to renew unified-session access.'); return
      }
      const reply = await gateway.request('slash.exec', { session_id: sid, profile, command: 'elm status' })
      if (!current() || token !== generation.current) return
      const next = parseStatus(reply)
      setStateOwner(identity); setState(next); setProject(next.project || '')
    } catch (e) {
      if (current() && token === generation.current) { setState(null); setError(e?.message || 'Settings unavailable.') }
    } finally {
      if (current() && token === generation.current) setBusy(false)
    }
  }

  useEffect(() => {
    ++generation.current; setState(null); setProject(''); setError(''); setBusy(false)
    if (valid) run()
    return () => { ++generation.current }
  }, [sid, profile, connectionId, gatewayState, gateway, owner?.connectionId, owner?.profile, epoch])

  const toggle = (key, label, description, command) => h(ToggleRow, {
    key, label, description, checked: !!visibleState?.[key], disabled: busy || !visibleState || (visibleState.permissions_via_cli && (key !== 'enabled' || !visibleState.enabled)),
    onChange: on => { if (!busy && visibleState) run(`${command ? command + ' ' : ''}${on ? 'on' : 'off'}`) }
  })

  return h('section', { style: { display: 'grid', gap: 16, maxWidth: 720, padding: 16 } },
    h('h2', { style: { fontSize: 18, fontWeight: 600 } }, 'ELM · focused chat'),
    h('p', null, valid ? 'Settings apply to the focused local chat, not every chat.' : 'Focus a saved local chat on the active connection to configure ELM.'),
    error && h('p', { role: 'alert' }, error),
    visibleState?.permissions_via_cli && h('p', { style: { fontSize: 12, opacity: .75 } }, 'Permissions are set with the local grant command for this exact chat. Any authenticated client of this chat shares access. You can turn memory off here.'),
    valid && h('button', { style: buttonStyle, disabled: busy, onClick: () => run() }, busy ? 'Loading…' : 'Refresh'),
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

export default {
  id: 'elm', name: 'ELM',
  register(ctx) {
    ctx.registerSettingsPage({ id: 'settings', title: 'ELM', icon: 'database', render: () => h(Settings) })
  }
}
