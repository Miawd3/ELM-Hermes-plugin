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
