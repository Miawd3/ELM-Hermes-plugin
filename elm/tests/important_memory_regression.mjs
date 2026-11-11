import {requireQualificationPath,qualificationScratch,qualificationPython} from './qualification_paths.mjs';
// Runs the frozen memory-inspector suites against THIS candidate; no old writes.
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {readFile,writeFile,mkdir,rm} from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
const host=requireQualificationPath('HERMES_STOCK_SOURCE');
const old=requireQualificationPath('ELM_LEGACY_UI_TESTS');
const here=path.dirname(fileURLToPath(import.meta.url)),root=path.resolve(here,'../../..');
const label=process.argv[2];assert.match(label,/^[a-z0-9-]+$/);
const evidence=path.join(root,'evidence/important-updates-ui',label),scratch=qualificationScratch('important-updates-ui')+label;
await mkdir(evidence);await mkdir(scratch);
const require=createRequire(host+'/apps/desktop/package.json'),{build}=require('esbuild'),{JSDOM}=require('jsdom');
const plugin=path.resolve(here,'../desktop/plugin.js').replaceAll('\\','/');
const built=await build({stdin:{contents:`export {default as plugin} from ${JSON.stringify(plugin)}; export * from ${JSON.stringify(plugin)}; export * as React from 'react'; export {createRoot} from 'react-dom/client'; export {act} from 'react'; export {fireEvent} from '@testing-library/dom'; export {host,atom,activationEpoch} from ${JSON.stringify(old+'/sdk-fixture.js')};`,resolveDir:host,loader:'js'},bundle:true,write:false,format:'esm',platform:'browser',nodePaths:[host+'/node_modules'],alias:{'@hermes/plugin-sdk':old+'/sdk-fixture.js','@':host+'/apps/desktop/src','react':path.dirname(require.resolve('react/package.json')),'react-dom':path.dirname(require.resolve('react-dom/package.json'))},logLevel:'silent'});
await writeFile(path.join(scratch,'fixture.mjs'),built.outputFiles[0].contents);
const dom=new JSDOM('<div id="root"></div>',{url:'http://127.0.0.1/'});
for(const key of ['window','document','HTMLElement','Event','MouseEvent'])globalThis[key]=dom.window[key];globalThis.IS_REACT_ACT_ENVIRONMENT=true;
const module=await import(pathToFileURL(path.join(scratch,'fixture.mjs'))),results=[];
async function test(name,fn){try{await fn();results.push({name,pass:true});console.log('PASS '+name);}catch(e){results.push({name,pass:false,error:e.stack});console.error('FAIL '+name+'\n'+e.stack);}}
const suites=[['tests.mjs','runTests'],['readback-tests.mjs','runReadbackTests'],['real-contract-tests.mjs','runRealContractTests'],['privacy-create-tests.mjs','runPrivacyCreateTests']];
for(const [file,fn] of suites){const m=await import(pathToFileURL(old+'/'+file));await m[fn]({module,test,assert});}
dom.window.close();await rm(scratch,{recursive:true,force:true});
const report={lane:'Frozen memory-inspector regression suites run against the NEW candidate, real React/JSDOM and SDK/API boundary fixture',source_sha256:createHash('sha256').update(await readFile(plugin)).digest('hex'),results,passed:results.filter(r=>r.pass).length,failed:results.filter(r=>!r.pass).length,scratch_removed:true};
await writeFile(path.join(evidence,'results.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({evidence,passed:report.passed,failed:report.failed}));process.exit(report.failed?1:0);
