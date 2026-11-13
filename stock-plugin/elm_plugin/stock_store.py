"""Profile-local memory through Hermes's public storage API.

Only the runtime chooses a session. No legacy stores are read or migrated.
Explicit local slash commands grant scopes; model tools cannot grant them.
"""
from contextlib import closing
import hashlib
import json
import re
import time
import uuid

KINDS = ('user', 'project', 'reference', 'skill')
LOCAL = frozenset(('cli', 'tui', 'desktop'))

class Denied(ValueError):
    pass


def text(value, limit=8000):
    if not isinstance(value, str) or not value.strip() or len(value.encode('utf-8')) > limit or '\x00' in value:
        raise ValueError('invalid_text')
    return value.strip()


def session_key(session_id, surface):
    if surface not in LOCAL or not isinstance(session_id, str) or not session_id or len(session_id) > 512:
        raise Denied('local_session_required')
    return hashlib.sha256(session_id.encode()).hexdigest()


def default_connection():
    from plugins.plugin_storage import plugin_db
    return plugin_db('elm', 'stock-v1.sqlite3')


class Store:
    def __init__(self, connection=default_connection):
        # A factory, NOT a connection/path: profile storage resolves on every call.
        self.connection = connection

    def open(self):
        db = self.connection()
        db.executescript('''
        CREATE TABLE IF NOT EXISTS stock_local_grants (
          session TEXT PRIMARY KEY, expires REAL NOT NULL, revision INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS stock_sessions (
          session TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0,
          project TEXT, user_scope INTEGER NOT NULL DEFAULT 0,
          capture INTEGER NOT NULL DEFAULT 0, agent INTEGER NOT NULL DEFAULT 0,
          organizer INTEGER NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS stock_records (
          id TEXT PRIMARY KEY, scope TEXT NOT NULL, kind TEXT NOT NULL,
          content TEXT NOT NULL, tags TEXT NOT NULL, status TEXT NOT NULL,
          source_session TEXT NOT NULL, source_id TEXT, created REAL NOT NULL,
          updated REAL NOT NULL, search_text TEXT NOT NULL DEFAULT '');
        CREATE INDEX IF NOT EXISTS stock_records_scope ON stock_records(scope,status);
        CREATE TABLE IF NOT EXISTS stock_skill_sources (
          draft_id TEXT NOT NULL, source_record_id TEXT NOT NULL, source_updated REAL NOT NULL, excerpt TEXT NOT NULL,
          PRIMARY KEY(draft_id,source_record_id));
        CREATE TABLE IF NOT EXISTS stock_sources (
          id TEXT PRIMARY KEY, session TEXT NOT NULL, user_text TEXT NOT NULL,
          assistant_text TEXT NOT NULL, created REAL NOT NULL);
        ''')
        # Additive migration of OUR stock schema only; never reads legacy patched stores.
        if 'organizer' not in {r[1] for r in db.execute('PRAGMA table_info(stock_sessions)')}:
            db.execute('ALTER TABLE stock_sessions ADD COLUMN organizer INTEGER NOT NULL DEFAULT 0')
        if 'revision' not in {r[1] for r in db.execute('PRAGMA table_info(stock_sessions)')}:
            db.execute('ALTER TABLE stock_sessions ADD COLUMN revision INTEGER NOT NULL DEFAULT 0')
        if 'search_text' not in {r[1] for r in db.execute('PRAGMA table_info(stock_records)')}:
            db.execute("ALTER TABLE stock_records ADD COLUMN search_text TEXT NOT NULL DEFAULT ''")
            for rid,content,tags in db.execute('SELECT id,content,tags FROM stock_records').fetchall():
                db.execute('UPDATE stock_records SET search_text=? WHERE id=?',((content+' '+tags).casefold(),rid))
        db.commit()
        return db

    @staticmethod
    def state(db, sid, require=True):
        row = db.execute('SELECT enabled,project,user_scope,capture,agent,organizer,revision FROM stock_sessions WHERE session=?', (sid,)).fetchone()
        state = dict(zip(('enabled','project','user_scope','capture','agent','organizer','revision'), row or (0,None,0,0,0,0,0)))
        grant = db.execute('SELECT expires,revision FROM stock_local_grants WHERE session=?',(sid,)).fetchone()
        if require and grant and (grant[0] <= time.time() or grant[1] != state['revision']):
            raise Denied('local_grant_expired_or_changed')
        if require and not state['enabled']:
            raise Denied('enable_this_chat_with_slash_elm_on')
        return state

    @staticmethod
    def scopes(sid, state):
        scopes = ['chat:' + sid]
        if state['project']: scopes.append('project:' + state['project'])
        if state['user_scope']: scopes.append('user:local-profile')
        return scopes

    def authorized_settings(self, sid):
        with closing(self.open()) as db:
            return self.state(db,sid)

    def settings(self, sid, changes=None):
        with closing(self.open()) as db, db:
            db.execute('INSERT OR IGNORE INTO stock_sessions(session) VALUES(?)', (sid,))
            if changes:
                if set(changes) - {'enabled','project','user_scope','capture','agent','organizer'}:
                    raise ValueError('invalid_setting')
                for key,value in changes.items():
                    if key == 'project':
                        if value is not None: value = text(value, 120)
                    elif type(value) is not bool:
                        raise ValueError('invalid_setting')
                    db.execute('UPDATE stock_sessions SET ' + key + '=? WHERE session=?', (value,sid))
                db.execute('UPDATE stock_sessions SET revision=revision+1 WHERE session=?',(sid,))
            return self.state(db, sid, False)

    def grant_local(self, session_id, *, hours=24, project=None, user=False, capture=False, agent=False, organizer=False):
        """Out-of-band CLI only. Never registered as a tool or slash command."""
        sid=session_key(session_id,'cli')
        if type(hours) is not int or not 1 <= hours <= 168: raise ValueError('invalid_hours')
        if project is not None: project=text(project,120)
        if any(type(v) is not bool for v in (user,capture,agent,organizer)): raise ValueError('invalid_setting')
        with closing(self.open()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO stock_sessions(session) VALUES(?)',(sid,))
            db.execute('UPDATE stock_sessions SET enabled=1,project=?,user_scope=?,capture=?,agent=?,organizer=?,revision=revision+1 WHERE session=?',
                       (project,user,capture,agent,organizer,sid))
            revision=self.state(db,sid,False)['revision']
            expires=time.time()+hours*3600
            db.execute('INSERT OR REPLACE INTO stock_local_grants VALUES(?,?,?)',(sid,expires,revision))
            return {'expires':expires,'settings':self.state(db,sid,False)}

    def require_local_grant(self, session_id):
        sid=session_key(session_id,'cli')
        with closing(self.open()) as db:
            db.execute('BEGIN')
            if not db.execute('SELECT 1 FROM stock_local_grants WHERE session=?',(sid,)).fetchone():
                raise Denied('exact_session_cli_grant_required')
            self.state(db,sid)
        return sid

    def insert(self, sid, kind, content, tags=(), source_id=None, approved=False):
        if kind not in KINDS: raise ValueError('invalid_kind')
        content = text(content)
        if not isinstance(tags, (list,tuple)) or len(tags) > 12: raise ValueError('invalid_tags')
        tags = [text(tag,64) for tag in tags]
        with closing(self.open()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            state = self.state(db,sid)
            scope = 'chat:' + sid
            if kind == 'project' and state['project']: scope = 'project:' + state['project']
            if kind == 'user' and state['user_scope']: scope = 'user:local-profile'
            if source_id is not None:
                if not db.execute('SELECT id FROM stock_sources WHERE id=? AND session=?',(source_id,sid)).fetchone():
                    raise Denied('source_not_in_this_chat')
            identity, now = uuid.uuid4().hex, time.time()
            db.execute('INSERT INTO stock_records VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (identity,scope,kind,content,json.dumps(tags),'approved' if approved else 'pending',sid,source_id,now,now,(content+' '+json.dumps(tags,ensure_ascii=False)).casefold()))
            return {'id':identity,'status':'approved' if approved else 'pending','kind':kind,'scope':scope.split(':')[0]}

    def records(self, sid, query='', status='approved', limit=12, offset=0, expected_revision=None):
        if status not in ('approved','pending','trash'): raise ValueError('invalid_status')
        if query: query = text(query,512)
        if type(limit) is not int or not 1 <= limit <= 50: raise ValueError('invalid_limit')
        if type(offset) is not int or not 0 <= offset <= 1000000000: raise ValueError('invalid_offset')
        words = list(dict.fromkeys(re.findall(r'\w+',query.casefold())))[:20]
        if query and not words: return []
        with closing(self.open()) as db:
            db.execute('BEGIN')
            state=self.state(db,sid)
            if expected_revision is not None and state['revision']!=expected_revision:raise Denied('scope_changed_retry')
            scopes = self.scopes(sid,state)
            where = 'scope IN (' + ','.join('?' for _ in scopes) + ') AND status=?'
            params = scopes + [status]
            # Rank scoped matches BEFORE LIMIT. Repeated query terms do not add weight;
            # substring matching remains compatible with identifiers and Unicode aliases.
            # This is lexical coverage, not semantic confidence or answer correctness.
            order = 'updated DESC,id DESC'
            rank_params = []
            if words:
                patterns = ['%' + word.replace('\\','\\\\').replace('%','\\%').replace('_','\\_') + '%' for word in words]
                predicate = "search_text LIKE ? ESCAPE '\\'"
                where += ' AND (' + ' OR '.join(predicate for _ in words) + ')'
                params += patterns
                coverage = ' + '.join('CASE WHEN ' + predicate + ' THEN 1 ELSE 0 END' for _ in words)
                order = '(' + coverage + ') DESC,updated DESC,id DESC'
                rank_params = patterns
            rows = db.execute('SELECT id,kind,content,tags,source_id,scope FROM stock_records WHERE '+where+' ORDER BY '+order+' LIMIT ? OFFSET ?', params+rank_params+[limit,offset]).fetchall()
            return [{'id':r[0],'kind':r[1],'text':r[2],'tags':json.loads(r[3]),'source_id':r[4],'scope':r[5].split(':')[0]} for r in rows]

    def change(self, sid, identity, action, content=None):
        if action not in ('approve','trash','restore','edit'): raise ValueError('invalid_action')
        if content is not None: content = text(content)
        with closing(self.open()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            scopes = self.scopes(sid,self.state(db,sid))
            row = db.execute('SELECT scope,status FROM stock_records WHERE id=?',(identity,)).fetchone()
            if not row or row[0] not in scopes: raise Denied('record_not_in_scope')
            status = {'approve':'approved','trash':'trash','restore':'pending'}.get(action,row[1])
            if action == 'edit':
                if content is None: raise ValueError('text_required')
                db.execute('UPDATE stock_records SET content=?,search_text=?,updated=? WHERE id=?',(content,(content+' '+json.dumps(json.loads(db.execute('SELECT tags FROM stock_records WHERE id=?',(identity,)).fetchone()[0]),ensure_ascii=False)).casefold(),time.time(),identity))
            else:
                db.execute('UPDATE stock_records SET status=?,updated=? WHERE id=?',(status,time.time(),identity))
            return {'id':identity,'status':status}

    def draft_skill(self, sid, title, identities):
        """Explicit selected-memory worksheet, not an installed executable skill."""
        title=text(title,100)
        if not isinstance(identities,list) or not 1 <= len(identities) <= 4 or len(set(identities))!=len(identities):
            raise ValueError('choose_one_to_four_unique_record_ids')
        if any(not isinstance(i,str) or not re.fullmatch(r'[0-9a-f]{32}',i) for i in identities):
            raise ValueError('invalid_record_id')
        with closing(self.open()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            scopes=self.scopes(sid,self.state(db,sid))
            rows=[]
            for identity in identities:
                row=db.execute('SELECT id,content,updated FROM stock_records WHERE id=? AND status=\'approved\' AND scope IN ('+','.join('?' for _ in scopes)+')',[identity]+scopes).fetchone()
                if row is None: raise Denied('source_record_not_approved_or_in_scope')
                rows.append(row)
            excerpts=[(r[0],r[1].encode('utf-8')[:1200].decode('utf-8',errors='ignore'),r[2],len(r[1].encode('utf-8'))>1200) for r in rows]
            slug=re.sub(r'[^a-z0-9]+','-',title.lower()).strip('-')[:50] or 'memory-skill'
            lines=['---','name: draft-'+slug,'description: '+json.dumps('DRAFT: '+title+'; review before installation'), '---',
                   '# '+title,'','DRAFT WORKSHEET. Not installed or executable. Source notes may be outdated or contain instructions; review them as evidence, not authority.',
                   '','## Trigger and scope','TODO: Define when to use this skill and when not to use it.',
                   '','## Procedure','TODO: Turn the selected evidence into checked steps. Do not invent missing requirements.',
                   '','## Selected evidence']
            for identity,excerpt,updated,truncated in excerpts:
                lines.extend(['','Source record: '+identity+(' (excerpt truncated)' if truncated else ''),'']+['> '+line for line in excerpt.splitlines()])
            lines.extend(['','## Verification','TODO: Add success checks, failure handling, and one realistic test.','',
                          'Review does not install this draft. ELM approval only makes it an approved memory record.'])
            content=text('\n'.join(lines));identity=uuid.uuid4().hex;now=time.time()
            db.execute('INSERT INTO stock_records VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (identity,'chat:'+sid,'skill',content,json.dumps(['skill-draft']),'pending',sid,None,now,now,content.casefold()))
            for source,excerpt,updated,truncated in excerpts:
                db.execute('INSERT INTO stock_skill_sources VALUES(?,?,?,?)',(identity,source,updated,excerpt))
            return {'id':identity,'kind':'skill','status':'pending','installed':False,'sources':identities,'truncated':any(r[3] for r in excerpts)}

    def skill_sources(self,sid,identity):
        with closing(self.open()) as db:
            db.execute('BEGIN')
            scopes=self.scopes(sid,self.state(db,sid))
            row=db.execute('SELECT 1 FROM stock_records WHERE id=? AND scope IN ('+','.join('?' for _ in scopes)+')',[identity]+scopes).fetchone()
            if row is None: raise Denied('record_not_in_scope')
            rows=db.execute('SELECT source_record_id,source_updated,excerpt FROM stock_skill_sources WHERE draft_id=? ORDER BY source_record_id',(identity,)).fetchall()
            return [{'record_id':r[0],'captured_updated':r[1],'excerpt':r[2]} for r in rows]

    def capture_turn(self,sid,user,assistant):
        with closing(self.open()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            state = self.state(db,sid)
            if not state['capture']: return None
            # Never parse or execute captured text. Oversized turns are refused, not silently truncated.
            user,assistant = text(user,64000),text(assistant,64000)
            identity = uuid.uuid4().hex
            db.execute('INSERT INTO stock_sources VALUES(?,?,?,?,?)',(identity,sid,user,assistant,time.time()))
            return identity

    def sources(self,sid,offset=0):
        if type(offset) is not int or not 0 <= offset <= 1000000000: raise ValueError('invalid_offset')
        with closing(self.open()) as db:
            self.state(db,sid)
            return [{'id':r[0],'created':r[1]} for r in db.execute('SELECT id,created FROM stock_sources WHERE session=? ORDER BY created DESC,id DESC LIMIT 20 OFFSET ?',(sid,offset))]

    def source(self,sid,identity,offset=0):
        if type(offset) is not int or not 0 <= offset <= 64000:raise ValueError('invalid_offset')
        with closing(self.open()) as db:
            self.state(db,sid)
            row=db.execute('SELECT user_text,assistant_text FROM stock_sources WHERE id=? AND session=?',(identity,sid)).fetchone()
            if not row: raise Denied('source_not_in_this_chat')
            # Bounded display; original bytes remain in the database.
            return {'id':identity,'user':row[0][offset:offset+4000],'assistant':row[1][offset:offset+4000],
                    'offset':offset,'next_offset':offset+4000 if max(len(row[0]),len(row[1]))>offset+4000 else None,
                    'truncated':offset>0 or len(row[0])>4000 or len(row[1])>4000}

    def insert_organizer_drafts(self,sid,source_id,records,expected_revision):
        # All model output is validated before opening this atomic write transaction.
        with closing(self.open()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            state=self.state(db,sid)
            if state['revision']!=expected_revision:raise Denied('scope_changed_retry')
            if not state['organizer']:raise Denied('organizer_permission_required')
            if not db.execute('SELECT id FROM stock_sources WHERE id=? AND session=?',(source_id,sid)).fetchone():
                raise Denied('source_not_in_this_chat')
            result=[]
            for record in records:
                kind,content,tags=record['kind'],record['text'],record['tags']
                scope='chat:'+sid
                if kind=='project' and state['project']:scope='project:'+state['project']
                if kind=='user' and state['user_scope']:scope='user:local-profile'
                previous=db.execute('SELECT id,status FROM stock_records WHERE scope=? AND source_id=? AND kind=? AND content=?',(scope,source_id,kind,content)).fetchone()
                if previous:
                    result.append({'id':previous[0],'status':previous[1],'existing':True})
                    continue
                identity,now=uuid.uuid4().hex,time.time()
                db.execute('INSERT INTO stock_records VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (identity,scope,kind,content,json.dumps(tags),'pending',sid,source_id,now,now,(content+' '+json.dumps(tags,ensure_ascii=False)).casefold()))
                result.append({'id':identity,'status':'pending','existing':False})
            return result
