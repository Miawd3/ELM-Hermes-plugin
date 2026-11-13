// Pure owner fence. Profile names and session IDs alone are not an identity.
export function usableIdentity(value) {
  return !!value && typeof value.sid === 'string' && !!value.sid && value.sid !== 'new' &&
    typeof value.connectionId === 'string' && !!value.connectionId && !!value.gateway &&
    value.gatewayState === 'open' && value.owner?.connectionId === value.connectionId &&
    value.owner?.profile === value.profile
}
export function sameIdentity(expected, actual) {
  return usableIdentity(expected) && usableIdentity(actual) &&
    expected.sid === actual.sid && expected.profile === actual.profile &&
    expected.connectionId === actual.connectionId && expected.gateway === actual.gateway &&
    expected.epoch === actual.epoch
}
export function parseStatus(reply) {
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
export function accessPresentation(code) {
  if (code === 'exact_session_cli_grant_required') return {kind:'locked', title:'Memory needs permission for this chat', text:'This chat has no active grant. It may be new, expired or revoked. Saved memories have not been deleted.'}
  if (code === 'local_grant_expired_or_changed') return {kind:'locked', title:'Memory permission changed or expired', text:'Renew the exact-chat grant from the correct Hermes profile, then refresh.'}
  if (code === 'enable_this_chat_with_slash_elm_on' || code === 'off') return {kind:'locked', title:'Memory is off for this chat', text:'Saved data is kept. Unified Desktop chats need the local grant command to enable access again.'}
  if (code === 'local_session_required') return {kind:'unsupported', title:'This session type is not supported', text:'ELM currently supports explicitly enrolled local chats. Memory access is not enabled for this session.'}
  return {kind:'unavailable', title:'Memory settings unavailable', text:'Check the Hermes connection and refresh. This is not a confirmed permission problem.'}
}
