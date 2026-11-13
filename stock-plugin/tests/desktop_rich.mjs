import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {richData,visualPrefs,ownedRow} from '../desktop/rich_helpers.js'
for(const kind of ['progress','update','answer','final','question']) assert.ok(richData({kind,text:'plain text'}))
for(const attrs of [null,[],{}, {kind:'verified',text:'x'}, {kind:'answer',text:''}, {kind:'answer',text:'x'.repeat(1201)}, {kind:'answer',title:'x'.repeat(101),text:'x'}, {kind:'answer',text:'x',html:'<b>x</b>'}, {kind:'answer',text:'x\0'}]) assert.equal(richData(attrs),null)
assert.equal(richData({kind:'answer',text:'<script>alert(1)</script>'}).text,'<script>alert(1)</script>')
assert.deepEqual(visualPrefs({rich:'true',style:'url(x)'}),{rich:false,shortcut:true,style:'accent'})
assert.equal(visualPrefs({rich:true,shortcut:false,style:'plain'}).shortcut,false)
assert.equal(ownedRow('stored','stored',{connectionId:'a',profile:'p'},'a','p'),true)
for(const args of [['stored','runtime',{connectionId:'a',profile:'p'},'a','p'],['stored','stored',{connectionId:'b',profile:'p'},'a','p'],['stored','stored',{connectionId:'a',profile:'q'},'a','p'],['stored','stored',null,'a','p']]) assert.equal(ownedRow(...args),false)
const shipped=readFileSync(new URL('../desktop/plugin.js',import.meta.url),'utf8')
const helper=readFileSync(new URL('../desktop/rich_helpers.js',import.meta.url),'utf8').replaceAll('export function','function')
assert.equal(shipped.split('// BEGIN INLINED RICH HELPERS\n')[1].split('// END INLINED RICH HELPERS')[0],helper)
assert.ok(!shipped.includes('dangerouslySetInnerHTML'))
assert.ok(shipped.includes("},data.text)"))
assert.ok(shipped.includes("pluginSettingsHref('elm:settings')"))
assert.ok(shipped.includes('host.state.focusedStoredSessionId.get()'))
console.log('PASS: rich kinds/bounds, plain text payload, preferences, stored-row owner fencing and shipped helper parity.')
