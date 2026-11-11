import {requireQualificationPath,qualificationScratch,qualificationPython} from './qualification_paths.mjs';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
import path from 'node:path';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const hostRoot=requireQualificationPath('HERMES_STOCK_SOURCE');
const require=createRequire(hostRoot+'/apps/desktop/package.json'),{build}=require('esbuild');
const here=path.dirname(fileURLToPath(import.meta.url)),root=path.resolve(here,'../../..');
const label=process.argv[2];assert.match(label,/^[a-z0-9-]+$/);
const out=path.join(root,'evidence/private-ui',label);await mkdir(path.dirname(out),{recursive:true});await mkdir(out);
const source=await readFile(path.resolve(here,'../desktop/plugin.js'));
const bundle=await build({entryPoints:[path.resolve(here,'../desktop/plugin.js')],bundle:true,write:false,platform:'node',format:'esm',nodePaths:[hostRoot+'/node_modules'],plugins:[{name:'sdk',setup(b){b.onResolve({filter:/^@hermes\/plugin-sdk$/},()=>({path:'sdk',namespace:'fixture'}));b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:'export const host={};export const gatewayActivationEpoch=()=>globalThis.__privateEpoch||0;',loader:'js'}));}}],logLevel:'silent'});
await writeFile(path.join(out,'plugin.mjs'),bundle.outputFiles[0].contents);
const mod=await import(pathToFileURL(path.join(out,'plugin.mjs'))),results=[];
function atom(v){const ls=new Set();return{get:()=>v,set(x){v=x;for(const f of ls)f();},listen(f){ls.add(f);return()=>ls.delete(f);}};}
function defaults(){const entry=reads=>({workspace_reads:reads,conversation:{provider:'',model:''},memory:{mode:'host',provider:'',model:'',allow_host_fallback:false}});return {private_chat:entry(false),private_workspace:entry(true),cap_enabled:false};}
function fixture(){
 const state={focusedSessionId:atom('runtime-a'),focusedStoredSessionId:atom('a'),focusedSessionProfile:atom('default'),focusedSessionOwner:atom({profile:'default',connectionId:'local'}),profile:atom('default'),connectionId:atom('local'),gateway:atom('open')};
 const calls=[];let data={schema:1,context:{session_id:'a',chat_id:'a'},revision:1,configured:false,settings:defaults(),projects:[{id:'w',name:'W',private_workspace:true}],memory_setup:true,capabilities:{hard_cap:false}},kind='private_chat',intent={id:'a'.repeat(32),method:'session.create',params:{request_id:'a'.repeat(32),source:'gui'},schema:1,context:{session_id:'a',chat_id:'a'}},status={id:'a'.repeat(32),state:'ready',target:null,outcome:null};
 const host={state,request:async(method,params)=>{calls.push({native:method,params});if(method==='model.options')return{providers:[{slug:'p',authenticated:true,models:['known'],unavailable_models:[]}]};if(method==='session.create')return{session_id:'new',stored_session_id:'new',message_count:0,messages:[]};return{project:{id:'new-workspace'}};}};
 const ctx={rest:async(url,o={})=>{calls.push({url,...o});if(url.startsWith('/ui/private/status'))return status;if(!o.method)return data;
 if(url.endsWith('/defaults')){data={...data,revision:data.revision+1,configured:true,settings:o.body.settings};return{ok:true,result:{revision:data.revision,configured:true,settings:data.settings}};}
 if(url.endsWith('/create')){kind=o.body.kind;intent={...intent,method:kind==='private_workspace'?'projects.create':'session.create',params:kind==='private_workspace'?{name:o.body.name,use:false,create_directory:false}:{request_id:intent.id,source:'gui',...(o.body.project_id?{project_id:o.body.project_id}:{})}};return{ok:true,result:intent};}
 if(url.endsWith('/finish')){const outcome={id:intent.id,kind,created_id:o.body.created_id,status:'configured',policy:{private:true}};status={...status,state:'applied',target:o.body.created_id,outcome};return{ok:true,result:outcome};}
 throw Error('Unexpected fixture path');}};
 return{host,ctx,calls,get data(){return data;},set data(x){data=x;}};
}
async function check(name,fn){try{await fn();results.push({name,pass:true});}catch(e){results.push({name,pass:false,error:e.stack});}}
await check('Explicit private creation uses one exact native RPC and independently reads back the owned intent',async()=>{
 assert.equal(typeof mod.createPrivateController,'function','Private defaults/native creation controller is missing');
 const f=fixture(),c=mod.createPrivateController(f.ctx,f.host);assert.equal(await c.refresh(),true);
 assert.equal(await c.create('private_chat','w',''),true);
 assert.equal(f.calls.filter(v=>v.native==='session.create').length,1);
 assert.equal(c.getSnapshot().created.created_id,'new');assert.equal(c.getSnapshot().unconfirmed,false);c.dispose();
});
await check('Uncertain defaults receipt blocks a second save until explicit read-only refresh',async()=>{
 const f=fixture(),base=f.ctx.rest;let writes=0;
 f.ctx.rest=async(p,o={})=>{const d=await base(p,o);if(p.endsWith('/defaults')){writes++;return{ok:true,result:{...d.result,settings:defaults()}};}return d;};
 const c=mod.createPrivateController(f.ctx,f.host);await c.refresh();const settings=defaults();settings.private_chat.workspace_reads=true;
 assert.equal(await c.save(settings),false);assert.equal(c.getSnapshot().saveUnknown,true);
 assert.equal(await c.save(settings),false);assert.equal(writes,1,'Unknown committed settings were written again');
 await c.refresh();assert.equal(c.getSnapshot().saveUnknown,false);assert.equal(c.getSnapshot().data.settings.private_chat.workspace_reads,true);c.dispose();
});
await check('Late native response after owner change cannot finish or retain former-owner state',async()=>{
 const f=fixture(),original=f.host.request;let release,started;
 const nativeStarted=new Promise(r=>started=r);
 f.host.request=(method,p)=>method==='session.create'?new Promise(r=>{release=r;started();}):original(method,p);
 const c=mod.createPrivateController(f.ctx,f.host);await c.refresh();const pending=c.create('private_chat','w','');await nativeStarted;
 f.host.state.profile.set('foreign');assert.equal(c.getSnapshot().data,null);
 release({session_id:'new',stored_session_id:'new',message_count:0,messages:[]});assert.equal(await pending,false);
 assert.equal(f.calls.filter(x=>x.url?.endsWith('/finish')).length,0);assert.equal(c.getSnapshot().intent,null);c.dispose();
});
await check('Unavailable model choices and unexpected native authority fields are refused before dispatch',async()=>{
 const f=fixture(),c=mod.createPrivateController(f.ctx,f.host);await c.refresh();const bad=defaults();bad.private_chat.conversation={provider:'p',model:'unknown'};
 assert.equal(await c.save(bad),false);assert.equal(f.calls.filter(x=>x.url?.endsWith('/defaults')).length,0);c.dispose();
 const g=fixture(),old=g.ctx.rest;g.ctx.rest=async(p,o)=>{const d=await old(p,o);if(p.endsWith('/create'))d.result.params.api_key='fictional-not-a-credential';return d;};
 const d=mod.createPrivateController(g.ctx,g.host);await d.refresh();assert.equal(await d.create('private_chat','w',''),false);assert.equal(g.calls.filter(x=>x.native==='session.create').length,0);d.dispose();
});
await check('Native uncertainty survives refresh and never causes automatic creation replay',async()=>{
 const f=fixture(),old=f.host.request;let calls=0;f.host.request=async(m,p)=>{if(m==='session.create'){calls++;throw Error('Lost ACK');}return old(m,p);};
 const c=mod.createPrivateController(f.ctx,f.host);await c.refresh();assert.equal(await c.create('private_chat','w',''),false);assert.equal(c.getSnapshot().unconfirmed,true);
 await c.refresh();assert.equal(c.getSnapshot().unconfirmed,true);assert.equal(await c.create('private_chat','w',''),false);assert.equal(calls,1);c.dispose();
});
await check('Disposal discards loaded private state and blocks every later mutation',async()=>{
 const f=fixture(),c=mod.createPrivateController(f.ctx,f.host);await c.refresh();assert.ok(c.getSnapshot().data);
 c.dispose();assert.equal(c.getSnapshot().data,null);assert.deepEqual(c.getSnapshot().choices,[]);
 const n=f.calls.length;assert.equal(await c.save(defaults()),false);assert.equal(await c.create('private_chat','w',''),false);assert.equal(f.calls.length,n);
});
await check('Follow-chat draft consumer snapshots native route and drops late responses after owner change',async()=>{
 assert.equal(typeof mod.requestChatModelDraft,'function','Human draft consumer lacks live model snapshot wiring');
 const f=fixture(),scope={id:'chat-root'},data={context:{session_id:'a'},selected_scope_id:'chat-root',model_policy:{mode:'follow_chat'}};
 let snap={ownerKey:'owner-a',data},actions=[];
 const c={getSnapshot:()=>snap,action:async(...a)=>{actions.push(a);return true;}};
 f.host.request=async(m,p)=>{assert.equal(m,'model.options');assert.equal(p.session_id,'runtime-a');return{provider:'p',model:'known',providers:[{slug:'p',authenticated:true,models:['known'],unavailable_models:[]}]};};
 assert.equal(await mod.requestChatModelDraft(c,data,scope,['source'],'summary',f.host),true);
 assert.deepEqual(actions[0][2].model_route,{provider:'p',model:'known'});assert.equal(actions[0][2].session_id,'a');
 actions=[];let release;f.host.request=()=>new Promise(r=>release=r);
 const pending=mod.requestChatModelDraft(c,data,scope,['source'],'summary',f.host);snap={ownerKey:'foreign',data:null};
 release({provider:'p',model:'known',providers:[{slug:'p',authenticated:true,models:['known']}]});assert.equal(await pending,false);assert.equal(actions.length,0);
});
await writeFile(path.join(out,'results.json'),JSON.stringify({results,source_sha256:createHash('sha256').update(source).digest('hex')},null,2));
console.log(JSON.stringify({passed:results.filter(x=>x.pass).length,failed:results.filter(x=>!x.pass).length,results}));process.exitCode=results.some(x=>!x.pass)?1:0;
