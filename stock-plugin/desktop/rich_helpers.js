// Untrusted presentation data only. No authority, HTML, URL or executable content.
export function richData(attrs) {
  if (!attrs || typeof attrs !== 'object' || Array.isArray(attrs)) return null
  if (Object.keys(attrs).some(k => !['kind','title','text'].includes(k))) return null
  const labels = {progress:'Progress', update:'Update', answer:'Answer', final:'Final', question:'Question'}
  if (!Object.hasOwn(labels, attrs.kind)) return null
  if (typeof attrs.text !== 'string' || !attrs.text.trim() || attrs.text.length > 1200) return null
  if (attrs.title !== undefined && (typeof attrs.title !== 'string' || attrs.title.length > 100)) return null
  if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test((attrs.title || '') + attrs.text)) return null
  return {label: labels[attrs.kind], title: attrs.title || '', text: attrs.text}
}
export function visualPrefs(value) {
  return {rich:value?.rich === true, shortcut:value?.shortcut !== false, style:value?.style === 'plain' ? 'plain' : 'accent'}
}
export function ownedRow(row, focused, owner, connection, profile) {
  return typeof row === 'string' && !!row && row === focused && !!connection &&
    !!owner && owner.connectionId === connection && owner.profile === profile
}
