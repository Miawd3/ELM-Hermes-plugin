"""Stock Hermes tools and local user commands. No client edits or private APIs."""
import json
import re
import shlex
import threading
from collections import OrderedDict
from pathlib import Path
from .stock_store import Store, Denied, session_key, text, KINDS
from .public_search_agent import search

HELP = ('ELM: /elm help | diagnostics (no memory or permission checks)\n'
        'Desktop/local setup: run `hermes elm grant` in a terminal (add -p PROFILE for a named profile) and pick this chat.\n'
        'Desktop/local: /elm on cannot grant access; rerun `hermes elm grant` after /elm off.\n'
        '/elm on | off | status | pending [offset] | list [offset] | sources [offset]\n'
        '/elm private (this chat stops sharing and reading shared notes) · /elm private off\n'
        '/elm project <name|off> · /elm user on|off\n'
        '/elm capture on|off · /elm agent on|off · /elm organizer on|off\n'
        '/elm organize <source-id> (sends that source to the organizer model)\n'
        '/elm save <user|project|reference|skill> <text>\n'
        '/elm approve|trash|restore <id> · /elm edit <id> <text>\n'
        '/elm draft-skill \"Title\" <record-id> [up to four IDs] · /elm skill-sources <id>\n'
        '/elm search <query> · /elm agent-search <query> · /elm source <id> [offset]\n'
        'Local chats only. Without auto mode (`hermes elm auto on`), each new chat/branch needs its own permission.\n'
        'Approved recall is added to your conversation and may be sent to its model provider.\n'
        'Agent mode sends the search query to your configured model and may cost money. '
        'Capture saves plain-text turns locally; never enable it for secrets.')


GRANT_ERRORS = ('exact_session_cli_grant_required','local_grant_expired_or_changed','change_permissions_with_local_grant_cli',
                'elm_auto_mode_off')


def grant_hint(session_id):
    """Human next step for local chats. Only a plain ID is echoed into a shell line."""
    if isinstance(session_id, str) and re.fullmatch(r'[A-Za-z0-9._:-]{1,200}', session_id):
        return (f'ELM is not on for this chat. In a terminal run: hermes elm auto on  (all your chats) or '
                f'hermes elm grant {session_id}  (this chat only; add -p PROFILE for a named profile)')
    return 'ELM is not on for this chat. In a terminal run: hermes elm auto on  (all your chats) or hermes elm grant  and pick this chat.'


def encode(value):
    return json.dumps(value,ensure_ascii=False)


def bounded(records, byte_limit=2400):
    """Bound final memory payload independently of how many agent queries ran."""
    result, seen = [], set()
    for record in records:
        if record['id'] in seen: continue
        seen.add(record['id'])
        candidate = {k:record[k] for k in ('id','kind','text','tags','source_id','scope')}
        if len(encode(result+[candidate]).encode()) > byte_limit: continue
        result.append(candidate)
        if len(result) >= 8: break
    return result


# Automatic recall only: words this common carry no signal and used to match nearly every note.
STOPWORDS = frozenset("""
a about above after again all also am an and any are as at be because been before being below between both
but by can could did do does doing done down during each else ever every few for from further get got had
has have having he her here hers him his how i if in into is it its just like make me more most my no nor
not now of off on once only or other our ours out over own please same she should so some still such than
that the their them then there these they this those through to too under until up us very was we were what
when where which while who whom why will with would yes yet you your yours
el la los las un una y o de del en que por para con es se lo al como mas pero sus le ya
""".split())
RECALL_HISTORY_SCAN = 40
INJECTED_SESSIONS = 256


def content_terms(value):
    """Distinct meaningful words for automatic recall (casefolded, stopwords dropped)."""
    words = re.findall(r'\w+', value.casefold())
    return list(dict.fromkeys(w for w in words if w not in STOPWORDS and (len(w) >= 3 or w.isdigit())))[:20]


def needed_matches(terms):
    return 1 if len(terms) <= 2 else 2 if len(terms) <= 5 else 3


def plain_text(message):
    """User message as text: multimodal turns arrive as a list of content parts."""
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        return ' '.join(p.get('text', '') for p in message if isinstance(p, dict) and isinstance(p.get('text'), str))
    return ''


def trivial(text_value):
    try:
        from agent.memory_provider import is_trivial_prompt
        return is_trivial_prompt(text_value)
    except Exception:
        stripped = text_value.strip()
        return not stripped or stripped.startswith('/')


def history_text(history):
    parts = []
    for message in (history or [])[-RECALL_HISTORY_SCAN:]:
        if not isinstance(message, dict):
            continue
        for key in ('content', 'api_content'):
            value = message.get(key)
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                parts.append(plain_text(value))
    return '\n'.join(parts)


