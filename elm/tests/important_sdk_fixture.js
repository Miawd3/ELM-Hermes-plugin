export {Button} from '@/components/ui/button.tsx';
export {Input} from '@/components/ui/input.tsx';
export {Textarea} from '@/components/ui/textarea.tsx';
import {useSyncExternalStore} from 'react';
export const ROUTES_AREA='routes', SIDEBAR_NAV_AREA='sidebarNav', TRANSCRIPT_DIRECTIVE_AREA='transcript.directive';
function atom(value){const listeners=new Set();return{get:()=>value,set(v){value=v;for(const f of listeners)f();},listen(f){listeners.add(f);return()=>listeners.delete(f);}};}
export const activationEpoch=atom(0);
export const gatewayActivationEpoch=activationEpoch.get;
export const useGatewayActivationEpoch=()=>useSyncExternalStore(activationEpoch.listen,activationEpoch.get,activationEpoch.get);
export const host={state:{focusedStoredSessionId:atom('chat-a'),focusedSessionProfile:atom('default'),focusedSessionOwner:atom({profile:'default',connectionId:'local'}),profile:atom('default'),connectionId:atom('local'),gateway:atom('open')},navigate:path=>{window.lastNavigation=path;},request:async()=>{throw Error('Native gateway RPC is not mounted in the isolated browser fixture');},onEvent:()=>()=>{}};
