"""Explicit human creation receipts; never infer newness from first memory use."""
from contextlib import closing
import json
import math
import sqlite3
import time
import uuid
from hermes_state import SessionDB
from hermes_cli import projects_db
from .private_controls import PrivateControls, validate_settings, _decode
from .result_inbox import InboxError, _id, _revision, _text
from .workspace_service import WorkspaceService, scope_key


class PrivateCreation(PrivateControls):
    def _creation_tables(self, db):
        self._tables(db)
        db.execute('CREATE TABLE IF NOT EXISTS private_creation (id TEXT PRIMARY KEY,caller TEXT NOT NULL,payload TEXT NOT NULL,state TEXT NOT NULL,target TEXT,outcome TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS private_workspaces (id TEXT PRIMARY KEY,payload TEXT NOT NULL)')

    def _projects(self):
        conn = self.identity._projects()
        if conn is None: return []
        with closing(conn):
            return projects_db.list_projects(conn, include_archived=True)

    def overview(self, session_id):
        defaults = self.read(session_id)
        with self._connection(session_id) as (db, ctx):
            known = {r['id'] for r in db.execute('SELECT id FROM private_workspaces')} if self._exists(db, 'private_workspaces') else set()
            pending = [dict(id=r['id'],state=r['state'],target=r['target']) for r in db.execute("SELECT id,state,target FROM private_creation WHERE caller=? AND state IN ('ready','applying') LIMIT 20",(ctx['chat_id'],))] if self._exists(db,'private_creation') else []
        service=WorkspaceService(self.home)
        setup=service.store.status()['initialized']
        return dict(schema=1, context=self._context(ctx), **defaults,
                    projects=[{'id':p.id,'name':p.name,'private_workspace':p.id in known} for p in self._projects() if not p.archived],
                    capabilities={'hard_cap':False,'memory_route':'Explicit override needs existing host grants; host fallback needs separate consent'},
                    memory_setup=setup, pending=pending,
                    current_policy=service.read_policy(session_id) if setup else None)

    def begin(self, session_id, kind, project_id, name, expected_revision):
        _revision(expected_revision)
        if kind not in ('private_chat', 'workspace_member', 'private_workspace') or not isinstance(project_id, str):
            raise InboxError('invalid_payload', 'Choose an explicit private creation kind and exact project ID or empty')
        WorkspaceService(self.home)._require_setup()
        projects = self._projects()
        if project_id and not any(p.id == project_id and not p.archived for p in projects):
            raise InboxError('project_unavailable', 'Selected project does not belong to this profile')
        if kind == 'private_workspace':
            _text(name, 'workspace name', 256)
            if project_id: raise InboxError('invalid_payload', 'A new workspace has no existing target')
        elif name != '':
            raise InboxError('invalid_payload', 'Chat creation does not accept a workspace name')
        # Read only a timestamp aggregate, not transcripts or per-session content.
        with closing(sqlite3.connect((self.home/'state.db').as_uri()+'?mode=ro', uri=True)) as native:
            native.execute('PRAGMA query_only=ON')
            latest = native.execute('SELECT COALESCE(MAX(started_at),0) FROM sessions').fetchone()[0]
        now = time.time()
        with self._connection(session_id, write=True) as (db, ctx):
            self._creation_tables(db)
            defaults = self._read_defaults(db)
            if defaults['revision'] != expected_revision:
                raise InboxError('revision_conflict', 'Defaults changed before creation; refresh first')
            settings = defaults['settings']
            if kind == 'workspace_member':
                row = db.execute('SELECT payload FROM private_workspaces WHERE id=?', (project_id,)).fetchone()
                if row is None: raise InboxError('sharing_denied', 'Workspace membership defaults require an explicitly created private workspace')
                settings = _decode(row['payload'])
            ident = uuid.uuid4().hex
            entry = settings['private_workspace' if kind != 'private_chat' else 'private_chat']
            params = {'name':name,'use':False,'create_directory':False} if kind == 'private_workspace' else {'request_id':ident,'source':'gui'}
            if kind != 'private_workspace':
                if project_id: params['project_id'] = project_id
                if entry['conversation']['provider']:
                    params.update(entry['conversation'], follow_profile_config=False)
            item = dict(kind=kind, project_id=project_id, name=name, issued=now, cutoff=max(now, float(latest)),
                        defaults_revision=defaults['revision'], settings=settings, fingerprint=ctx['fingerprint'],
                        existing_projects=[p.id for p in projects])
            db.execute('INSERT INTO private_creation VALUES(?,?,?,\'ready\',NULL,NULL)',
                       (ident,ctx['chat_id'],json.dumps(item,allow_nan=False)))
        return {'schema':1,'context':self._context(ctx),'id':ident,'method':'projects.create' if kind=='private_workspace' else 'session.create','params':params,
                'meaning':'One explicit native creation; if the outcome is uncertain, never repeat it automatically'}

    def status(self, session_id, intent_id):
        _id(intent_id)
        with self._connection(session_id) as (db, ctx):
            row = db.execute('SELECT * FROM private_creation WHERE id=? AND caller=?', (intent_id,ctx['chat_id'])).fetchone() if self._exists(db,'private_creation') else None
            if row is None: raise InboxError('creation_not_found', 'No creation intent belongs to this chat')
            return {'id':intent_id,'state':row['state'],'target':row['target'],
                    'outcome':json.loads(row['outcome']) if row['outcome'] else None}

    def abandon(self, session_id, intent_id, confirm):
        _id(intent_id)
        if confirm is not True: raise InboxError('invalid_payload','Inspect the native list and explicitly confirm before closing an uncertain attempt')
        with self._connection(session_id,write=True) as (db,ctx):
            self._creation_tables(db)
            row=db.execute('SELECT state FROM private_creation WHERE id=? AND caller=?',(intent_id,ctx['chat_id'])).fetchone()
            if row is None: raise InboxError('creation_not_found','Creation intent unavailable')
            if row['state']!='applied':
                db.execute("UPDATE private_creation SET state='closed' WHERE id=? AND caller=?",(intent_id,ctx['chat_id']))
        return self.status(session_id,intent_id)

    def finish(self, session_id, intent_id, created_id):
        _id(intent_id);_text(created_id, 'exact created native ID', 256)
        with self._connection(session_id, write=True) as (db, ctx):
            self._creation_tables(db)
            row = db.execute('SELECT * FROM private_creation WHERE id=? AND caller=?', (intent_id,ctx['chat_id'])).fetchone()
            if row is None: raise InboxError('creation_not_found', 'Creation intent unavailable')
            if row['state']=='applied' and row['target']==created_id:
                return json.loads(row['outcome'])
            if row['state']!='ready':
                raise InboxError('publication_unconfirmed', 'Creation was already attempted; inspect its status, do not repeat')
            item=json.loads(row['payload'])
            item['settings'] = validate_settings(item['settings'])
            if (ctx['fingerprint']!=item['fingerprint'] or not 0 <= time.time()-item['issued'] <= 300
                    or self._read_defaults(db)['revision']!=item['defaults_revision']):
                raise InboxError('scope_changed','Creation identity/defaults changed or intent expired; no automatic retry')
            project=None
            if item['kind']=='private_workspace':
                project=next((p for p in self._projects() if p.id==created_id and not p.archived),None)
                if project is None or created_id in item['existing_projects'] or project.name!=item['name']:
                    raise InboxError('creation_refused','The native workspace is not new and exactly selected')
            else:
                target=self.identity.resolve(created_id)
                with closing(SessionDB(self.home/'state.db',read_only=True)) as native:
                    meta=native.get_session_list_row(created_id)
                if (not meta or target['chat_id']!=created_id or target['project_id']!=(item['project_id'] or None)
                        or meta['source'] not in ('gui','desktop') or meta['message_count']!=0
                        or type(meta['started_at']) not in (float,int) or not math.isfinite(meta['started_at'])
                        or meta['started_at']<=item['cutoff']):
                    raise InboxError('creation_refused','Only a genuinely new empty root chat can receive creation defaults')
                entry=item['settings']['private_workspace' if item['kind']=='workspace_member' else 'private_chat']
                if entry['conversation']['model'] and meta['model']!=entry['conversation']['model']:
                    raise InboxError('creation_refused','Native conversation model readback differs from the explicit selection')
            # Cross-store publication is not falsely called one atomic transaction.
            # Claim first; any later failure remains sticky/uncertain, never re-executed.
            db.execute("UPDATE private_creation SET state='applying',target=? WHERE id=?",(created_id,intent_id))
        try:
            service=WorkspaceService(self.home)
            if item['kind']=='private_workspace':
                def apply_workspace():
                    if self.identity.resolve(session_id)['fingerprint'] != item['fingerprint']:
                        raise InboxError('scope_changed','Creation caller moved before configuration')
                    current = next((p for p in self._projects() if p.id==created_id and not p.archived),None)
                    if current is None or current.name != item['name']:
                        raise InboxError('scope_changed','Created workspace changed before configuration')
                    service._ensure_scopes(self.identity.resolve(session_id))
                    with self._connection(session_id,write=True) as (db,_):
                        db.execute('INSERT INTO private_workspaces VALUES(?,?)',(created_id,json.dumps(item['settings'],allow_nan=False)))
                    return {'scope_id':scope_key('workspace',created_id),'private':True}
                policy=service._mutate(apply_workspace)
            else:
                def apply_chat():
                    view=service.read_policy(created_id)
                    if (self.identity.resolve(session_id)['fingerprint'] != item['fingerprint']
                            or view['identity'] != target['fingerprint']):
                        raise InboxError('scope_changed','Creation target/caller moved before configuration')
                    if view['policy_revision'] is not None or service.store.list_records(view['authored_scope_id']):
                        raise InboxError('creation_refused','The new chat already has a policy or authored records')
                    enabled=entry['workspace_reads'] and view['workspace_scope_id'] is not None
                    service.store.set_read_policy(view['authored_scope_id'],view['workspace_scope_id'] if enabled else None,None)
                    self.bind_chat_model_policy(created_id,item['settings'],item['kind'])
                    return service.read_policy(created_id)
                policy=service._mutate(apply_chat)
            observed=self.identity.resolve(created_id if item['kind']!='private_workspace' else session_id)
            if item['kind']!='private_workspace' and observed['project_id']!=(item['project_id'] or None):
                raise InboxError('scope_changed','Created chat moved during publication')
            outcome={'status':'configured','id':intent_id,'created_id':created_id,'kind':item['kind'],'policy':policy}
            with self._connection(session_id,write=True) as (db,_):
                db.execute("UPDATE private_creation SET state='applied',outcome=? WHERE id=? AND state='applying'",(json.dumps(outcome),intent_id))
            if self.status(session_id,intent_id)['outcome']!=outcome:
                raise InboxError('publication_unconfirmed','Creation configuration readback is unconfirmed')
            return outcome
        except Exception:
            raise InboxError('publication_unconfirmed','Native container exists; privacy configuration may be partial. Inspect it; do not repeat creation automatically') from None
