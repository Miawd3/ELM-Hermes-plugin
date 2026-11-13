import {readFileSync,writeFileSync} from 'node:fs'
import {execFileSync} from 'node:child_process'
import vm from 'node:vm'
import assert from 'node:assert/strict'
import {managerCommand,memoryDestination,parseManager} from '../desktop/manager.js'
const shipped=readFileSync(new URL('../desktop/plugin.js',import.meta.url),'utf8')
assert.equal(shipped.split('// BEGIN INLINED MANAGER HELPERS\n')[1].split('// END INLINED MANAGER HELPERS')[0],readFileSync(new URL('../desktop/manager.js',import.meta.url),'utf8').replaceAll('export function','function'))
const value={action:'save',revision:1,store_identity:'a'.repeat(32),kind:'reference',text:`apostrophe ' quote " backslash \\ newline\n<script>x</script> ; /elm off`}
assert.deepEqual(JSON.parse(execFileSync('python',['-c','import sys,shlex,json;print(shlex.split(sys.argv[1])[2])',managerCommand(value)],{encoding:'utf8'})),value)
assert.equal(memoryDestination('user',{user_scope:0,project:null}),'This chat only')
assert.equal(memoryDestination('user',{user_scope:1,project:null}),'Shared user memory in this profile')
assert.equal(memoryDestination('project',{user_scope:1,project:'A'}),'Project: A')
assert.equal(memoryDestination('reference',{user_scope:1,project:'A'}),'This chat only')
const page={store_identity:'a'.repeat(32),revision:1,project:null,user_scope:0,status:'approved',offset:0,next_offset:null,records:[]}
assert.deepEqual(parseManager({output:JSON.stringify(page)},true),page)
for(const bad of [null,'oops',{}, {error:'denied'},{...page,records:[{id:'not-a-record'}]},{...page,store_identity:null}])assert.throws(()=>parseManager({output:JSON.stringify(bad)},true))
// Lightweight hook/element contract harness, not a real React/host visual test.
function harness(request){
 const states=[],refs=[],effects=[];let index=0,refindex=0,mounted=false,current=true
 const context={TextEncoder,console,
 h:(tag,props,...children)=>({tag,props:props||{},children:children.flat(Infinity).filter(x=>x!==false&&x!==null&&x!==undefined)}),
 useState:init=>{const i=index++;if(!(i in states))states[i]=init;return [states[i],v=>states[i]=typeof v==='function'?v(states[i]):v]},
 useRef:init=>{const i=refindex++;return refs[i]??(refs[i]={current:init})},useEffect:fn=>{if(!mounted)effects.push(fn)}}
 vm.createContext(context)
 vm.runInContext(shipped.slice(shipped.indexOf('// BEGIN INLINED MANAGER HELPERS'),shipped.indexOf('function Settings'))+shipped.slice(shipped.indexOf('function MemoryManager'),shipped.indexOf('function AccessSetup'))+'\nthis.Component=MemoryManager',context)
 const identity={sid:'chat-a',profile:'default',gateway:{request}}
 const render=()=>{index=0;refindex=0;const tree=context.Component({identity,current:()=>current});mounted=true;return tree}
 render();const cleanup=effects[0]()
 return {render,cleanup,setup:effects[0],states,refs,setCurrent:v=>current=v}
}
const tick=()=>new Promise(resolve=>setImmediate(resolve))
const find=(tree,predicate)=>{if(tree&&typeof tree==='object'){if(predicate(tree))return tree;for(const c of tree.children||[]){const result=find(c,predicate);if(result)return result}}}
let calls=[]
const a=harness(async(method,args)=>{calls.push(args);return {output:JSON.stringify(page)}})
await tick();let tree=a.render()
assert.equal(calls.length,1);assert.equal(calls[0].session_id,'chat-a')
assert.ok(find(tree,n=>n.tag==='textarea'))
// Literal text, not HTML. Button submits explicit snapshot revision and destination identity.
find(tree,n=>n.tag==='textarea').props.onChange({target:{value:value.text}})
tree=a.render();find(tree,n=>n.tag==='button'&&n.children.includes('Save approved memory')).props.onClick()
await tick();assert.equal(calls.length,3)
const save=JSON.parse(execFileSync('python',['-c','import sys,shlex;print(shlex.split(sys.argv[1])[2])',calls[1].command],{encoding:'utf8'}));assert.equal(save.text,value.text);assert.equal(save.store_identity,page.store_identity)
a.cleanup()
// Response from an old owner cannot publish; cleanup/setup can launch again (StrictMode pattern).
let resolves=[];const b=harness(()=>new Promise(resolve=>resolves.push(resolve)))
b.cleanup();b.setup();assert.equal(resolves.length,2)
resolves[0]({output:JSON.stringify(page)});await tick();assert.equal(b.states[0],null);assert.equal(b.states[2],true)
resolves[1]({output:JSON.stringify(page)});await tick();assert.equal(b.states[0].revision,1);assert.equal(b.states[2],false)
b.cleanup()
const c=harness(()=>new Promise(resolve=>resolves.push(resolve)))
c.setCurrent(false);resolves.at(-1)({output:JSON.stringify(page)});await tick();assert.equal(c.states[0],null);c.cleanup()
console.log('PASS manager: safe shlex round-trip, schema validation, destination semantics, actual component save route, stale response and StrictMode lifecycle contracts. Not a real host render.')
