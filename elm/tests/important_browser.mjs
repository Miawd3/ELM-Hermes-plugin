import {requireQualificationPath,qualificationScratch,qualificationPython} from './qualification_paths.mjs';
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
const scratch=qualificationScratch('important-updates-ui')+label;
const evidence=path.join(root,'evidence/important-updates-ui',label);
await mkdir(path.dirname(evidence),{recursive:true});await mkdir(evidence);
for(const p of ['home','tmp','runtime'])await mkdir(path.join(scratch,p),{recursive:true});
const require=createRequire(host+'/apps/desktop/package.json'),{build}=require('esbuild'),{chromium}=require('@playwright/test');
const env=Object.fromEntries(Object.entries(process.env).filter(([k])=>['SYSTEMROOT','WINDIR','PATH','PATHEXT','COMSPEC','USERPROFILE','HOMEDRIVE','HOMEPATH','LOCALAPPDATA','APPDATA'].includes(k.toUpperCase())));
Object.assign(env,{HERMES_HOME:path.join(scratch,'home'),HERMES_RUNTIME_DIR:path.join(scratch,'runtime'),TMP:path.join(scratch,'tmp'),TEMP:path.join(scratch,'tmp'),TMPDIR:path.join(scratch,'tmp'),SQLITE_TMPDIR:path.join(scratch,'tmp'),PYTHONDONTWRITEBYTECODE:'1',HERMES_DISABLE_LAZY_INSTALLS:'1',TZ:'UTC'});
let child,browser,server,failure,stderr='',serial=0;const pending=new Map(),api=[],results=[],pageErrors=[],blocked=[],pids=[],hashes={};
function rpc(value){const id=++serial;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(Error('Python bridge timeout'));},60000);pending.set(id,{resolve:x=>{clearTimeout(timer);resolve(x);},reject});child.stdin.write(JSON.stringify({id,...value})+'\n');});}
async function call(method,p,body){const r=await rpc({method,path:'/api/plugins/elm'+p,body});api.push({method,path:p,request:body??null,...r});assert.equal(r.status,200,JSON.stringify(r));return r.body;}
async function check(name,fn){try{const detail=await fn();results.push({name,pass:true,detail});console.log('PASS '+name);}catch(e){results.push({name,pass:false,error:e.stack});throw e;}}
try{
 child=spawn(qualificationPython(),['-I','-B',path.join(here,'important_browser_backend.py'),host,path.resolve(here,'..'),deps],{cwd:scratch,env,stdio:['pipe','pipe','pipe']});child.stderr.on('data',b=>stderr+=b);
 const ready=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('No Python readiness: '+stderr)),45000);createInterface({input:child.stdout}).on('line',line=>{try{const x=JSON.parse(line);if(x.ready){clearTimeout(timer);resolve(x);}else if(x.id){pending.get(x.id)?.resolve(x);pending.delete(x.id);}}catch{stderr+='\n'+line;}});child.once('exit',()=>{clearTimeout(timer);reject(Error('Python exited: '+stderr));});});pids.push(ready.pid);
 for(const f of ['../desktop/plugin.js','../elm_plugin/result_inbox.py','../elm_plugin/product_ui_api.py','important_browser.mjs','important_browser_backend.py','important_browser_entry.js','important_sdk_fixture.js']){const p=path.resolve(here,f);hashes[p]=createHash('sha256').update(await readFile(p)).digest('hex');}
 const bundle=await build({entryPoints:[path.join(here,'important_browser_entry.js')],write:false,bundle:true,format:'esm',platform:'browser',nodePaths:[host+'/node_modules'],alias:{'@hermes/plugin-sdk':path.join(here,'important_sdk_fixture.js'),'@':host+'/apps/desktop/src'},define:{'process.env.NODE_ENV':'"production"'},logLevel:'silent'});
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
 const page=await context.newPage();page.setDefaultTimeout(12000);page.on('pageerror',e=>pageErrors.push(e.message));
 const result=()=>page.locator('article').filter({has:page.getByRole('heading',{name:'Rollback package · partial',exact:true})});
 await check('Actual publisher → ASGI API → registered Important page renders quiet unread output',async()=>{
  await page.goto(origin);await page.getByRole('heading',{name:'Important results',exact:true}).waitFor();
  await result().waitFor();assert.match(await result().innerText(),/Unread/);
  assert.equal(api.filter(x=>x.path.includes('/view')||x.path.includes('/read')).length,0);
  await page.screenshot({path:path.join(evidence,'wide-unread.png'),fullPage:true});return {result_id:ready.seed.result.id};
 });
 await check('Opening marks Viewed only, literal text stays safe, copy preserves full authored output',async()=>{
  await result().getByRole('button',{name:'View result',exact:true}).click();
  await page.getByRole('status').filter({hasText:'Saved and verified by exact readback.'}).waitFor();
  assert.match(await result().innerText(),/Viewed/);assert.equal(await page.evaluate(()=>window.injected),undefined);
  await result().getByRole('button',{name:'Copy full result',exact:true}).click();
  await page.waitForFunction(()=>typeof window.copied==='string');assert.equal(await page.evaluate(()=>window.copied),ready.seed.result.body);
  const read=await call('GET','/ui/results/'+ready.seed.result.id+'?session_id=chat-a');assert.equal(read.result.status,'viewed');
  await page.setViewportSize({width:320,height:900});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
  assert.equal(await result().locator('div[style*="pre-wrap"]').evaluate(el=>el.scrollWidth<=el.clientWidth+1),true);
  await page.screenshot({path:path.join(evidence,'narrow-long-result.png'),fullPage:true});
  await page.setViewportSize({width:1440,height:1000});
 });
 await check('Read is explicit, dismiss/restore/delete readbacks survive real backend reopen',async()=>{
  await result().getByRole('button',{name:'Mark read',exact:true}).click();await page.getByRole('status').filter({hasText:'Saved and verified by exact readback.'}).waitFor();
  assert.equal((await call('GET','/ui/results/'+ready.seed.result.id+'?session_id=chat-a')).result.status,'read');
  await result().getByRole('button',{name:'Dismiss',exact:true}).click();await page.getByText('No saved results in this view.',{exact:true}).waitFor();
  await page.getByLabel('Show dismissed results',{exact:true}).check();await result().waitFor();
  await result().getByRole('button',{name:'Restore',exact:true}).click();await page.getByRole('status').filter({hasText:'Saved and verified by exact readback.'}).waitFor();
  await result().getByRole('button',{name:'Delete',exact:true}).click();assert.equal(api.filter(x=>x.method==='DELETE').length,0);
  await result().getByRole('button',{name:'Confirm delete result',exact:true}).click();await page.getByText('No saved results in this view.',{exact:true}).waitFor();
  const reopened=await rpc({control:'reopen'});assert.equal(reopened.body.memory_root_exists,false);assert.deepEqual(reopened.body.result.results,[]);
 });
 await check('Preference persistence and optional native check use the real backend, not mocked controls',async()=>{
  await page.getByLabel('Show update controls',{exact:true}).click();await page.getByRole('heading',{name:'Updates',exact:true}).waitFor();
  const prefs=await call('GET','/ui/attention?session_id=chat-a');assert.equal(prefs.attention.updates_visible,true);
  assert.equal(api.filter(x=>x.path.endsWith('/updates/check')).length,0);
  await page.getByRole('button',{name:'Check native updates',exact:true}).click();await page.getByLabel('Select skill fictional-owned',{exact:true}).waitFor();
  assert.equal(api.filter(x=>x.path.endsWith('/updates/apply')).length,0);
  const checked=api.findLast(x=>x.path.endsWith('/updates/check')).body;
  const selected=checked.rows.find(x=>x.type==='skill');assert.equal(selected.selectable,true);
  const manual=checked.rows.find(x=>x.type==='plugin'&&x.name==='manual-fixture');assert.equal(manual.status,'unknown');assert.equal(manual.selectable,false);
  await page.getByLabel('Select skill fictional-owned',{exact:true}).check();
  await page.getByRole('button',{name:'Review 1 selected update',exact:true}).click();
  assert.equal(api.filter(x=>x.path.endsWith('/updates/apply')).length,0);
  await page.getByRole('button',{name:'Confirm selected updates',exact:true}).click();
  await page.getByRole('list',{name:'Update outcomes',exact:true}).filter({hasText:'skill:fictional-owned · updated'}).waitFor();
  const installed=await call('GET','/ui/updates/installed?session_id=chat-a&type=skill&name=fictional-owned');assert.equal(installed.observed,selected.target);
  assert.equal(api.filter(x=>x.path.endsWith('/updates/apply')).length,1);
  await page.screenshot({path:path.join(evidence,'native-update-verified.png'),fullPage:true});
 });
 await check('Narrow reflow, keyboard focus, foreign owner and gateway changes clear loaded UI',async()=>{
  await page.setViewportSize({width:360,height:900});await page.screenshot({path:path.join(evidence,'narrow.png'),fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
  await page.evaluate(()=>{document.documentElement.style.setProperty('--ui-text-primary','#20242a');document.documentElement.style.setProperty('--ui-text-secondary','#4b5360');document.documentElement.style.setProperty('--ui-stroke-secondary','#727985');document.documentElement.style.setProperty('--ui-bg-secondary','#f5f6f8');document.documentElement.style.colorScheme='light';document.body.style.background='#ffffff';});
  await page.waitForTimeout(200); // Native Button transitions last 100ms.
  assert.equal(await page.getByRole('button',{name:'Refresh results',exact:true}).evaluate(el=>getComputedStyle(el).color),'rgb(32, 36, 42)');
  await page.screenshot({path:path.join(evidence,'narrow-light.png'),fullPage:true});
  await writeFile(path.join(evidence,'light-control-measurements.json'),JSON.stringify(await page.getByRole('button',{name:'Refresh results',exact:true}).evaluate(el=>({disabled:el.disabled,color:getComputedStyle(el).color,background:getComputedStyle(el).backgroundColor,opacity:getComputedStyle(el).opacity,classes:el.className,token:getComputedStyle(el).getPropertyValue('--ui-text-primary')})),null,2));
  await page.evaluate(()=>{for(const k of ['--ui-text-primary','--ui-text-secondary','--ui-stroke-secondary','--ui-bg-secondary','color-scheme'])document.documentElement.style.removeProperty(k);document.body.style.removeProperty('background');});
  await page.getByRole('button',{name:'Refresh results',exact:true}).focus();await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>document.activeElement?.tagName==='BODY'),false);
  await page.evaluate(()=>window.importantFixture.owner('other'));await page.getByRole('alert').filter({hasText:'another profile or gateway'}).waitFor();assert.equal(await page.getByRole('heading',{name:'Updates',exact:true}).count(),0);
  await page.evaluate(()=>window.importantFixture.owner('default'));await page.getByRole('heading',{name:'Updates',exact:true}).waitFor();
  await page.evaluate(()=>window.importantFixture.gateway('closed'));await page.getByRole('alert').filter({hasText:'gateway is unavailable'}).waitFor();
  await page.evaluate(()=>window.importantFixture.gateway('open'));await page.getByRole('heading',{name:'Updates',exact:true}).waitFor();
  await page.evaluate(()=>window.importantFixture.epoch());await page.getByRole('heading',{name:'Updates',exact:true}).waitFor();
  await page.evaluate(()=>window.importantFixture.session('chat-b'));await page.getByText('No saved results in this view.',{exact:true}).waitFor();assert.equal(await page.getByLabel('Show update controls').isChecked(),false);
 });
 await check('Own-result directive opens its exact saved output rather than an ordinary-message jump',async()=>{
  await page.evaluate(()=>window.importantFixture.session('chat-a'));await page.getByRole('heading',{name:'Updates',exact:true}).waitFor();
  const made=await call('POST','/ui/results',{session_id:'chat-a',title:'Directive output',body:'Exact own saved body for the directive.',kind:'blocked'});
  await page.getByRole('button',{name:'Refresh results',exact:true}).click();await page.getByRole('heading',{name:'Directive output',exact:true}).waitFor();
  await page.evaluate(id=>window.importantFixture.directive(id),made.result.id);
  await page.getByRole('button',{name:'Open saved result in Important results',exact:true}).click();
  await page.getByText('Exact own saved body for the directive.',{exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>window.lastNavigation),'/elm-important');
  await page.screenshot({path:path.join(evidence,'own-result-directive.png'),fullPage:true});
 });
 await check('Real preference commit with contradictory readback stays unconfirmed without retry',async()=>{
  const count=api.filter(x=>x.method==='POST'&&x.path.endsWith('/attention')).length;
  await page.route('**/api/plugins/elm/ui/attention?*',async route=>{const response=await route.fetch();const d=await response.json();d.attention.mode='quiet';await route.fulfill({response,json:d});});
  await page.getByLabel('Important result attention',{exact:true}).selectOption('off');
  await page.getByRole('alert').filter({hasText:'preference receipt and independent readback'}).first().waitFor();
  assert.equal(await page.getByLabel('Important result attention',{exact:true}).isDisabled(),true);
  assert.equal(api.filter(x=>x.method==='POST'&&x.path.endsWith('/attention')).length,count+1);
  assert.equal((await call('GET','/ui/attention?session_id=chat-a')).attention.mode,'off');
  await page.screenshot({path:path.join(evidence,'unconfirmed-readback.png'),fullPage:true});
  await page.unroute('**/api/plugins/elm/ui/attention?*');await page.getByRole('button',{name:'Refresh results',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('[aria-label="Important result attention"]')?.value==='off');
 });
 await check('Late real chat-a response cannot repopulate results after switching to chat-b',async()=>{
  let release,entered;const held=new Promise(r=>release=r),started=new Promise(r=>entered=r);
  await page.route('**/api/plugins/elm/ui/results?*',async route=>{const url=new URL(route.request().url());if(url.searchParams.get('session_id')==='chat-a'){const response=await route.fetch();entered();await held;return route.fulfill({response});}return route.continue();});
  await page.getByRole('button',{name:'Refresh results',exact:true}).click();await started;
  await page.evaluate(()=>window.importantFixture.session('chat-b'));await page.getByText('No saved results in this view.',{exact:true}).waitFor();
  release();await page.waitForTimeout(100);assert.equal(await page.getByRole('heading',{name:'Directive output',exact:true}).count(),0);
  assert.equal(await page.getByLabel('Show update controls').isChecked(),false);await page.unroute('**/api/plugins/elm/ui/results?*');
 });
 assert.deepEqual(pageErrors,[]);await page.evaluate(()=>window.importantFixture.dispose());
}catch(e){failure=e;console.error(e.stack);}
finally{
 if(browser)await browser.close();if(server){server.closeAllConnections();await new Promise(r=>server.close(r));}
 if(child){child.stdin.end(JSON.stringify({control:'close'})+'\n');await new Promise(r=>{if(child.exitCode!==null)return r();const t=setTimeout(()=>{child.kill();r();},10000);child.once('exit',()=>{clearTimeout(t);r();});});}
 let alive=[];for(let i=0;i<20;i++){alive=[...new Set(pids)].filter(pid=>{try{process.kill(pid,0);return true;}catch{return false;}});if(!alive.length)break;await new Promise(r=>setTimeout(r,250));}
 let cleanup={scratch,owned_pids:[...new Set(pids)],remaining_pids:alive,removed:false};
 if(!alive.length){try{await rm(scratch,{recursive:true,force:true});cleanup.removed=true;}catch(e){cleanup.error=e.message;}}
 const report={lane:'Headless Edge, real candidate ASGI/store/publisher and real native host components; SDK identity/navigation stand-in; no authenticated host mount or plugin Git update exercised',results,passed:results.filter(r=>r.pass).length,failed:results.filter(r=>!r.pass).length,pageErrors,blocked,fatal:failure?.stack||null,hashes,cleanup};
 await writeFile(path.join(evidence,'results.json'),JSON.stringify(report,null,2));await writeFile(path.join(evidence,'api-log.json'),JSON.stringify(api,null,2));await writeFile(path.join(evidence,'python-stderr.txt'),stderr);console.log(JSON.stringify({evidence,passed:report.passed,failed:report.failed,fatal:report.fatal,cleanup}));process.exitCode=failure||alive.length||!cleanup.removed?1:0;
}