INJECTED_ID = re.compile(r'"id": "([0-9a-f]{32})"')
ROUTING_TERM = re.compile(r'[^\W\d_]{3,24}')  # plain words only: no numbers, codes, keys or IDs


def routing_terms(goal):
    """Up to 12 plain-word keywords of a delegated goal (stopwords, digits, tokens with digits dropped)."""
    if not isinstance(goal, str):
        return []
    words = (w for w in re.findall(r'\w+', goal.casefold()) if ROUTING_TERM.fullmatch(w))
    return list(dict.fromkeys(w for w in words if w not in STOPWORDS))[:12]


def provider_configured():
    """True when this profile's config selects ELM as memory provider (for `hermes elm doctor`)."""
    try:
        from hermes_cli.config import load_config_readonly
        memory = load_config_readonly().get('memory') or {}
        return str(memory.get('provider') or '').strip().lower() == 'elm'
    except Exception:
        return False


def provider_serving(session_id):
    """True when ELM's memory provider is live for this chat in this process: the hooks step aside."""
    from .serving import current_home, serving
    return serving(current_home(), session_id)


class Runtime:
    def __init__(self,ctx,store=None,provider_selected=provider_serving):
        self.ctx,self.store = ctx,store or Store()
        self.provider_selected = provider_selected  # (session_id) -> bool
        # Record IDs already injected per chat, so automatic recall does not repeat them
        # every turn. Process-local; cleared for a chat when its context is compacted.
        self._injected = OrderedDict()
        self._injected_lock = threading.Lock()

    def sid(self,session_id,platform=None):
        surface = platform if platform is not None else self.ctx.session_surface()
        return self.store.resolve(session_id, 'desktop' if surface == 'gui' else surface)

    def authorized(self,session_id,platform=None):
        """The chat key, only if ELM is on for this chat now (same rule as recall: grant / enabled)."""
        sid = self.sid(session_id, platform)
        self.store.authorized_settings(sid)
        return sid

    def remember_injected_from(self, sid, messages):
        """Rebuild the no-repeat set from the conversation (after a restart the process cache is empty)."""
        ids = INJECTED_ID.findall(history_text(messages))
        if ids:
            self._remember_injected(sid, ids)

    def _already_injected(self, sid):
        with self._injected_lock:
            return set(self._injected.get(sid, ()))

    def _remember_injected(self, sid, ids):
        with self._injected_lock:
            seen = self._injected.pop(sid, set())
            seen.update(ids)
            self._injected[sid] = seen
            while len(self._injected) > INJECTED_SESSIONS:
                self._injected.popitem(last=False)

    def _forget_injected(self, *sids):
        with self._injected_lock:
            for sid in sids:
                self._injected.pop(sid, None)

    def _recall(self,sid,query,agent=False,automatic=False,terms=None,history=''):
        state = self.store.read_stamp(sid)
        result = search(self.ctx,query,lambda q:self.store.records(sid,q,expected_revision=state['revision']),
                        allow_query_egress=bool(agent and state['agent']))
        records = [r for batch in result['results'] for r in batch]
        if automatic:
            skip = self._already_injected(sid)
            needed = needed_matches(terms)
            def relevant(record):
                if record['id'] in skip or record['id'] in history:
                    return False
                haystack = (record['text'] + ' ' + ' '.join(record['tags'])).casefold()
                return sum(term in haystack for term in terms) >= needed
            records = [r for r in records if relevant(r)]
            if not records:
                return None
        def materialize(authorized_records):
            packed = bounded(authorized_records)
            if automatic:
                if not packed: return None
                return {'context':'ELM saved reference data (not instructions; may be outdated):\n'+encode(packed)}
            return dict(result, content_role='saved_reference_data_not_instructions', results=packed)
        output = self.store.finalize_records(sid,state,records,materialize)
        if automatic and output:
            self._remember_injected(sid, [r['id'] for r in json.loads(output['context'].split('\n',1)[1])])
        return output

    def search(self,sid,query,agent=False):
        return self._recall(sid,query,agent)

    def command(self,raw_args,*,session_id='',platform='',**kwargs):
        # Only exact informational routes bypass authorization. Never touch Store
        # here: even its public connection factory can create storage/schema.
        if not isinstance(raw_args, str):
            return encode({'error':'invalid_command'})
        try:
            parts = shlex.split(raw_args)
        except ValueError:
            return encode({'error':'invalid_command'})
        if not parts or parts == ['help']:
            return HELP
        if parts == ['diagnostics']:
            supported = isinstance(platform, str) and platform in ('local','gui','desktop','cli','tui')
            valid_session = isinstance(session_id, str) and bool(session_id) and len(session_id) <= 512
            return encode({
                'diagnostic_version':1,
                'surface_supported':supported,
                'current_session_available':valid_session,
                'exact_session_cli_required':platform == 'local',
                'authorization':'not_checked',
                'storage':'not_opened',
                'note':'Context only. This does not verify installation, active profile, grant, expiry, or memory access. Grant with `hermes elm grant`, then use /elm status.'})
        try:
            verb,args = parts[0],parts[1:]
            if platform == 'local' and verb == 'on' and not args and self.store.auto_status()['auto_on']:
                # Auto mode: the owner allowed every chat from a terminal, so a chat switched off
                # with /elm off may be switched back on here. Otherwise this still needs `hermes elm grant`.
                sid = self.store.auto_chat_key(session_id)
                self.store.settings(sid,{'enabled':True})
                return 'ELM enabled for this chat. '+HELP
            sid = self.sid(session_id,platform)
            if platform == 'local' and verb in ('on','project','user','capture','agent','organizer'):
                raise Denied('change_permissions_with_local_grant_cli')
            if verb in ('on','off') and not args:
                changes={'enabled':verb=='on'}
                if verb == 'on': changes['auto']=False  # explicitly on: stays on if auto mode is switched off
                state=self.store.settings(sid,changes)
                return 'ELM '+('enabled for this chat. '+HELP if state['enabled'] else 'off for this chat. Saved data kept.')
            if verb == 'private' and args in ([], ['on'], ['off']):
                if args == ['off']:
                    if platform == 'local' and not self.store.auto_status()['auto_on']:
                        raise Denied('change_permissions_with_local_grant_cli')
                    self.store.settings(sid,{'user_scope':True,'share_notes':True})
                    return 'This chat uses shared memory again: it can recall notes from your other chats, and new notes here are shared.'
                self.store.settings(sid,{'user_scope':False,'share_notes':False},keep_grant=True)
                return ('This chat is private now: it no longer reads notes shared by your other chats, and new notes '
                        'and routing history from here stay in this chat. Notes it already shared stay shared. Undo: /elm private off')
            if verb == 'status' and not args:
                state=self.store.settings(sid)
                return encode(dict(state,permissions_via_cli=platform=='local',
                                   shared_memory=bool(state['user_scope'] and state['share_notes']),
                                   auto_mode=self.store.auto_status()['auto_on']))
            if verb in ('user','capture','agent','organizer') and args in (['on'],['off']):
                key={'user':'user_scope','capture':'capture','agent':'agent','organizer':'organizer'}[verb]
                result=self.store.settings(sid,{key:args[0]=='on'})
                note={'user':'Shares approved user facts with other local chats you explicitly enable for user memory.',
                      'capture':'Captures plain-text turns locally. Existing sources are retained when off.',
                      'agent':'Agent searches send only the query through Hermes; provider fees may apply.',
                      'organizer':'Explicit organize calls send the selected captured text to your organizer model; fees may apply. Drafts need review.'}[verb]
                return encode(result)+'\n'+note
            if verb=='project' and args:
                return encode(self.store.settings(sid,{'project':None if args==['off'] else ' '.join(args)}))
            if verb == 'manager' and len(args) == 1:
                data=json.loads(args[0])
                if not isinstance(data,dict): raise ValueError('invalid_manager_request')
                action=data.get('action')
                allowed={'list':{'action','status','offset'},'save':{'action','revision','store_identity','kind','text'},
                         'approve':{'action','revision','store_identity','id','version'},'trash':{'action','revision','store_identity','id','version'},'restore':{'action','revision','store_identity','id','version'}}
                if action not in allowed or set(data)!=allowed[action]: raise ValueError('invalid_manager_request')
                if action=='list': return self.store.manager_snapshot(sid,data['status'],data['offset'],materialize=encode)
                if type(data['revision']) is not int or data['revision']<0: raise ValueError('invalid_revision')
                if not isinstance(data['store_identity'],str) or not re.fullmatch(r'[a-f0-9]{32}',data['store_identity']): raise ValueError('invalid_store_identity')
                if action=='save': return encode(self.store.insert(sid,data['kind'],data['text'],approved=True,expected_revision=data['revision'],expected_store=data['store_identity']))
                if not isinstance(data['id'],str) or not re.fullmatch(r'[a-f0-9]{32}',data['id']): raise ValueError('invalid_record')
                if not isinstance(data['version'],str) or not re.fullmatch(r'[a-f0-9]{64}',data['version']): raise ValueError('invalid_record_version')
                return encode(self.store.change(sid,data['id'],action,expected_revision=data['revision'],expected_record=data['version'],expected_store=data['store_identity']))
            if verb in ('list','pending','trash') and (not args or (len(args)==1 and args[0].isdigit())):
                offset=int(args[0]) if args else 0
                rows=self.store.records(sid,status={'list':'approved','pending':'pending','trash':'trash'}[verb],offset=offset)
                return encode({'records':rows,'offset':offset,'next_offset':offset+12 if len(rows)==12 else None})
            if verb=='draft-skill' and 2 <= len(args) <= 5:
                return encode(self.store.draft_skill(sid,args[0],args[1:]))
            if verb=='skill-sources' and len(args)==1:
                return encode(self.store.skill_sources(sid,args[0]))
            if verb=='organize' and len(args)==1:
                state=self.store.authorized_settings(sid)
                if not state['enabled'] or not state['organizer']: raise Denied('enable_elm_and_organizer_first')
                source=self.store.source(sid,args[0])
                if self.store.authorized_settings(sid)['revision']!=state['revision']:raise Denied('scope_changed_retry')
                from .stock_organizer import organize
                try: records=organize(self.ctx,source)
                except Exception: return encode({'error':'organizer_failed_no_drafts_saved'})
                return encode({'drafts':self.store.insert_organizer_drafts(sid,args[0],records,state['revision']),'source_truncated':source['truncated']})
            if verb=='sources' and (not args or (len(args)==1 and args[0].isdigit())):
                offset=int(args[0]) if args else 0
                rows=self.store.sources(sid,offset)
                return encode({'sources':rows,'offset':offset,'next_offset':offset+20 if len(rows)==20 else None})
            if verb=='source' and len(args) in (1,2): return encode(self.store.source(sid,args[0],int(args[1]) if len(args)==2 else 0))
            if verb=='save' and len(args)>=2:
                return encode(self.store.insert(sid,args[0],' '.join(args[1:]),approved=True))
            if verb in ('approve','trash','restore') and len(args)==1:
                return encode(self.store.change(sid,args[0],verb))
            if verb=='edit' and len(args)>=2:
                return encode(self.store.change(sid,args[0],'edit',' '.join(args[1:])))
            if verb in ('search','agent-search') and args:
                return encode(self.search(sid,' '.join(args),agent=verb=='agent-search'))
            return HELP
        except (ValueError,TypeError) as exc:
            error = {'error':str(exc)}
            if str(exc) in GRANT_ERRORS:
                error['hint'] = grant_hint(session_id)
            elif str(exc) == 'enable_this_chat_with_slash_elm_on':
                error['hint'] = 'Type /elm on in this chat to turn ELM on.'
            return encode(error)
        except Exception:
            return encode({'error':'elm_operation_failed; saved data was not migrated'})

    def tool(self,args,*,session_id='',**kwargs):
        try:
            sid=self.sid(session_id)
            if not isinstance(args,dict): raise ValueError('invalid_request')
            action=args.get('action')
            allowed={'search':{'action','query','use_agent'},'propose':{'action','kind','text','tags','source_id'},'read_source':{'action','source_id','offset'}}
            if action not in allowed or set(args)-allowed[action]: raise ValueError('invalid_request')
            if action=='read_source': return encode(self.store.source(sid,args.get('source_id'),args.get('offset',0)))
            if action=='search':
                use_agent=args.get('use_agent',False)
                if type(use_agent) is not bool: raise ValueError('invalid_request')
                return encode(self.search(sid,args.get('query'),use_agent))
            return encode(self.store.insert(sid,args.get('kind'),args.get('text'),args.get('tags',[]),args.get('source_id')))
        except (ValueError,TypeError) as exc:
            return encode({'error':str(exc)})
        except Exception:
            return encode({'error':'elm_operation_failed'})

    def before_turn(self,*,session_id='',user_message='',conversation_history=None,**kwargs):
        try:
            if self.provider_selected(session_id):
                return None  # the memory provider recalls for this chat instead
            message = plain_text(user_message)
            if trivial(message):
                return None
            terms = content_terms(message)
            if not terms:
                return None
            sid=self.sid(session_id)
            # Automatic recall NEVER invokes a model. Only meaningful words are searched,
            # and a note must match enough of them to be injected.
            query=' '.join(terms).encode()[:512].decode('utf-8',errors='ignore').strip()
            return self._recall(sid,query,automatic=True,terms=terms,history=history_text(conversation_history))
        except Exception:
            return None

    def after_compaction(self,*,session_id='',old_session_id='',**kwargs):
        try:
            if old_session_id:
                self.store.link_rotation(old_session_id, session_id)
            # Earlier injections may have been summarized away: allow them again.
            self._forget_injected(*(self.store.resolve_quiet(i) for i in (session_id, old_session_id) if i))
        except Exception:
            return None

    def session_deleted(self,*,session_id='',reason='',deleted_ids=None,**kwargs):
        if reason == 'archive':
            return None  # archived chats can be restored; keep their memory
        try:
            ids = [i for i in (deleted_ids or []) if isinstance(i, str)] or [session_id]
            self.store.forget_sessions(ids)
        except Exception:
            return None

    def subagent_started(self,*,parent_session_id='',child_session_id='',child_goal='',**kwargs):
        """Link a child the ELM routing backend chose to its parent chat - only when ELM is on there."""
        try:
            if not (child_session_id and isinstance(child_goal, str) and child_goal.strip()):
                return None
            sid = self.authorized(parent_session_id)  # raises unless ELM is on for the parent chat
            self.store.route_started(sid, child_session_id, child_goal, routing_terms(child_goal))
        except Exception:
            return None

    def subagent_stopped(self,*,child_session_id='',child_status=None,duration_ms=0,**kwargs):
        try:
            if child_session_id:
                self.store.route_finished(child_session_id, child_status, duration_ms)
        except Exception:
            return None

    def after_turn(self,*,session_id='',user_message='',assistant_response='',**kwargs):
        try:
            if self.provider_selected(session_id):
                return None  # the memory provider's sync_turn captures for this chat instead
            self.store.capture_turn(self.sid(session_id),plain_text(user_message),plain_text(assistant_response))
        except Exception:
            return None


