import {requireQualificationPath,qualificationScratch,qualificationPython} from './qualification_paths.mjs';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {mkdir,writeFile,readFile,rm,stat} from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import net from 'node:net';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
const H=requireQualificationPath('HERMES_STOCK_SOURCE'),req=createRequire(H+'/apps/desktop/package.json');
const {build}=req('esbuild'),{chromium}=req('@playwright/test');
const here=path.dirname(fileURLToPath(import.meta.url)),root=path.resolve(here,'../../..'),label=process.argv[2];assert.match(label,/^[a-z0-9-]+$/);
const out=path.join(root,'evidence/private-browser',label),stage=qualificationScratch('private-integration')+label;
await mkdir(path.dirname(out),{recursive:true});await mkdir(out);await mkdir(stage);await mkdir(path.join(stage,'tmp'));
await writeFile(path.join(stage,'OWNER.json'),JSON.stringify({owner:'private-controls-browser',label}));
Object.assign(process.env,{TMP:path.join(stage,'tmp'),TEMP:path.join(stage,'tmp'),TMPDIR:path.join(stage,'tmp')});
const env=Object.fromEntries(Object.entries(process.env).filter(([k])=>['SYSTEMROOT','WINDIR','PATH','PATHEXT','COMSPEC','USERPROFILE','HOMEDRIVE','HOMEPATH','LOCALAPPDATA','APPDATA'].includes(k.toUpperCase())));
Object.assign(env,{PRIVATE_UI_STAGE:stage,PRIVATE_UI_STAGE_ROOT:qualificationScratch('private-integration'),HERMES_STOCK_SOURCE:H,ELM_TEST_DEPS:requireQualificationPath('ELM_TEST_DEPS'),HERMES_HOME:path.join(stage,'home'),HERMES_DISABLE_LAZY_INSTALLS:'1',PYTHONDONTWRITEBYTECODE:'1',TMP:path.join(stage,'tmp'),TEMP:path.join(stage,'tmp'),TMPDIR:path.join(stage,'tmp'),SQLITE_TMPDIR:path.join(stage,'tmp')});
const sdk=`const atom=v=>{const s=new Set();return{get:()=>v,set:x=>{v=x;for(const f of s)f();},listen:f=>{s.add(f);return()=>s.delete(f);}}};export const ROUTES_AREA='routes',SIDEBAR_NAV_AREA='nav';export const gatewayActivationEpoch=()=>globalThis.__epoch||0;export const host={state:{focusedSessionId:atom('a'),focusedStoredSessionId:atom('a'),focusedSessionProfile:atom('default'),focusedSessionOwner:atom({profile:'default',connectionId:'local'}),profile:atom('default'),connectionId:atom('local'),gateway:atom('open')},onEvent:()=>()=>{},openSession:id=>{globalThis.__opened=id;},request:async(method,params)=>{const r=await fetch('/fixture/rpc',{method:'POST',headers:{'Content-Type':'application/json','x-fixture':'private-controls-fixture'},body:JSON.stringify({method,params})});if(!r.ok)throw Error('Synthetic native refusal');const d=await r.json();if(globalThis.__breakAfterCreate&&method==='session.create'){globalThis.__breakAfterCreate=false;throw Error('Synthetic lost native ACK');}return d;}};globalThis.__privateHost=host;`;
const entry=`import React from 'react';import{createRoot}from'react-dom/client';import plugin from ${JSON.stringify(path.resolve(here,'../desktop/plugin.js'))};const all=[];const ctx={register:x=>all.push(x),registerSettingsPage:x=>all.push(x),onDispose:()=>{},rest:async(p,o={})=>{const r=await fetch('/api/plugins/elm'+p,{method:o.method||'GET',headers:{'Content-Type':'application/json','x-fixture':'private-controls-fixture'},body:o.body===undefined?undefined:JSON.stringify(o.body)});const d=await r.json();(globalThis.__fixtureReplies||=[]).push({path:p,status:r.status,data:d});if(!r.ok)throw Error(d.code||'Synthetic API refusal');return d;}};plugin.register(ctx);const page=all.find(x=>x.id==='private-settings');if(!page)throw Error('Private page missing');createRoot(document.getElementById('root')).render(page.render());`;
let child,browser,page,failure;const checks=[],errors=[],blocked=[];let stdout='',stderr='';
const source=path.resolve(here,'../desktop/plugin.js'),sourceHash=createHash('sha256').update(await readFile(source)).digest('hex');
async function check(name,fn){await fn();checks.push(name);console.log('PASS '+name);}
try{
 const built=await build({stdin:{contents:entry,resolveDir:here,sourcefile:'private-browser-entry.js',loader:'js'},bundle:true,write:false,platform:'browser',format:'esm',nodePaths:[H+'/node_modules'],plugins:[{name:'sdk-fixture',setup(b){b.onResolve({filter:/^@hermes\/plugin-sdk$/},()=>({path:'sdk',namespace:'fixture'}));b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:sdk,loader:'js'}));}}],logLevel:'silent'});
 await writeFile(path.join(stage,'bundle.js'),built.outputFiles[0].contents);
 const listener=net.createServer();listener.listen(0,'127.0.0.1');await once(listener,'listening');const port=listener.address().port;await new Promise(r=>listener.close(r));const base='http://127.0.0.1:'+port;
 child=spawn(qualificationPython(),['-I','-X','utf8','-B',path.join(here,'private_controls_browser_backend.py'),String(port)],{env,cwd:stage,stdio:['ignore','pipe','pipe']});child.stdout.on('data',d=>stdout+=d);child.stderr.on('data',d=>stderr+=d);
 let ready=false;for(let i=0;i<100;i++){if(child.exitCode!==null)break;try{const r=await fetch(base);if(r.ok){ready=true;break;}}catch{}await new Promise(r=>setTimeout(r,100));}assert.ok(ready,'Owned fixture backend did not start: '+stderr);
 browser=await chromium.launch({headless:true,executablePath:requireQualificationPath('ELM_TEST_BROWSER'),env,args:['--no-first-run','--disable-background-networking','--disable-component-update','--disable-default-apps','--disable-sync','--no-proxy-server']});
 const context=await browser.newContext({viewport:{width:1440,height:1100}});await context.route('**/*',r=>{if(r.request().url().startsWith(base+'/'))return r.continue();blocked.push(r.request().url());return r.abort();});page=await context.newPage();page.setDefaultTimeout(15000);page.on('pageerror',e=>errors.push(e.message));
 const api=async(sid='a')=>{const r=await fetch(base+'/fixture/snapshot?session_id='+encodeURIComponent(sid),{headers:{'x-fixture':'private-controls-fixture'}});assert.ok(r.ok);return r.json();};
 await page.goto(base);await page.getByRole('heading',{name:'Private memory controls',exact:true}).waitFor();
 // Two independent pages issue startup reads. The existing store deliberately
 // refuses concurrent locks; exercise the explicit READ-only recovery control.
 await page.waitForFunction(()=>globalThis.__fixtureReplies?.some(x=>x.path.startsWith('/ui/private?')));
 if(await page.getByRole('alert').count()){
   await page.waitForFunction(()=>globalThis.__fixtureReplies?.some(x=>x.path.startsWith('/overview?')&&x.status===200));
   await page.getByRole('button',{name:'Refresh private controls',exact:true}).click();
 }
 await page.getByRole('button',{name:'New private chat',exact:true}).waitFor({state:'visible'});
 await check('Real defaults persistence and separate route preferences leave existing chat unchanged',async()=>{
  const group=page.getByRole('group',{name:'Future private chats',exact:true});await group.getByRole('checkbox').first().check();
  await group.getByLabel('Conversation model',{exact:true}).selectOption(JSON.stringify(['fixture-provider','fixture-model']));
  await group.getByLabel('Memory-processing route',{exact:false}).selectOption('separate');
  await group.getByLabel('Preferred memory model (existing host permission required)',{exact:true}).selectOption(JSON.stringify(['fixture-provider','fixture-model']));
  await group.getByRole('checkbox').last().check();await page.getByRole('button',{name:'Save future defaults',exact:true}).click();
  await page.getByRole('status').filter({hasText:'Defaults saved and independently read back'}).waitFor();
  assert.equal((await api()).policy.workspace_enabled,false);
 });
 let created;
 await check('Explicit native private chat wire is typed and real backend policy/model readback matches',async()=>{
  await page.getByLabel('Project placement',{exact:false}).selectOption({label:'Project: Original fixture project'});
  await page.getByRole('button',{name:'New private chat',exact:true}).click();await page.getByRole('heading',{name:'Private chat configured',exact:true}).waitFor();created=await page.locator('main section code').last().innerText();
  const d=await api(created);assert.equal(d.policy.private,true);assert.equal(d.policy.workspace_enabled,true);assert.equal(d.row.model,'fixture-model');assert.equal(d.model_policy.settings.private_chat.memory.model,'fixture-model');
  assert.equal(d.native_calls.filter(x=>x.method==='session.create').length,1);
 });
 await check('Private workspace and ordinary new member use their independent defaults',async()=>{
  await page.getByLabel('New private workspace name',{exact:false}).fill('Private QA workspace');await page.getByRole('button',{name:'New private workspace',exact:true}).click();await page.getByRole('heading',{name:'Private workspace configured',exact:true}).waitFor();
  await page.getByLabel('Project placement',{exact:false}).selectOption({label:'Private workspace: Private QA workspace'});await page.getByRole('button',{name:'New private-workspace member chat',exact:true}).click();await page.getByRole('heading',{name:'Private chat configured',exact:true}).waitFor();
  const id=await page.locator('main section code').last().innerText(),d=await api(id);assert.equal(d.policy.workspace_enabled,true);assert.equal(d.policy.private,true);assert.equal(d.model_policy.kind,'workspace_member');assert.equal(d.model_policy.settings.private_workspace.memory.mode,'host');
 });
 await check('Lost native ACK remains sticky across refresh with no duplicate creation; explicit inspect/close never deletes',async()=>{
  await page.evaluate(()=>window.__breakAfterCreate=true);await page.getByRole('button',{name:'New private chat',exact:true}).click();await page.getByRole('alert').filter({hasText:'Native creation may have happened'}).waitFor();const before=await api();
  await page.getByRole('button',{name:'Refresh private controls',exact:true}).click();await page.getByText('A creation attempt is unresolved.',{exact:false}).waitFor();assert.equal(await page.getByRole('button',{name:'New private chat',exact:true}).isDisabled(),true);assert.equal((await api()).native_calls.length,before.native_calls.length);
  await page.getByRole('button',{name:'Check prior attempt',exact:true}).click();await page.getByRole('alert').filter({hasText:'Outcome remains unconfirmed'}).waitFor();assert.equal((await api()).native_calls.length,before.native_calls.length);
  await page.getByRole('button',{name:'I inspected the native list — close attempt without retry or deletion',exact:true}).click();await page.getByRole('status').filter({hasText:'Attempt closed after your inspection'}).waitFor();assert.equal((await api()).native_calls.length,before.native_calls.length);
 });
 await check('Wide/narrow controls render without horizontal clipping and native caps are honestly unavailable',async()=>{
  await page.getByRole('group',{name:'Optional API spending cap — OFF',exact:true}).waitFor();assert.equal(await page.getByRole('group',{name:'Optional API spending cap — OFF',exact:true}).getByRole('checkbox').isDisabled(),true);
  await page.screenshot({path:path.join(out,'private-controls-wide.png'),fullPage:true,animations:'disabled'});await page.setViewportSize({width:360,height:1000});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);await page.screenshot({path:path.join(out,'private-controls-narrow.png'),fullPage:true,animations:'disabled'});
 });
 await check('Foreign owner immediately removes former-owner preferences and blocks new writes',async()=>{
  const before=(await api()).native_calls.length;await page.evaluate(()=>window.__privateHost.state.profile.set('foreign'));await page.getByRole('alert').waitFor();assert.equal(await page.getByRole('group',{name:'Future private chats',exact:true}).count(),0);assert.equal((await api()).native_calls.length,before);
 });
 assert.deepEqual(errors,[]);assert.deepEqual(blocked,[]);assert.equal(createHash('sha256').update(await readFile(source)).digest('hex'),sourceHash);
}catch(e){failure=e.stack;console.error(e.stack);if(page)try{await writeFile(path.join(out,'diagnostic.json'),JSON.stringify(await page.evaluate(()=>({text:document.body.innerText,replies:globalThis.__fixtureReplies})),null,2));await page.screenshot({path:path.join(out,'failure.png'),fullPage:true});}catch{}}finally{
 if(browser)await browser.close();
 if(child&&child.exitCode===null&&child.signalCode===null){const stopped=once(child,'exit');child.kill();await Promise.race([stopped,new Promise((_,reject)=>setTimeout(()=>reject(Error('Owned backend exit not confirmed')),10000))]);}
 await writeFile(path.join(out,'backend-stdout.txt'),stdout);await writeFile(path.join(out,'backend-stderr.txt'),stderr);
 const bytes=async dir=>{const {readdir}=await import('node:fs/promises');let n=0;for(const x of await readdir(dir,{withFileTypes:true})){const p=path.join(dir,x.name);n+=x.isDirectory()?await bytes(p):(await stat(p)).size;}return n;};const removed=await bytes(stage);
 assert.equal(JSON.parse(await readFile(path.join(stage,'OWNER.json'),'utf8')).owner,'private-controls-browser');await rm(stage,{recursive:true});
 const result={passed:checks.length,checks,failure:failure||null,page_errors:errors,external_requests:blocked,source_sha256:sourceHash,temporary_root_removed:!(await stat(stage).catch(()=>null)),removed_logical_bytes:removed,native_RPC:'public typed-contract stand-in; candidate API/native metadata stores are real',new_model_calls:0,live_UI_changed:false};await writeFile(path.join(out,'results.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));process.exitCode=failure?1:0;
}
