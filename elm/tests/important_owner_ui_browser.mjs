import {requireQualificationPath,qualificationScratch,qualificationPython} from './qualification_paths.mjs';
// Actual candidate ASGI/store + isolated Edge; public SDK identity/event fixture.
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {readFile,writeFile,mkdir,readdir,rm} from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {createHash} from 'node:crypto';
import http from 'node:http';
import path from 'node:path';
import assert from 'node:assert/strict';
const here=path.dirname(fileURLToPath(import.meta.url)),root=path.resolve(here,'../../..');
const host=requireQualificationPath('HERMES_STOCK_SOURCE'),deps=requireQualificationPath('ELM_TEST_DEPS');
const label=process.argv[2];assert.match(label,/^[a-z0-9-]+$/);
const scratch=qualificationScratch('important-owner-ui-repairs')+label;
const evidence=path.join(root,'evidence/important-owner-ui-repairs',label);
await mkdir(path.dirname(evidence),{recursive:true});await mkdir(evidence);
for(const p of ['home','tmp','runtime'])await mkdir(path.join(scratch,p),{recursive:true});
const require=createRequire(host+'/apps/desktop/package.json'),{build}=require('esbuild'),{chromium}=require('@playwright/test');
const env=Object.fromEntries(Object.entries(process.env).filter(([k])=>['SYSTEMROOT','WINDIR','PATH','PATHEXT','COMSPEC','USERPROFILE','HOMEDRIVE','HOMEPATH','LOCALAPPDATA','APPDATA'].includes(k.toUpperCase())));
Object.assign(env,{HERMES_HOME:path.join(scratch,'home'),HERMES_RUNTIME_DIR:path.join(scratch,'runtime'),TMP:path.join(scratch,'tmp'),TEMP:path.join(scratch,'tmp'),TMPDIR:path.join(scratch,'tmp'),SQLITE_TMPDIR:path.join(scratch,'tmp'),PYTHONDONTWRITEBYTECODE:'1',HERMES_DISABLE_LAZY_INSTALLS:'1',TZ:'UTC'});
let child,browser,server,failure,stderr='',serial=0,releaseHeld;const pending=new Map(),api=[],results=[],pageErrors=[],blocked=[],pids=[],hashes={};
function rpc(value){const id=++serial;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(Error('Python bridge timeout'));},60000);pending.set(id,{resolve:x=>{clearTimeout(timer);resolve(x);},reject});child.stdin.write(JSON.stringify({id,...value})+'\n');});}
async function call(method,p,body){const r=await rpc({method,path:'/api/plugins/elm'+p,body});api.push({method,path:p,request:body??null,...r});assert.equal(r.status,200,JSON.stringify(r));return r.body;}
async function check(name,fn){try{const detail=await fn();results.push({name,pass:true,detail});console.log('PASS '+name);}catch(e){results.push({name,pass:false,error:e.stack});throw e;}}
try{
 child=spawn(qualificationPython(),['-I','-B',path.join(here,'important_browser_backend.py'),host,path.resolve(here,'..'),deps],{cwd:scratch,env,stdio:['pipe','pipe','pipe']});child.stderr.on('data',b=>stderr+=b);
 const ready=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('No Python readiness: '+stderr)),45000);createInterface({input:child.stdout}).on('line',line=>{try{const x=JSON.parse(line);if(x.ready){clearTimeout(timer);resolve(x);}else if(x.id){pending.get(x.id)?.resolve(x);pending.delete(x.id);}}catch{stderr+='\n'+line;}});child.once('exit',()=>{clearTimeout(timer);reject(Error('Python exited: '+stderr));});});pids.push(ready.pid);
 for(const f of ['../desktop/plugin.js','../elm_plugin/result_inbox.py','../elm_plugin/product_ui_api.py','important_owner_ui_browser.mjs','important_browser_backend.py','important_browser_entry.js','important_sdk_fixture.js']){const p=path.resolve(here,f);hashes[p]=createHash('sha256').update(await readFile(p)).digest('hex');}
 // Preserve frozen fixtures. Add only runtime identity + public event fan-out.
 let sdk=await readFile(path.join(here,'important_sdk_fixture.js'),'utf8');
 sdk=sdk.replace('export const host=',"const eventListeners=new Map(); export const host=").replace("focusedStoredSessionId:atom('chat-a'),","focusedStoredSessionId:atom('chat-a'),focusedSessionId:atom('runtime-a'),").replace('onEvent:()=>()=>{}',"onEvent:(type,fn)=>{const set=eventListeners.get(type)||new Set();set.add(fn);eventListeners.set(type,set);return()=>set.delete(fn);}");
 sdk+='\nexport const emitCompletion=event=>{for(const fn of eventListeners.get("message.complete")||[])fn(event);};\n';
 let entry=await readFile(path.join(here,'important_browser_entry.js'),'utf8');
 entry+='\nimport {emitCompletion} from "./important_sdk_fixture.js"; window.importantFixture.complete=emitCompletion;window.importantFixture.connection=id=>host.state.connectionId.set(id);window.importantFixture.profile=id=>host.state.profile.set(id);\n';
 await writeFile(path.join(evidence,'sdk-boundary-fixture.js'),sdk);await writeFile(path.join(evidence,'entry-boundary-fixture.js'),entry);
 const bundle=await build({stdin:{contents:entry,resolveDir:here,loader:'js'},write:false,bundle:true,format:'esm',platform:'browser',nodePaths:[host+'/node_modules'],alias:{'@hermes/plugin-sdk':path.join(here,'important_sdk_fixture.js'),'@':host+'/apps/desktop/src'},plugins:[{name:'event-boundary',setup(b){b.onLoad({filter:/important_sdk_fixture\.js$/},()=>({contents:sdk,loader:'js',resolveDir:here}));}}],define:{'process.env.NODE_ENV':'"production"'},logLevel:'silent'});
 const cssName=(await readdir(host+'/apps/desktop/dist/assets')).find(x=>/^main-.*\.css$/.test(x));assert.ok(cssName);const css=await readFile(host+'/apps/desktop/dist/assets/'+cssName);
 const html='<!doctype html><html lang="en"><meta charset="utf-8"><link rel="stylesheet" href="/host.css"><style>:root{--ui-text-primary:#e9e9eb;--ui-text-secondary:#a9abb3;--ui-stroke-secondary:#42444b;--ui-bg-secondary:#24262b;--ui-accent:#98c4ff;font:16px system-ui;color-scheme:dark}body{margin:0;background:#181a1f;color:var(--ui-text-primary)}button,input,select{font:inherit}button{min-height:28px}button:focus-visible,a:focus-visible,summary:focus-visible,input:focus-visible{outline:2px solid var(--ui-accent);outline-offset:3px}#root{height:100vh}*{box-sizing:border-box}</style><div id="root"></div><script type="module" src="/fixture.js"></script></html>';
 server=http.createServer(async(req,res)=>{try{
  if(req.url.startsWith('/api/plugins/elm/')){const chunks=[];for await(const b of req)chunks.push(b);const body=chunks.length?JSON.parse(Buffer.concat(chunks)):undefined;const r=await rpc({method:req.method,path:req.url,body});api.push({method:req.method,path:req.url,request:body??null,...r});res.writeHead(r.status,{'Content-Type':'application/json'});res.end(JSON.stringify(r.body));}
  else if(req.url==='/fixture.js'){res.setHeader('Content-Type','application/javascript');res.end(bundle.outputFiles[0].contents);}
  else if(req.url==='/host.css'){res.setHeader('Content-Type','text/css');res.end(css);}
  else if(req.url==='/'){res.setHeader('Content-Type','text/html');res.end(html);}else{res.statusCode=404;res.end();}
 }catch(e){res.statusCode=500;res.end(JSON.stringify({message:e.message}));}});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin='http://127.0.0.1:'+server.address().port;
 browser=await chromium.launch({headless:true,executablePath:requireQualificationPath('ELM_TEST_BROWSER'),env,args:['--no-first-run','--disable-background-networking','--disable-component-update','--disable-default-apps','--disable-sync','--no-proxy-server']});
 const cdp=await browser.newBrowserCDPSession();pids.push(...(await cdp.send('SystemInfo.getProcessInfo')).processInfo.map(x=>x.id));
 const context=await browser.newContext({viewport:{width:1440,height:1000}});await context.route('**/*',r=>{if(new URL(r.request().url()).origin===origin)return r.continue();blocked.push(r.request().url());return r.abort();});
 const page=await context.newPage();page.setDefaultTimeout(15000);page.on('pageerror',e=>pageErrors.push(e.message));
 const result=()=>page.locator('article').filter({has:page.getByRole('heading',{name:'Rollback package · partial',exact:true})});
 const saved=()=>page.getByRole('main',{name:'Important results',exact:true}).getByRole('status').filter({hasText:'Saved and verified by exact readback.'});
 const listGets=()=>api.filter(x=>x.method==='GET'&&x.path.includes('/ui/results?')).length;
 async function holdRefresh(){let entered;const started=new Promise(r=>entered=r),held=new Promise(r=>releaseHeld=r);await page.route('**/api/plugins/elm/ui/results?*',async route=>{if(new URL(route.request().url()).searchParams.get('session_id')!=='chat-a')return route.continue();const response=await route.fetch();entered();await held;return route.fulfill({response});});return started;}
 const retained=async()=>page.evaluate(()=>{
  const article=[...document.querySelectorAll('article')].find(el=>el.querySelector('h2')?.textContent==='Rollback package · partial');
  return{same:article===window.readingNode,body:article?.textContent.includes('Signature verification is still blocked.'),expanded:article?.querySelector('[aria-expanded]')?.getAttribute('aria-expanded'),identity:article?.querySelector('details')?.open,copy:article?.textContent.includes('Copied full result.'),deleting:!!article?.querySelector('[aria-label="Confirm result deletion"]'),selected:document.querySelector('[aria-label="Select skill fictional-owned"]')?.checked,review:!!document.querySelector('[aria-label="Confirm selected native updates"]')};
 });
 const expected={same:true,body:true,expanded:'true',identity:true,copy:true,deleting:true,selected:true,review:true};
 await check('Real API pages 100 + 1: opening oldest unread result keeps all 101 rows and full body',async()=>{
  for(let i=0;i<100;i++)await call('POST','/ui/results',{session_id:'chat-a',title:'Newer output '+i,body:'Synthetic recent output '+i,kind:'progress'});
  await page.goto(origin);await page.getByRole('button',{name:'Load older results',exact:true}).waitFor();assert.equal(await page.locator('article').count(),100);assert.equal(await result().count(),0);
  await page.getByRole('button',{name:'Load older results',exact:true}).click();await result().waitFor();assert.equal(await page.locator('article').count(),101);
  await result().getByRole('button',{name:'View result',exact:true}).click();await saved().waitFor();
  assert.equal(await page.locator('article').count(),101);assert.match(await result().innerText(),/Viewed/);
  assert.equal(await result().locator('div[style*="pre-wrap"]').textContent(),ready.seed.result.body);
  assert.equal((await call('GET','/ui/results/'+ready.seed.result.id+'?session_id=chat-a')).result.status,'viewed');
  await result().scrollIntoViewIfNeeded();await page.screenshot({path:path.join(evidence,'wide-paginated-older.png')});
  return{loaded:101,result_id:ready.seed.result.id};
 });
 await check('Explicit own detail outside first 100 opens exact body and acknowledges only on Mark read',async()=>{
  await page.reload();await page.getByRole('button',{name:'Load older results',exact:true}).waitFor();assert.equal(await result().count(),0);
  await page.evaluate(id=>window.importantFixture.directive(id),ready.seed.result.id);
  await page.getByRole('button',{name:'Open saved result in Important results',exact:true}).click();await result().getByRole('button',{name:'Hide result',exact:true}).waitFor();
  assert.equal(await result().locator('div[style*="pre-wrap"]').textContent(),ready.seed.result.body);
  await result().getByRole('button',{name:'Mark read',exact:true}).click();await saved().waitFor();
  assert.equal((await call('GET','/ui/results/'+ready.seed.result.id+'?session_id=chat-a')).result.status,'read');
 });
 await check('Unrelated session/profile/connection completions leave active disclosure and update review untouched',async()=>{
  await page.getByLabel('Show update controls',{exact:true}).click();await saved().waitFor();await page.getByRole('heading',{name:'Updates',exact:true}).waitFor();
  await page.getByRole('button',{name:'Check native updates',exact:true}).click();await page.getByLabel('Select skill fictional-owned',{exact:true}).waitFor();
  await page.getByLabel('Select skill fictional-owned',{exact:true}).check();await page.getByRole('button',{name:'Review 1 selected update',exact:true}).click();
  await result().getByRole('button',{name:'Copy full result',exact:true}).click();await result().getByText('Copied full result.',{exact:true}).waitFor();
  await result().getByText('Saved result identity',{exact:true}).click();await result().getByRole('button',{name:'Delete',exact:true}).click();
  await result().evaluate(el=>window.readingNode=el);const before=listGets();
  await page.evaluate(()=>{for(const e of [{session_id:'chat-b'},{session_id:'chat-a',profile:'other'},{session_id:'chat-a',connectionId:'remote'}])window.importantFixture.complete(e);});
  await page.waitForTimeout(100);assert.equal(listGets(),before);assert.deepEqual(await retained(),expected);
  assert.equal(api.some(x=>x.path.endsWith('/updates/apply')),false);return{unrelated_events:3,list_requests_added:0};
 });
 await check('Same-owner runtime completion preserves nodes/disclosures/detail/update selection both pending and reconciled',async()=>{
  const made=await call('POST','/ui/results',{session_id:'chat-a',title:'New background publication',body:'New real saved result while reading.',kind:'partial'});
  const started=holdRefresh();await page.evaluate(()=>window.importantFixture.complete({session_id:'runtime-a',profile:'default',connectionId:'local'}));await(await started);
  await page.getByRole('status').filter({hasText:'previous view remains visible'}).waitFor();assert.deepEqual(await retained(),expected);
  releaseHeld();await page.getByRole('status').filter({hasText:'previous view remains visible'}).waitFor({state:'hidden'});await page.unroute('**/api/plugins/elm/ui/results?*');releaseHeld=undefined;
  await page.getByRole('heading',{name:'New background publication',exact:true}).waitFor();assert.deepEqual(await retained(),expected);
  assert.equal((await call('GET','/ui/results/'+made.result.id+'?session_id=chat-a')).exists,true);
  await result().scrollIntoViewIfNeeded();await page.screenshot({path:path.join(evidence,'wide-background-retained.png')});return{rendered:await page.locator('article').count(),detail_id:ready.seed.result.id};
 });
 await check('Refresh error retains previous reading/review state with writes disabled until explicit reconciliation',async()=>{
  await page.route('**/api/plugins/elm/ui/results?*',r=>r.fulfill({status:503,json:{message:'Synthetic offline refresh failure'}}));
  await page.evaluate(()=>window.importantFixture.complete({session_id:'chat-a'}));await page.getByRole('main',{name:'Important results',exact:true}).getByRole('alert').filter({hasText:'Synthetic offline refresh failure'}).waitFor();
  assert.deepEqual(await retained(),expected);assert.equal(await result().getByRole('button',{name:'Dismiss',exact:true}).isDisabled(),true);
  await page.unroute('**/api/plugins/elm/ui/results?*');await page.getByRole('button',{name:'Refresh results',exact:true}).click();
  await result().getByRole('button',{name:'Dismiss',exact:true}).waitFor({state:'visible'});await page.waitForFunction(()=>![...document.querySelectorAll('article button')].find(x=>x.textContent==='Dismiss')?.disabled);assert.deepEqual(await retained(),expected);
 });
 await check('Final wide/narrow render uses host components without horizontal overflow and keeps reading state',async()=>{
  const measures=[];
  for(const width of [1440,360,320]){await page.setViewportSize({width,height:1000});await result().scrollIntoViewIfNeeded();
   const measure=await result().locator('div[style*="pre-wrap"]').evaluate(el=>({viewport:window.innerWidth,document:document.documentElement.scrollWidth,body:el.scrollWidth,bodyClient:el.clientWidth,font:getComputedStyle(el).fontSize,lineHeight:getComputedStyle(el).lineHeight}));
   assert.ok(measure.document<=width);assert.ok(measure.body<=measure.bodyClient+1);assert.deepEqual(await retained(),expected);measures.push(measure);
   await page.screenshot({path:path.join(evidence,`final-reading-${width}.png`)});
  }
  await page.getByRole('group',{name:'Confirm selected native updates',exact:true}).scrollIntoViewIfNeeded();await page.screenshot({path:path.join(evidence,'final-update-review-320.png')});
  await writeFile(path.join(evidence,'render-measurements.json'),JSON.stringify(measures,null,2));return measures;
 });
 await check('Real session/owner/profile/connection/gateway/epoch changes clear content; delayed former-session refresh stays rejected',async()=>{
  const started=holdRefresh();await page.evaluate(()=>window.importantFixture.complete({session_id:'chat-a'}));await(await started);
  await page.evaluate(()=>window.importantFixture.session('chat-b'));await page.getByText('No saved results in this view.',{exact:true}).waitFor();
  assert.equal(await result().count(),0);assert.equal(await page.getByRole('heading',{name:'Updates',exact:true}).count(),0);
  releaseHeld();await page.unrouteAll({behavior:'wait'});releaseHeld=undefined;await page.waitForTimeout(100);assert.equal(await result().count(),0);
  await page.evaluate(()=>window.importantFixture.session('chat-a'));await page.getByRole('heading',{name:'Updates',exact:true}).waitFor();
  for(const [method,foreign,normal] of [['owner','other','default'],['profile','other','default'],['connection','remote','local'],['gateway','closed','open']]){
   await page.evaluate(([m,v])=>window.importantFixture[m](v),[method,foreign]);await page.getByRole('alert').first().waitFor();assert.equal(await page.locator('article').count(),0);
   await page.evaluate(([m,v])=>window.importantFixture[m](v),[method,normal]);await page.getByRole('heading',{name:'Updates',exact:true}).waitFor();
  }
  await page.evaluate(()=>window.importantFixture.epoch());await page.getByRole('heading',{name:'Updates',exact:true}).waitFor();
  assert.equal(await result().count(),0);assert.equal(await page.getByRole('group',{name:'Confirm selected native updates',exact:true}).count(),0);
  const reopened=await rpc({control:'reopen'});assert.equal(reopened.body.memory_root_exists,false);assert.equal(reopened.body.result.counts.read,1);
 });
 assert.deepEqual(pageErrors,[]);await page.evaluate(()=>window.importantFixture.dispose());
}catch(e){failure=e;console.error(e.stack);}
finally{
 releaseHeld?.();if(browser)await browser.close();if(server){server.closeAllConnections();await new Promise(r=>server.close(r));}
 if(child){child.stdin.end(JSON.stringify({control:'close'})+'\n');await new Promise(r=>{if(child.exitCode!==null)return r();const t=setTimeout(()=>{child.kill();r();},10000);child.once('exit',()=>{clearTimeout(t);r();});});}
 let alive=[];for(let i=0;i<20;i++){alive=[...new Set(pids)].filter(pid=>{try{process.kill(pid,0);return true;}catch{return false;}});if(!alive.length)break;await new Promise(r=>setTimeout(r,250));}
 let cleanup={scratch,owned_pids:[...new Set(pids)],remaining_pids:alive,removed:false};
 if(!alive.length){try{await rm(scratch,{recursive:true,force:true});cleanup.removed=true;}catch(e){cleanup.error=e.message;}}
 const report={lane:'Isolated Headless Edge, actual candidate ASGI/store/publisher and native host components/checker; public SDK identity/event/navigation stand-in. No live activation, authenticated host mount or update application.',results,passed:results.filter(r=>r.pass).length,failed:results.filter(r=>!r.pass).length,pageErrors,blocked,fatal:failure?.stack||null,hashes,cleanup};
 await writeFile(path.join(evidence,'results.json'),JSON.stringify(report,null,2));await writeFile(path.join(evidence,'api-log.json'),JSON.stringify(api,null,2));await writeFile(path.join(evidence,'python-stderr.txt'),stderr);console.log(JSON.stringify({evidence,passed:report.passed,failed:report.failed,fatal:report.fatal,cleanup}));process.exitCode=failure||alive.length||!cleanup.removed?1:0;
}