class _NoSessionContext:
    """For the memory loader's collector: the lifecycle hooks below never read the session surface."""
    def session_surface(self):
        return ''


def register_lifecycle_hooks(ctx):
    """Memory-only registration: delete purge and compaction carry-over must still run."""
    runtime = Runtime(_NoSessionContext())
    ctx.register_hook('post_compaction', runtime.after_compaction)
    ctx.register_hook('on_session_delete', runtime.session_deleted)
    return runtime


def register_stock(ctx):
    runtime=Runtime(ctx)
    ctx.register_auxiliary_task('elm_search',display_name='ELM Search',description='Plan memory search queries.')
    ctx.register_auxiliary_task('elm_organizer',display_name='ELM Organizer',description='Extract source excerpts for review.')
    ctx.register_command(name='elm',handler=runtime.command,description='Local memory, review and search',args_hint='<command>')
    ctx.register_tool(name='elm_memory',toolset='elm',handler=runtime.tool,schema={
        'name':'elm_memory','description':'Search permitted ELM memory or propose a draft. Never approves records or grants access. Use /elm commands for user review.',
        'parameters':{'type':'object','properties':{
            'action':{'type':'string','enum':['search','propose','read_source']},
            'query':{'type':'string'},'use_agent':{'type':'boolean'},
            'kind':{'type':'string','enum':list(KINDS)},'text':{'type':'string'},
            'offset':{'type':'integer','minimum':0},
            'tags':{'type':'array','items':{'type':'string'}},'source_id':{'type':'string'}},
            'required':['action'],'additionalProperties':False}})
    ctx.register_hook('pre_llm_call',runtime.before_turn)
    ctx.register_hook('post_llm_call',runtime.after_turn)
    ctx.register_hook('post_compaction',runtime.after_compaction)
    ctx.register_hook('on_session_delete',runtime.session_deleted)
    ctx.register_hook('subagent_start',runtime.subagent_started)
    ctx.register_hook('subagent_stop',runtime.subagent_stopped)
    try:
        from .routing import ElmDelegationProvider
    except ImportError:  # Hermes without pluggable delegation: no ELM routing backend
        ElmDelegationProvider = None
    if ElmDelegationProvider is not None and hasattr(ctx, 'register_delegation_provider'):
        # selected with delegation.backend: elm; checks the calling chat through this runtime
        ctx.register_delegation_provider(ElmDelegationProvider(runtime=runtime))
    from . import cli as elm_cli
    ctx.register_cli_command(name='elm',help='Grant ELM memory to one chat, revoke it, or list recent chats',
                             setup_fn=lambda parser:elm_cli.setup_cli(parser,runtime.store),description=elm_cli.__doc__)
    root=Path(__file__).parent.parent/'starter_skills'
    for name in ('source-research','documentation-lookup','debugging-recovery','verification','delegation','creative-continuity','rich-answers'):
        ctx.register_skill(name,root/name/'SKILL.md')
    return runtime
