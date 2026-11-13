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
        if require and not state['enabled']:
            raise Denied('enable_this_chat_with_slash_elm_on')
        return state

    @staticmethod
    def scopes(sid, state):
        scopes = ['chat:' + sid]
        if state['project']: scopes.append('project:' + state['project'])
        if state['user_scope']: scopes.append('user:local-profile')
        return scopes

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
            # Parameterized LIKE, literal escaping, scope-first SQL filtering; no global scan in Python.
            if words:
                where += ' AND (' + ' OR '.join("search_text LIKE ? ESCAPE '\\'" for _ in words) + ')'
                params += ['%' + word.replace('\\','\\\\').replace('%','\\%').replace('_','\\_') + '%' for word in words]
            rows = db.execute('SELECT id,kind,content,tags,source_id,scope FROM stock_records WHERE '+where+' ORDER BY updated DESC,id DESC LIMIT ? OFFSET ?', params+[limit,offset]).fetchall()
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
