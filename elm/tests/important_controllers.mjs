import {requireQualificationPath,qualificationScratch,qualificationPython} from './qualification_paths.mjs';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
import path from 'node:path';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
const host=requireQualificationPath('HERMES_STOCK_SOURCE');
const require=createRequire(host+'/apps/desktop/package.json');
const {build}=require('esbuild');
const here=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(here,'../../..');
const label=process.argv[2];
assert.match(label,/^[a-z0-9-]+$/);
const out=path.join(root,'evidence/important-updates-ui',label);
await mkdir(path.dirname(out),{recursive:true});
await mkdir(out,{recursive:false});
const bundle=await build({entryPoints:[path.resolve(here,'../desktop/plugin.js')],bundle:true,write:false,platform:'node',format:'esm',nodePaths:[host+'/node_modules'],plugins:[{name:'sdk',setup(b){b.onResolve({filter:/^@hermes\/plugin-sdk$/},()=>({path:'sdk',namespace:'fixture'}));b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:'export const host={}; export const gatewayActivationEpoch=()=>globalThis.__testEpoch||0;',loader:'js'}));}}],logLevel:'silent'});
await writeFile(path.join(out,'plugin.mjs'),bundle.outputFiles[0].contents);
const mod=await import(pathToFileURL(path.join(out,'plugin.mjs')));
const results=[];
async function check(name,fn){try{await fn();results.push({name,pass:true});console.log('PASS '+name);}catch(e){results.push({name,pass:false,error:e.stack});throw e;}}
function atom(v){const ls=new Set();return{get:()=>v,set(x){v=x;for(const f of ls)f();},listen(f){ls.add(f);return()=>ls.delete(f);},count:()=>ls.size};}
function state(){return{focusedStoredSessionId:atom('a'),focusedSessionProfile:atom('default'),focusedSessionOwner:atom({profile:'default',connectionId:'local'}),profile:atom('default'),connectionId:atom('local'),gateway:atom('open')};}
function record(over={}){return{id:'a'.repeat(32),session_id:'a',chat_id:'a',title:'Partial output',body:'Not the whole request.',kind:'partial',status:'unread',dismissed:false,revision:1,created_at:'now',updated_at:'now',...over};}
function overview(session='a',rs=[record()]){return{schema:1,context:{session_id:session,chat_id:session},results:rs,counts:{unread:rs.filter(r=>r.status==='unread').length,viewed:0,read:0,dismissed:0},attention:{mode:'quiet',updates_visible:false,revision:1},next_cursor:null};}
let failure;
try{
 await check('Important controller loads only a verified own-chat API response',async()=>{
  assert.equal(typeof mod.createImportantController,'function','The genuine Important results controller is missing');
  const s=state(),calls=[];const c=mod.createImportantController({rest:async(p)=>{calls.push(p);return overview();}},{state:s});
  assert.equal(await c.refresh(),true);assert.equal(c.getSnapshot().data.results[0].kind,'partial');
  assert.equal(calls.length,1);c.dispose();assert.equal(s.profile.count(),0);
 });
 await check('Loaded and pending content invalidates on owner/session/gateway/epoch changes',async()=>{
  const s=state();let resolve,slow=false;const c=mod.createImportantController({rest:()=>slow?new Promise(r=>resolve=r):Promise.resolve(overview())},{state:s});
  await c.refresh();const old=c.getSnapshot().ownerKey;
  slow=true;const pending=c.refresh();s.focusedStoredSessionId.set('b');assert.equal(c.getSnapshot().data,null);
  resolve(overview());assert.equal(await pending,false);assert.equal(c.getSnapshot().data,null);
  s.focusedSessionOwner.set({profile:'foreign',connectionId:'local'});assert.equal(c.getSnapshot().phase,'unavailable');assert.equal(await c.refresh(),false);
  s.focusedSessionOwner.set({profile:'default',connectionId:'local'});slow=false;s.focusedStoredSessionId.set('a');await c.refresh();
  s.gateway.set('closed');assert.equal(c.getSnapshot().data,null);s.gateway.set('open');await c.refresh();
  globalThis.__testEpoch=1;c.reconcile();assert.equal(c.getSnapshot().data,null);assert.notEqual(c.getSnapshot().ownerKey,old);c.dispose();
 });
 await check('Read requires exact result readback; uncertain writes are blocked without retry',async()=>{
  const s=state();let r=record(),writes=0,lie=false,timeout=false;
  const c=mod.createImportantController({rest:async(p,o={})=>{
   if(o.method){writes++;if(timeout)throw Error('Timeout after possible commit');r={...r,status:'read',revision:2};return{ok:true,result:r};}
   if(p.split('?')[0]===`/ui/results/${r.id}`)return{schema:1,context:{session_id:'a',chat_id:'a'},id:r.id,exists:true,result:lie?record():r};
   return overview('a',[r]);
  }},{state:s});
  await c.refresh();const pin=c.getSnapshot().ownerKey;lie=true;
  assert.equal(await c.mutate(r,'read',pin),false);assert.equal(c.getSnapshot().unconfirmed,true);assert.equal(writes,1);
  assert.equal(await c.mutate(r,'read',pin),false);assert.equal(writes,1);
  lie=false;await c.refresh();timeout=true;assert.equal(await c.mutate(r,'dismiss',pin),false);assert.equal(c.getSnapshot().unconfirmed,true);assert.equal(writes,2);c.dispose();
 });
 await check('Preference receipt must match the intended value and independent GET',async()=>{
  const s=state();let writes=0;const c=mod.createImportantController({rest:async(p,o={})=>{
   if(o.method){writes++;return{ok:true,result:{mode:'off',updates_visible:false,revision:2}};}
   if(p.startsWith('/ui/attention'))return{schema:1,context:{session_id:'a',chat_id:'a'},attention:{mode:'quiet',updates_visible:false,revision:2}};
   return overview();
  }},{state:s});await c.refresh();assert.equal(await c.setAttention({mode:'off',updates_visible:false},c.getSnapshot().ownerKey),false);assert.equal(c.getSnapshot().unconfirmed,true);assert.equal(writes,1);c.dispose();
 });
 await check('Selective updater sends exact selections only, reads back and stops after uncertainty',async()=>{
  assert.equal(typeof mod.createUpdatesController,'function','The native update controller is missing');
  const s=state(),one={type:'skill',name:'one',source:'github',identifier:'x/one',current:'sha256:'+'a'.repeat(16),target:'sha256:'+'b'.repeat(16),status:'update_available',selectable:true,detail:''};
  const two={...one,name:'two',identifier:'x/two'},calls=[];
  const c=mod.createUpdatesController({rest:async(p,o={})=>{calls.push({p,...o});
   if(p==='/ui/updates/check')return{schema:1,context:{session_id:'a',chat_id:'a'},rows:[one,two],errors:[],policy:'Native controls'};
   if(p==='/ui/updates/apply')return{ok:true,result:{type:'skill',name:'one',current:one.current,target:one.target,observed:one.target,status:'updated'}};
   return{schema:1,context:{session_id:'a',chat_id:'a'},type:'skill',name:'one',observed:one.current};
  }},{state:s});await c.check();assert.equal(await c.apply([one,two],c.getSnapshot().ownerKey),false);
  assert.equal(calls.filter(x=>x.p==='/ui/updates/apply').length,1);assert.equal(c.getSnapshot().unconfirmed,true);
  assert.equal(calls.some(x=>/\/(install|auto_update|update_all)$/.test(x.p)),false);
  s.profile.set('foreign');assert.deepEqual(c.getSnapshot().rows,[]);c.dispose();
 });
}catch(e){failure=e;console.error(e.stack);}finally{await writeFile(path.join(out,'results.json'),JSON.stringify({results,fatal:failure?.stack||null},null,2));process.exitCode=failure?1:0;}
