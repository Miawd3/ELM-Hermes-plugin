import { readFileSync } from 'node:fs'
import assert from 'node:assert/strict'
import { usableIdentity, sameIdentity, parseStatus } from '../desktop/identity.js'
const gateway = {}
const a = { sid: 's', profile: 'default', connectionId: 'local', gateway, gatewayState: 'open', owner: {connectionId:'local',profile:'default'}, epoch:1 }
assert.equal(usableIdentity(a),true)
assert.equal(sameIdentity(a,{...a}),true)
assert.equal(sameIdentity(a,{...a,connectionId:'other',owner:{connectionId:'other',profile:'default'}}),false)
assert.equal(sameIdentity(a,{...a,gateway:{}}),false)
assert.equal(sameIdentity(a,{...a,epoch:2}),false)
assert.equal(sameIdentity(a,{...a,owner:{connectionId:'other',profile:'default'}}),false)
assert.equal(sameIdentity(a,{...a,owner:{connectionId:'local',profile:'another'}}),false)
assert.equal(sameIdentity(a,{...a,gatewayState:'connecting'}),false)
assert.equal(sameIdentity(a,{...a,sid:'another'}),false)
assert.equal(usableIdentity({...a,connectionId:null}),false)
assert.equal(usableIdentity({...a,sid:'new'}),false)
const valid={enabled:1,capture:0,agent:0,organizer:0,user_scope:0,project:null,revision:2}
assert.deepEqual(parseStatus({output:JSON.stringify(valid)}),valid)
for(const bad of [null,{}, {output:'nope'},{output:'{}'}, {output:JSON.stringify({...valid,agent:true})}, {output:JSON.stringify({...valid,error:'no'})}]) {
  assert.throws(()=>parseStatus(bad))
}
// An awaited response may publish only against its captured identity + generation.
let published=false;const current={...a,gateway:{}}
if(sameIdentity(a,current))published=true
assert.equal(published,false)
console.log('PASS: 19 desktop owner/status guards, including connection/socket swaps, ABA epoch, focused-owner mismatch, reconnect, malformed response and stale publication.')

const shipped = readFileSync(new URL('../desktop/plugin.js', import.meta.url), 'utf8')
const helper = readFileSync(new URL('../desktop/identity.js', import.meta.url), 'utf8').replaceAll('export function', 'function')
assert.equal(shipped.split('// BEGIN INLINED IDENTITY HELPERS\n')[1].split('// END INLINED IDENTITY HELPERS')[0], helper)
const imports = [...shipped.matchAll(/from\s+['"]([^'"]+)['"]/g)].map(x=>x[1])
assert.deepEqual(imports.sort(), ['@hermes/plugin-sdk', 'react'])
assert.ok(shipped.includes('const epoch = useGatewayActivationEpoch()'))
assert.ok(shipped.includes('const visibleState = sameIdentity(stateOwner, identity) ? state : null'))
assert.ok(shipped.includes("visibleState && h('div'"))
assert.ok(shipped.includes('setStateOwner(identity); setState(next)'))
console.log('PASS: 6 shipped UI contract checks: inline helper parity, loader-supported imports, reactive epoch, owner-bound rendering and publication.')
assert.ok(shipped.includes("visibleState.permissions_via_cli && (key !== 'enabled' || !visibleState.enabled)"))
assert.ok(shipped.includes('disabled: busy || visibleState.permissions_via_cli'))
assert.ok(shipped.includes('Any authenticated client of this chat shares access.'))
console.log('PASS: 3 exact-session grant UI restriction checks.')
