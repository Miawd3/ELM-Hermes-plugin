import {readFile} from 'node:fs/promises';
import test from 'node:test';
import assert from 'node:assert/strict';
const original=await readFile(new URL('../../elm/desktop/plugin.js',import.meta.url),'utf8');
async function load(sdk={}) {
 globalThis.__reviewSdk={host:{state:{},request(){throw Error('No RPC permitted');}},TRANSCRIPT_DIRECTIVE_AREA:'transcript.directives',ROUTES_AREA:'routes',SIDEBAR_NAV_AREA:'sidebar',...sdk};
 const source=original.replace("import * as SDK from '@hermes/plugin-sdk';",'const SDK=globalThis.__reviewSdk;').replace("import { createElement as h, useLayoutEffect, useState, useSyncExternalStore } from 'react';",'const h=(type,props,...children)=>({type,props:props||{},children}),useState=x=>[x,()=>{}],useSyncExternalStore=(_s,g)=>g(),useLayoutEffect=()=>{};');
 return import('data:text/javascript;base64,'+Buffer.from(source+'\n//'+Math.random()).toString('base64'));
}
test('throwing preference storage cannot disable all existing ELM registration',async()=>{
 const m=await load(), registrations=[],stops=[];
 assert.doesNotThrow(()=>m.default.register({register:x=>registrations.push(x),onDispose:x=>stops.push(x),storage:{get(){throw Error('private-storage-error');},set(){throw Error('private-write-error');}}}));
 assert.equal(registrations.filter(x=>x.area==='routes').length,2);
 stops.forEach(stop=>stop());
});
test('explicit safe link only; hostile URLs never produce an opening handler',async()=>{
 const m=await load(),opened=[];const render=m.richMarkdownComponents({os:{openExternal:url=>opened.push(url)}}).a;
 for(const href of ['javascript:alert(1)','data:text/html,<script>x</script>','file:///secret','https://user:pass@example.com/','https://example.com/\\evil','https://example.com/\nsecret']) {
  const node=render({href,children:'untrusted'}); assert.equal(node.props.onClick,undefined);
 }
 const node=render({href:'https://example.com/evidence',children:'declared label'});
 assert.deepEqual(opened,[]);node.props.onClick();assert.deepEqual(opened,['https://example.com/evidence']);
});
test('inline directive admits only finite presentation fields, never action metadata',async()=>{
 const m=await load();
 for(const attrs of [{category:'approved',text:'x'},{category:'final',action:'delete'},{category:'answer',source:'private-root'},{category:'answer',text:'x'.repeat(1201)},{category:'answer',text:'\u0000'}]) assert.throws(()=>m.parseRichDirective(attrs));
 const value=m.parseRichDirective({category:'final',title:'<img src=x onerror=evil()>',text:'::other-action{confirm="true"}'});
 assert.equal(value.category,'final');assert.equal(value.summary,'::other-action{confirm="true"}');assert.deepEqual(value.sections,[]);assert.deepEqual(value.sources,[]);
});
test('render component does not fetch images or invoke remote opening implicitly',async()=>{
 const m=await load();let calls=0;const c=m.richMarkdownComponents({os:{openExternal(){calls++;}}});
 const image=c.img({src:'https://example.com/tracker',alt:'<svg onload=evil>'});
 assert.equal(image.type,'span');assert.equal(image.props.src,undefined);assert.equal(calls,0);
 const doc=m.normalizeDocument({title:'<script>evil</script>',summary:'[run](javascript:evil)',sections:[],category:'question'});
 const tree=m.RichAnswerReader({document:doc,ctx:{os:{openExternal(){calls++;}}}});assert.equal(tree.type,'article');assert.equal(calls,0);
});
