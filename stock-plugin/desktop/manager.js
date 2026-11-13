// Pure helpers are inlined in the shipped ESM file (no relative imports).
export function managerCommand(payload) {
  // POSIX shlex quoting, not JSON string quoting: preserves newlines and slashes.
  return "elm manager '" + JSON.stringify(payload).replaceAll("'", "'\\''") + "'"
}
export function memoryDestination(kind, snapshot) {
  if (kind === 'user' && snapshot.user_scope === 1) return 'Shared user memory in this profile'
  if (kind === 'project' && snapshot.project) return 'Project: ' + snapshot.project
  return 'This chat only'
}
export function parseManager(reply, listing=false) {
  const raw = typeof reply === 'string' ? reply : reply?.output
  let value
  try { value = JSON.parse(raw) } catch { throw new Error('Unexpected response. Refresh before trying again.') }
  if (!value || typeof value !== 'object' || value.error) throw new Error('Memory access or data changed. Refresh; renew this chat’s grant if needed.')
  if (listing && (!/^[a-f0-9]{32}$/.test(value.store_identity) || !Number.isInteger(value.revision) || !Array.isArray(value.records) || value.records.length > 12 || !['approved','pending','trash'].includes(value.status) || !Number.isInteger(value.offset) || ![0,1].includes(value.user_scope) || (value.project !== null && typeof value.project !== 'string') || (value.next_offset !== null && !Number.isInteger(value.next_offset)) || value.records.some(r => !r || !/^[a-f0-9]{64}$/.test(r.version) || !/^[a-f0-9]{32}$/.test(r.id) || !['user','project','reference','skill'].includes(r.kind) || typeof r.text !== 'string' || typeof r.destination !== 'string' || !Array.isArray(r.tags) || r.tags.some(t=>typeof t !== 'string')))) throw new Error('Unexpected memory list. Refresh before trying again.')
  return value
}
