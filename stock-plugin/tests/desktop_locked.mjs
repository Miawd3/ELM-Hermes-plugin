import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import vm from 'node:vm'
import {parseStatus,accessPresentation} from '../desktop/identity.js'
for (const code of ['exact_session_cli_grant_required','local_grant_expired_or_changed','enable_this_chat_with_slash_elm_on']) {
  let caught; try {parseStatus({output:JSON.stringify({error:code,private:'SECRET'})})} catch(e) {caught=e}
  assert.equal(caught.code,code)
  assert.equal(accessPresentation(caught.code).kind,'locked')
  assert.ok(!JSON.stringify(accessPresentation(caught.code)).includes('SECRET'))
}
assert.equal(accessPresentation('storage_unavailable').kind,'unavailable')
assert.equal(accessPresentation('local_session_required').kind,'unsupported')
assert.equal(accessPresentation('<script>SECRET</script>').kind,'unavailable')
assert.equal(accessPresentation('off').kind,'locked')
assert.throws(()=>parseStatus({output:'<html>SECRET</html>'}), /Settings unavailable/)
const src=readFileSync(new URL('../desktop/plugin.js',import.meta.url),'utf8')
const setup=src.slice(src.indexOf('function AccessSetup'),src.indexOf('\nlet visualStorage'))
const ctx={h:(type,props,...children)=>({type,props,children})};vm.createContext(ctx);vm.runInContext(setup+';this.render=AccessSetup',ctx)
let tree=ctx.render({access:accessPresentation('exact_session_cli_grant_required'),sid:'s-test',profile:'test-profile'})
const text=JSON.stringify(tree)
for(const label of ['--show-home','--expect-home','24 hours','same session','not the saved settings','native chat folders','s-test','test-profile'])assert.ok(text.includes(label),label)
const find=(x,p)=>x && typeof x==='object' ? [ ...(p(x)?[x]:[]), ...Object.values(x).flatMap(y=>Array.isArray(y)?y.flatMap(z=>find(z,p)):find(y,p))] : []
assert.equal(find(tree,x=>x.type==='input').length,6)
assert.ok(find(tree,x=>x.type==='input').every(x=>x.props.disabled && x.props.checked===false))
assert.equal(find(tree,x=>x.props?.onClick||x.props?.onChange).length,0)
tree=ctx.render({access:accessPresentation('storage_unavailable'),sid:'s-test',profile:'test-profile'})
assert.equal(find(tree,x=>x.type==='fieldset').length,0)
assert.ok(!JSON.stringify(tree).includes('s-test'))
assert.ok(src.includes('const visibleAccess = sameIdentity(stateOwner, identity) ? access : null'))
assert.ok(src.includes("setState(null); setAccess(null); setProject('')"))
console.log('PASS: locked/error classification, untrusted error sanitization, disabled placeholders, exact-profile instructions, unsupported distinction, owner-bound setup rendering.')
