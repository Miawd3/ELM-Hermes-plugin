import {requireQualificationPath,qualificationScratch,qualificationPython} from './qualification_paths.mjs';
// Real exported controllers. Only SDK identity and REST boundaries are fixtures.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
import path from 'node:path';
import {mkdir,readFile,writeFile,rm} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const host=requireQualificationPath('HERMES_STOCK_SOURCE');
const require=createRequire(host+'/apps/desktop/package.json');
const {build}=require('esbuild');
const here=path.dirname(fileURLToPath(import.meta.url)),root=path.resolve(here,'../../..');
const label=process.argv[2],group=process.argv[3]||'all';
assert.match(label,/^[a-z0-9-]+$/);
const evidence=path.join(root,'evidence/important-owner-ui-repairs',label);
const scratch=qualificationScratch('important-owner-ui-repairs')+label;
await mkdir(path.dirname(evidence),{recursive:true});await mkdir(evidence);
await mkdir(scratch,{recursive:true});
const source=await readFile(path.resolve(here,'../desktop/plugin.js'));
await writeFile(path.join(evidence,'plugin-source.js'),source);
const bundled=await build({entryPoints:[path.resolve(here,'../desktop/plugin.js')],bundle:true,write:false,platform:'node',format:'esm',nodePaths:[host+'/node_modules'],plugins:[{name:'sdk',setup(b){b.onResolve({filter:/^@hermes\/plugin-sdk$/},()=>({path:'sdk',namespace:'fixture'}));b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:'export const host=globalThis.__importantHost; export const gatewayActivationEpoch=()=>globalThis.__importantEpoch||0;',loader:'js'}));}}],logLevel:'silent'});
await writeFile(path.join(scratch,'plugin.mjs'),bundled.outputFiles[0].contents);
function atom(v){const listeners=new Set();return{get:()=>v,set(x){v=x;for(const f of listeners)f();},listen(f){listeners.add(f);return()=>listeners.delete(f);},count:()=>listeners.size};}
function state(){return{focusedStoredSessionId:atom('a'),focusedSessionId:atom('runtime-a'),focusedSessionProfile:atom('default'),focusedSessionOwner:atom({profile:'default',connectionId:'local'}),profile:atom('default'),connectionId:atom('local'),gateway:atom('open')};}
const sdkHost={state:state()};globalThis.__importantHost=sdkHost;
const mod=await import(pathToFileURL(path.join(scratch,'plugin.mjs')));
const results=[];
async function check(groupName,name,fn){if(group!=='all'&&group!==groupName)return;try{await fn();results.push({group:groupName,name,pass:true});console.log('PASS '+name);}catch(e){results.push({group:groupName,name,pass:false,error:e.stack});console.error('FAIL '+name+'\n'+e.stack);}}
function record(n){return{id:n.toString(16).padStart(32,'0'),session_id:'a',chat_id:'a',title:'Output '+n,body:'Full saved body '+n,kind:'partial',status:'unread',dismissed:false,revision:1,created_at:'now',updated_at:'now'};}
function fixture(total=101){
 let rows=Array.from({length:total},(_,n)=>record(n+1));const calls=[];
 const envelope=extra=>({schema:1,context:{session_id:'a',chat_id:'a'},...extra});
 const rest=async(p,o={})=>{
  calls.push({p,...o});const u=new URL(p,'http://fixture');
  if(u.pathname==='/ui/results'){
   const visible=rows.filter(r=>u.searchParams.get('include_dismissed')==='true'||!r.dismissed);
   const cursor=Number(u.searchParams.get('cursor')||0),items=visible.filter(r=>parseInt(r.id,16)>cursor).slice(0,100);
   return envelope({results:items,counts:{unread:rows.filter(r=>!r.dismissed&&r.status==='unread').length,viewed:rows.filter(r=>!r.dismissed&&r.status==='viewed').length,read:rows.filter(r=>!r.dismissed&&r.status==='read').length,dismissed:rows.filter(r=>r.dismissed).length},attention:{mode:'quiet',updates_visible:false,revision:1},next_cursor:visible.some(r=>parseInt(r.id,16)>parseInt(items.at(-1)?.id||'0',16))?String(parseInt(items.at(-1).id,16)):null});
  }
  const [,id,action]=u.pathname.match(/^\/ui\/results\/([0-9a-f]{32})(?:\/(view|read|dismiss|restore))?$/)||[];
  assert.ok(id,'Unexpected fixture boundary '+p);let r=rows.find(r=>r.id===id);
  if(!o.method)return envelope({id,exists:Boolean(r),result:r||null});
  assert.equal(o.body.expected_revision,r.revision);
  if(o.method==='DELETE'){rows=rows.filter(x=>x.id!==id);return{ok:true,result:{deleted_id:id,deleted_revision:r.revision}};}
  const status=action==='read'?'read':action==='view'&&r.status==='unread'?'viewed':r.status;
  const dismissed=action==='dismiss'?true:action==='restore'?false:r.dismissed;
  r={...r,status,dismissed,revision:r.revision+Number(status!==r.status||dismissed!==r.dismissed)};
  rows=rows.map(x=>x.id===id?r:x);return{ok:true,result:r};
 };
 return{rest,calls,rows:()=>rows};
}
try{
 await check('pagination','Opening unread row 101 preserves all accumulated rows and exact body',async()=>{
  const f=fixture(),c=mod.createImportantController(f,{state:state()});
  try{assert.equal(await c.refresh(),true);assert.equal(await c.more(),true);
   const before=c.getSnapshot(),r=before.data.results[100];assert.equal(before.data.results.length,101);
   assert.equal(await c.mutate(r,'view',before.ownerKey),true);
   assert.equal(c.getSnapshot().data.results.length,101,'Viewing page two must not replace the accumulated list with page one');
   assert.equal(c.getSnapshot().data.results[100].body,r.body);assert.equal(c.getSnapshot().data.results[100].status,'viewed');
   assert.equal(c.getSnapshot().data.next_cursor,null);assert.equal(c.getSnapshot().data.counts.viewed,1);
  }finally{c.dispose();}
 });
 await check('pagination','Explicit own detail outside page one remains exact through view/read/delete',async()=>{
  const f=fixture(102),c=mod.createImportantController(f,{state:state()});
  try{await c.refresh();const pin=c.getSnapshot().ownerKey,id=record(102).id;
   assert.equal(await c.openResult(id,pin),true);assert.equal(c.getSnapshot().data.results.length,100);
   assert.equal(await c.mutate(c.getSnapshot().detail,'view',pin),true);
   assert.equal(c.getSnapshot().detail.id,id);assert.equal(c.getSnapshot().detail.status,'viewed');
   assert.equal(await c.mutate(c.getSnapshot().detail,'read',pin),true);assert.equal(c.getSnapshot().detail.status,'read');
   assert.equal(c.getSnapshot().detail.body,record(102).body);
   assert.equal(await c.mutate(c.getSnapshot().detail,'delete',pin),true);assert.equal(c.getSnapshot().detail,null);
   assert.equal(c.getSnapshot().data.results.length,100);
  }finally{c.dispose();}
 });
 await check('pagination','Accumulated row mutations preserve cursor and reconcile only exact target',async()=>{
  const f=fixture(205),c=mod.createImportantController(f,{state:state()});
  try{await c.refresh();await c.more();const pin=c.getSnapshot().ownerKey;
   assert.equal(c.getSnapshot().data.next_cursor,'200');
   for(const action of ['view','read','dismiss']){
    const r=c.getSnapshot().data.results.find(r=>r.id===record(150).id);
    assert.equal(await c.mutate(r,action,pin),true);
    assert.equal(c.getSnapshot().data.next_cursor,'200');
   }
   assert.equal(c.getSnapshot().data.results.length,199);assert.equal(c.getSnapshot().data.results.some(r=>r.id===record(150).id),false);
   assert.equal(await c.more(),true);assert.equal(c.getSnapshot().data.results.length,204);
   const r=c.getSnapshot().data.results.find(r=>r.id===record(205).id);
   assert.equal(await c.mutate(r,'delete',pin),true);assert.equal(c.getSnapshot().data.results.length,203);
  }finally{c.dispose();}
 });
 await check('refresh','Same-owner refresh retains loaded rows and own detail until independently reconciled',async()=>{
  const f=fixture(101),s=state();let held,release,fail=false;
  const c=mod.createImportantController({rest:async(p,o)=>{if(held&&p.startsWith('/ui/results?'))await held;if(fail)throw Error('Offline refresh');return f.rest(p,o);}},{state:s});
  try{await c.refresh();await c.more();const pin=c.getSnapshot().ownerKey;await c.openResult(record(101).id,pin);
   const before=c.getSnapshot();held=new Promise(r=>release=r);const pending=c.refresh();
   assert.equal(c.getSnapshot().data,before.data,'Background refresh must retain the rendered data object while pending');
   assert.equal(c.getSnapshot().detail,before.detail,'Own detail must remain mounted while pending');
   release();assert.equal(await pending,true);assert.equal(c.getSnapshot().data.results.length,101);
   assert.equal(c.getSnapshot().detail.id,record(101).id);assert.equal(c.getSnapshot().detail.body,record(101).body);
   fail=true;assert.equal(await c.refresh(),false);assert.equal(c.getSnapshot().data.results.length,101);
   assert.equal(c.getSnapshot().detail.id,record(101).id);assert.match(c.getSnapshot().error,/Offline/);
  }finally{release?.();c.dispose();}
 });
 await check('refresh','Registered completion listener ignores clearly foreign events but refreshes stored/runtime owner events',async()=>{
  const f=fixture(),events=new Map(),dispose=[],registrations=[];let calls=0;
  sdkHost.state=state();sdkHost.onEvent=(type,fn)=>{events.set(type,fn);return()=>events.delete(type);};
  mod.default.register({rest:async(p,o)=>{if(p.startsWith('/ui/')){calls++;return f.rest(p,o);}throw Error('Unused memory API fixture');},register:x=>registrations.push(x),onDispose:fn=>dispose.push(fn)});
  const fire=events.get('message.complete');assert.equal(typeof fire,'function');
  try{
   for(const event of [{session_id:'other'}, {session_id:'a',profile:'other'}, {session_id:'a',connectionId:'remote'}])fire(event);
   await new Promise(r=>setImmediate(r));assert.equal(calls,0,'Foreign completions must not trigger Important REST');
   fire({session_id:'runtime-a',profile:'default',connectionId:'local'});await new Promise(r=>setImmediate(r));assert.equal(calls,1);
   fire({session_id:'a'});await new Promise(r=>setImmediate(r));assert.equal(calls,2);
   fire({});await new Promise(r=>setImmediate(r));assert.equal(calls,3,'Legacy unscoped completion may refresh without destructive invalidation');
  }finally{dispose.forEach(fn=>fn());assert.equal(events.size,0);}
 });
 await check('refresh','Genuine ownership/lifetime changes immediately invalidate retained data and reject late refreshes',async()=>{
  for(const change of [s=>s.focusedStoredSessionId.set('b'),s=>s.focusedSessionProfile.set('other'),s=>s.focusedSessionOwner.set({profile:'other',connectionId:'local'}),s=>s.profile.set('other'),s=>s.connectionId.set('remote'),s=>s.gateway.set('closed'),(s,c)=>{globalThis.__importantEpoch=(globalThis.__importantEpoch||0)+1;c.reconcile();}]){
   const f=fixture(),s=state();let held,release;const c=mod.createImportantController({rest:async(p,o)=>{if(held)await held;return f.rest(p,o);}},{state:s});
   try{await c.refresh();await c.openResult(record(101).id,c.getSnapshot().ownerKey);
    held=new Promise(r=>release=r);const pending=c.refresh();change(s,c);
    assert.equal(c.getSnapshot().data,null);assert.equal(c.getSnapshot().detail,null);
    release();assert.equal(await pending,false);assert.equal(c.getSnapshot().data,null);assert.equal(c.getSnapshot().detail,null);
   }finally{release?.();c.dispose();}
  }
 });
}finally{
 await rm(scratch,{recursive:true,force:true});
 const report={lane:'Actual exported Important controllers; SDK identity and REST boundary fixture, not real backend',source_sha256:createHash('sha256').update(source).digest('hex'),test_sha256:createHash('sha256').update(await readFile(fileURLToPath(import.meta.url))).digest('hex'),results,passed:results.filter(r=>r.pass).length,failed:results.filter(r=>!r.pass).length,scratch_removed:true};
 await writeFile(path.join(evidence,'results.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({evidence,passed:report.passed,failed:report.failed}));process.exitCode=report.failed?1:0;
}
