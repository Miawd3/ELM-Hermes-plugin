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


SCHEMA_VERSION = 3
_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS stock_local_grants (
      session TEXT PRIMARY KEY, expires REAL NOT NULL, revision INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS stock_sessions (
      session TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0,
      project TEXT, user_scope INTEGER NOT NULL DEFAULT 0,
      capture INTEGER NOT NULL DEFAULT 0, agent INTEGER NOT NULL DEFAULT 0,
      organizer INTEGER NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 0)""",
    """CREATE TABLE IF NOT EXISTS stock_records (
      id TEXT PRIMARY KEY, scope TEXT NOT NULL, kind TEXT NOT NULL,
      content TEXT NOT NULL, tags TEXT NOT NULL, status TEXT NOT NULL,
      source_session TEXT NOT NULL, source_id TEXT, created REAL NOT NULL,
      updated REAL NOT NULL, search_text TEXT NOT NULL DEFAULT '')""",
    "CREATE INDEX IF NOT EXISTS stock_records_scope ON stock_records(scope,status)",
    """CREATE TABLE IF NOT EXISTS stock_skill_sources (
      draft_id TEXT NOT NULL, source_record_id TEXT NOT NULL, source_updated REAL NOT NULL, excerpt TEXT NOT NULL,
      PRIMARY KEY(draft_id,source_record_id))""",
    """CREATE TABLE IF NOT EXISTS stock_sources (
      id TEXT PRIMARY KEY, session TEXT NOT NULL, user_text TEXT NOT NULL,
      assistant_text TEXT NOT NULL, created REAL NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS stock_read_epoch (
      singleton INTEGER PRIMARY KEY CHECK(singleton=1), identity TEXT NOT NULL, generation INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS stock_session_alias (
      session TEXT PRIMARY KEY, root TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS stock_session_alias_root ON stock_session_alias(root)",
    # Memory-aware routing (schema 3). No task or result text: hashed goals, agent names, a few
    # keywords of the goal (only for chats with ELM on), success and duration.
    """CREATE TABLE IF NOT EXISTS stock_route_pending (
      goal TEXT PRIMARY KEY, agent TEXT NOT NULL, chosen_by TEXT NOT NULL, created REAL NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS stock_route_runs (
      child TEXT PRIMARY KEY, agent TEXT NOT NULL, session TEXT NOT NULL, terms TEXT NOT NULL,
      created REAL NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS stock_route_outcomes (
      id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT NOT NULL, session TEXT NOT NULL,
      terms TEXT NOT NULL, ok INTEGER NOT NULL, duration_ms INTEGER NOT NULL, created REAL NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS stock_route_outcomes_session ON stock_route_outcomes(session)",
)
ROUTE_PENDING_SECONDS = 3600
ROUTE_OUTCOMES_KEPT = 2000


def _hash(session_id):
    if not isinstance(session_id, str) or not session_id or len(session_id) > 512:
        return None
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
        try:
            # Schema setup runs once per database file. Re-running DDL plus the epoch
            # INSERT on every open took a write lock on each read (4-6 times per turn).
            if db.execute('PRAGMA user_version').fetchone()[0] < SCHEMA_VERSION:
                self._migrate(db)
        except BaseException:
            db.close()
            raise
        return db

    @staticmethod
    def _migrate(db):
        db.execute('BEGIN IMMEDIATE')
        try:
            if db.execute('PRAGMA user_version').fetchone()[0] >= SCHEMA_VERSION:
                db.rollback()
                return
            for statement in _SCHEMA:
                db.execute(statement)
            # Additive migration of OUR stock schema only; never reads legacy patched stores.
            if 'organizer' not in {r[1] for r in db.execute('PRAGMA table_info(stock_sessions)')}:
                db.execute('ALTER TABLE stock_sessions ADD COLUMN organizer INTEGER NOT NULL DEFAULT 0')
            if 'revision' not in {r[1] for r in db.execute('PRAGMA table_info(stock_sessions)')}:
                db.execute('ALTER TABLE stock_sessions ADD COLUMN revision INTEGER NOT NULL DEFAULT 0')
            if 'search_text' not in {r[1] for r in db.execute('PRAGMA table_info(stock_records)')}:
                db.execute("ALTER TABLE stock_records ADD COLUMN search_text TEXT NOT NULL DEFAULT ''")
                for rid,content,tags in db.execute('SELECT id,content,tags FROM stock_records').fetchall():
                    db.execute('UPDATE stock_records SET search_text=? WHERE id=?',((content+' '+tags).casefold(),rid))
            # Persistent identity and monotonic content generation fence in-flight reads.
            db.execute("INSERT OR IGNORE INTO stock_read_epoch VALUES(1,?,0)",(uuid.uuid4().hex,))
            for event in ('INSERT','UPDATE','DELETE'):
                db.execute("CREATE TRIGGER IF NOT EXISTS stock_record_epoch_"+event.lower()+
                           " AFTER "+event+" ON stock_records BEGIN UPDATE stock_read_epoch SET generation=generation+1 WHERE singleton=1; END")
            db.execute('PRAGMA user_version=%d' % SCHEMA_VERSION)
            db.commit()
        except BaseException:
            db.rollback()
            raise

    @staticmethod
    def root(db, sid):
        """Hermes can rotate a chat to a new session ID on compression; ELM state stays on the first ID."""
        row = db.execute('SELECT root FROM stock_session_alias WHERE session=?', (sid,)).fetchone()
        return row[0] if row else sid

    def resolve(self, session_id, surface):
        """Hashed, alias-resolved chat key. Local (unified Desktop) chats also need a live grant."""
        if surface == 'local':
            return self.require_local_grant(session_id)
        sid = session_key(session_id, surface)
        with closing(self.open()) as db:
            return self.root(db, sid)

    def health(self):
        """Counts only (never content or IDs), for `hermes elm doctor` and bug reports."""
        now = time.time()
        with closing(self.open()) as db:
            count = lambda sql, *a: db.execute(sql, a).fetchone()[0]
            records = dict(db.execute('SELECT status, COUNT(*) FROM stock_records GROUP BY status').fetchall())
            return {
                'schema_version': count('PRAGMA user_version'),
                'chats_with_elm_state': count('SELECT COUNT(*) FROM stock_sessions'),
                'chats_enabled': count('SELECT COUNT(*) FROM stock_sessions WHERE enabled=1'),
                'active_local_grants': count('SELECT COUNT(*) FROM stock_local_grants WHERE expires>?', now),
                'expired_local_grants': count('SELECT COUNT(*) FROM stock_local_grants WHERE expires<=?', now),
                'records': {k: records.get(k, 0) for k in ('approved', 'pending', 'trash')},
                'captured_sources': count('SELECT COUNT(*) FROM stock_sources'),
                'compaction_links': count('SELECT COUNT(*) FROM stock_session_alias'),
                'routing_outcomes': count('SELECT COUNT(*) FROM stock_route_outcomes'),
                'integrity': db.execute('PRAGMA quick_check').fetchone()[0],
            }

    def resolve_quiet(self, session_id):
        """Alias-resolved key with no permission check; for process-local cache bookkeeping only."""
        sid = _hash(session_id)
        if sid is None:
            return None
        with closing(self.open()) as db:
            return self.root(db, sid)

    def link_rotation(self, old_session_id, new_session_id):
        """Carry one chat's ELM grant, settings and chat-only memory across a compaction rotation."""
        old, new = _hash(old_session_id), _hash(new_session_id)
        if old is None or new is None or old == new:
            return None
        with closing(self.open()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            root = self.root(db, old)
            if root == new:
                return None
            if not db.execute('SELECT 1 FROM stock_sessions WHERE session=?', (root,)).fetchone():
                return None  # this chat never used ELM; keep no metadata for it
            db.execute('INSERT OR REPLACE INTO stock_session_alias VALUES(?,?)', (new, root))
            return root

    def forget_sessions(self, session_ids):
        """Purge chat-only memory, captured sources, settings and grants of deleted chats.

        Project and shared user records survive. A chat is purged only when its first
        session ID is deleted and no later (rotated) ID of it remains.
        """
        deleted = {h for h in (_hash(i) for i in session_ids) if h}
        if not deleted:
            return []
        purged = []
        with closing(self.open()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            roots = {self.root(db, sid) for sid in deleted} | deleted
            db.executemany('DELETE FROM stock_session_alias WHERE session=?', [(sid,) for sid in deleted])
            for root in sorted(roots):
                if root not in deleted:
                    continue
                if db.execute('SELECT 1 FROM stock_session_alias WHERE root=? LIMIT 1', (root,)).fetchone():
                    continue
                scope = 'chat:' + root
                drafts = [r[0] for r in db.execute('SELECT id FROM stock_records WHERE scope=?', (scope,))]
                db.executemany('DELETE FROM stock_skill_sources WHERE draft_id=?', [(d,) for d in drafts])
                records = db.execute('DELETE FROM stock_records WHERE scope=?', (scope,)).rowcount
                sources = db.execute('DELETE FROM stock_sources WHERE session=?', (root,)).rowcount
                settings = db.execute('DELETE FROM stock_sessions WHERE session=?', (root,)).rowcount
                db.execute('DELETE FROM stock_local_grants WHERE session=?', (root,))
                db.execute('DELETE FROM stock_route_runs WHERE session=?', (root,))
                db.execute('DELETE FROM stock_route_outcomes WHERE session=?', (root,))
                if records or sources or settings:
                    purged.append({'records': records, 'sources': sources})
        return purged

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

    def read_stamp(self, sid):
        """Capture policy and content version together in this profile's database."""
        with closing(self.open()) as db:
            db.execute('BEGIN')
            state = self.state(db,sid)
            identity,generation = db.execute('SELECT identity,generation FROM stock_read_epoch WHERE singleton=1').fetchone()
            return dict(state, store_identity=identity, content_generation=generation)

    def finalize_records(self, sid, stamp, records, materialize):
        """Linearization point for recall. No model/network call inside this lock.

        Changes committed before this point invalidate the request. Already returned
        text cannot be revoked; callers must not interpret this as remote erasure.
        """
        with closing(self.open()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            state = self.state(db,sid)
            if state['revision'] != stamp['revision']:
                raise Denied('scope_changed_retry')
            identity,generation = db.execute('SELECT identity,generation FROM stock_read_epoch WHERE singleton=1').fetchone()
            if identity != stamp['store_identity'] or generation != stamp['content_generation']:
                raise Denied('memory_changed_retry')
            scopes = self.scopes(sid,state)
            for record in records:
                row = db.execute('SELECT id,kind,content,tags,source_id,scope,status FROM stock_records WHERE id=?',(record['id'],)).fetchone()
                if not row or row[6]!='approved' or row[5] not in scopes:
                    raise Denied('memory_changed_retry')
                current = dict(id=row[0],kind=row[1],text=row[2],tags=json.loads(row[3]),source_id=row[4],scope=row[5].split(':')[0])
                if current != record:
                    raise Denied('memory_changed_retry')
            result = materialize(records)
            # Time-based expiry can advance without a SQLite mutation.
            self.state(db,sid)
            return result

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
            sid=self.root(db,sid)
            db.execute('INSERT OR IGNORE INTO stock_sessions(session) VALUES(?)',(sid,))
            db.execute('UPDATE stock_sessions SET enabled=1,project=?,user_scope=?,capture=?,agent=?,organizer=?,revision=revision+1 WHERE session=?',
                       (project,user,capture,agent,organizer,sid))
            revision=self.state(db,sid,False)['revision']
            expires=time.time()+hours*3600
            db.execute('INSERT OR REPLACE INTO stock_local_grants VALUES(?,?,?)',(sid,expires,revision))
            return {'expires':expires,'settings':self.state(db,sid,False)}

    def revoke_local(self, session_id):
        sid=session_key(session_id,'cli')
        with closing(self.open()) as db:
            sid=self.root(db,sid)
        return self.settings(sid,{'enabled':False})

    def require_local_grant(self, session_id):
        sid=session_key(session_id,'cli')
        with closing(self.open()) as db:
            db.execute('BEGIN')
            sid=self.root(db,sid)
            if not db.execute('SELECT 1 FROM stock_local_grants WHERE session=?',(sid,)).fetchone():
                raise Denied('exact_session_cli_grant_required')
            self.state(db,sid)
        return sid

    def insert(self, sid, kind, content, tags=(), source_id=None, approved=False, expected_revision=None, expected_store=None):
        if kind not in KINDS: raise ValueError('invalid_kind')
        content = text(content)
        if not isinstance(tags, (list,tuple)) or len(tags) > 12: raise ValueError('invalid_tags')
        tags = [text(tag,64) for tag in tags]
        with closing(self.open()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            state = self.state(db,sid)
            if expected_revision is not None and state['revision'] != expected_revision: raise Denied('scope_changed_retry')
            if expected_store is not None and expected_store != db.execute('SELECT identity FROM stock_read_epoch WHERE singleton=1').fetchone()[0]: raise Denied('memory_changed_retry')
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

    def manager_snapshot(self, sid, status='approved', offset=0, materialize=lambda value:value):
        """One authorized snapshot; no global records, counts, paths or grant changes."""
        if status not in ('approved','pending','trash'): raise ValueError('invalid_status')
        if type(offset) is not int or not 0 <= offset <= 1000000000: raise ValueError('invalid_offset')
        with closing(self.open()) as db:
            db.execute('BEGIN IMMEDIATE')
            state = self.state(db,sid)
            scopes = self.scopes(sid,state)
            rows = db.execute('SELECT id,kind,content,tags,source_id,scope,updated FROM stock_records WHERE scope IN (' + ','.join('?' for _ in scopes) + ') AND status=? ORDER BY updated DESC,id DESC LIMIT 13 OFFSET ?', scopes+[status,offset]).fetchall()
            records = [{'version':hashlib.sha256(json.dumps([r[0],r[2],r[3],r[6],status]).encode()).hexdigest(),'id':r[0],'kind':r[1],'text':r[2],'tags':json.loads(r[3]),'source_id':r[4],
                        'destination':('Project: '+state['project']) if r[5].startswith('project:') else ('Shared user memory in this profile' if r[5].startswith('user:') else 'This chat only')} for r in rows[:12]]
            result = materialize({'store_identity':db.execute('SELECT identity FROM stock_read_epoch WHERE singleton=1').fetchone()[0], 'revision':state['revision'], 'project':state['project'], 'user_scope':state['user_scope'],
                    'records':records,'status':status,'offset':offset,'next_offset':offset+12 if len(rows)>12 else None})
            self.state(db,sid)
            return result

    def change(self, sid, identity, action, content=None, expected_revision=None, expected_record=None, expected_store=None):
        if action not in ('approve','trash','restore','edit'): raise ValueError('invalid_action')
        if content is not None: content = text(content)
        with closing(self.open()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            state = self.state(db,sid)
            if expected_revision is not None and state['revision'] != expected_revision: raise Denied('scope_changed_retry')
            if expected_store is not None and expected_store != db.execute('SELECT identity FROM stock_read_epoch WHERE singleton=1').fetchone()[0]: raise Denied('memory_changed_retry')
            scopes = self.scopes(sid,state)
            row = db.execute('SELECT scope,status,content,tags,updated FROM stock_records WHERE id=?',(identity,)).fetchone()
            if not row or row[0] not in scopes: raise Denied('record_not_in_scope')
            if expected_record is not None and expected_record != hashlib.sha256(json.dumps([identity,row[2],row[3],row[4],row[1]]).encode()).hexdigest(): raise Denied('record_changed_retry')
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

    # -- Memory-aware routing ------------------------------------------------------------------
    # route_task (no session context) -> subagent_start (child id + goal) -> subagent_stop (status).
    # Goals are linked by hash only; keywords are kept only when the parent chat has ELM on.

    def route_pending(self, goal, agent, chosen_by):
        key = _hash(goal.strip()) if isinstance(goal, str) else None
        if key is None:
            return
        now = time.time()
        with closing(self.open()) as db, db:
            db.execute('DELETE FROM stock_route_pending WHERE created<?', (now - ROUTE_PENDING_SECONDS,))
            db.execute('INSERT OR REPLACE INTO stock_route_pending VALUES(?,?,?,?)', (key, agent, chosen_by, now))

    def route_started(self, sid, child_session_id, goal, terms):
        """Link a spawned child to the agent route_task chose. ``sid``: the parent chat, already authorized."""
        key, child = (_hash(goal.strip()) if isinstance(goal, str) else None), _hash(child_session_id)
        if key is None or child is None:
            return None
        with closing(self.open()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT agent FROM stock_route_pending WHERE goal=?', (key,)).fetchone()
            if not row:
                return None
            db.execute('DELETE FROM stock_route_pending WHERE goal=?', (key,))
            db.execute('INSERT OR REPLACE INTO stock_route_runs VALUES(?,?,?,?,?)',
                       (child, row[0], sid, json.dumps(list(terms)[:12]), time.time()))
            return row[0]

    def route_finished(self, child_session_id, ok, duration_ms):
        child = _hash(child_session_id)
        if child is None:
            return None
        with closing(self.open()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT agent,session,terms FROM stock_route_runs WHERE child=?', (child,)).fetchone()
            if not row:
                return None
            db.execute('DELETE FROM stock_route_runs WHERE child=?', (child,))
            duration = int(duration_ms) if isinstance(duration_ms, (int, float)) and duration_ms >= 0 else 0
            db.execute('INSERT INTO stock_route_outcomes(agent,session,terms,ok,duration_ms,created) VALUES(?,?,?,?,?,?)',
                       (row[0], row[1], row[2], 1 if ok else 0, duration, time.time()))
            db.execute('DELETE FROM stock_route_outcomes WHERE id NOT IN '
                       '(SELECT id FROM stock_route_outcomes ORDER BY id DESC LIMIT ?)', (ROUTE_OUTCOMES_KEPT,))
            return row[0]

    def route_history(self, limit=500):
        """Recent outcomes for scoring: (agent, terms, ok). Keywords only; never shown to a model."""
        with closing(self.open()) as db:
            rows = db.execute('SELECT agent,terms,ok FROM stock_route_outcomes ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
        return [(agent, json.loads(terms), bool(ok)) for agent, terms, ok in rows]

    def route_stats(self):
        """Per-agent counts for `hermes elm routes` (no keywords, no chat IDs)."""
        with closing(self.open()) as db:
            rows = db.execute('SELECT agent, COUNT(*), SUM(ok), AVG(duration_ms) FROM stock_route_outcomes '
                              'GROUP BY agent ORDER BY agent').fetchall()
        return [{'agent': a, 'runs': n, 'succeeded': int(s or 0), 'avg_seconds': round((d or 0) / 1000, 1)}
                for a, n, s, d in rows]
