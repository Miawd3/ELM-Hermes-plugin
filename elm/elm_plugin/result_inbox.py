"""Saved assistant output, not memory facts or original-request completion.

The host supplies home and current session; payloads never choose a profile/root.
Only the resolved chat lineage can read its results. No transcript reads, memory
initialization, recall, notifications, model calls or external network live here.
"""
from contextlib import contextmanager, closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import uuid

from hermes_constants import get_hermes_home
from .host_identity import HostIdentity


class InboxError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _text(value, name, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or '\x00' in value:
        raise InboxError('invalid_payload', f'{name} must be nonblank text of at most {maximum} characters')
    return value


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{32}', value):
        raise InboxError('invalid_id', 'A literal 32-character lowercase result ID is required')
    return value


def _revision(value):
    if type(value) is not int or value < 1:
        raise InboxError('invalid_revision', 'A positive integer expected_revision is required')
    return value


_INIT = threading.Lock()
_DEFAULTS = {'mode':'quiet', 'updates_visible':False, 'revision':1}


class ResultInbox:
    """Human store seam. ``home`` is host-only, never a body field."""
    def __init__(self, home):
        self.home = Path(home).resolve()
        self.root = self.home/'elm-product-ui'
        self.path = self.root/'results.sqlite3'
        self.identity = HostIdentity(self.home)
        self.marker = {'owner':'elm-product-ui', 'schema':1,
                       'profile':hashlib.sha256(str(self.home).encode()).hexdigest()}

    def _guard(self):
        if self.root.is_symlink() or self.path.is_symlink() or (self.root/'owner.json').is_symlink():
            raise InboxError('unowned_ui_root', 'Product UI state must not be redirected')
        if self.root.exists():
            try:
                marker = json.loads((self.root/'owner.json').read_text(encoding='utf-8'))
            except (OSError, ValueError) as exc:
                raise InboxError('unowned_ui_root', 'Product UI state has no valid ownership marker') from exc
            if marker != self.marker:
                raise InboxError('unowned_ui_root', 'Product UI state belongs to a different owner or schema')

    def _initialize(self):
        with _INIT:
            self._guard()
            if not self.root.exists():
                self.root.mkdir()
                with (self.root/'owner.json').open('x', encoding='utf-8') as f:
                    json.dump(self.marker, f, sort_keys=True)
            if self.path.exists():
                with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True,timeout=3)) as existing:
                    if existing.execute('PRAGMA user_version').fetchone()[0] != 1:
                        raise InboxError('invalid_ui_schema','Unsupported product UI schema; no migration or overwrite was attempted')
                return
            with closing(sqlite3.connect(self.path, timeout=3)) as db:
                db.execute('PRAGMA journal_mode=DELETE')
                db.execute('PRAGMA synchronous=FULL')
                db.executescript('''
                    CREATE TABLE IF NOT EXISTS results (
                        seq INTEGER PRIMARY KEY AUTOINCREMENT,
                        id TEXT NOT NULL UNIQUE, chat_id TEXT NOT NULL,
                        session_id TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
                        kind TEXT NOT NULL, status TEXT NOT NULL, dismissed INTEGER NOT NULL,
                        revision INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                    CREATE INDEX IF NOT EXISTS results_chat ON results(chat_id,seq);
                    CREATE TABLE IF NOT EXISTS attention (
                        chat_id TEXT PRIMARY KEY, mode TEXT NOT NULL,
                        updates_visible INTEGER NOT NULL, revision INTEGER NOT NULL);
                    PRAGMA user_version=1;
                ''')

    @contextmanager
    def _connection(self, session_id, *, write=False):
        context = self.identity.resolve(session_id)
        self._guard()
        if write:
            self._initialize()
        elif not self.path.exists():
            yield None, context
            return
        db = sqlite3.connect(self.path.as_uri() + ('?mode=rw' if write else '?mode=ro'), uri=True, timeout=3)
        db.row_factory = sqlite3.Row
        try:
            if db.execute('PRAGMA user_version').fetchone()[0] != 1:
                raise InboxError('invalid_ui_schema', 'Unsupported product UI schema')
            if write:
                db.execute('BEGIN IMMEDIATE')
            else:
                db.execute('PRAGMA query_only=ON')
                db.execute('BEGIN')
            yield db, context
            if write:
                if self.identity.resolve(session_id)['fingerprint'] != context['fingerprint']:
                    raise InboxError('scope_changed', 'The host chat changed during the write; refresh before trying again')
                db.commit()
        finally:
            db.close()

    @staticmethod
    def _result(row):
        return {k:(bool(row[k]) if k == 'dismissed' else row[k]) for k in
                ('id','chat_id','session_id','title','body','kind','status','dismissed','revision','created_at','updated_at')}

    @staticmethod
    def _context(context):
        return {'session_id':context['session_id'], 'chat_id':context['chat_id']}

    def list(self, session_id, limit=50, cursor=None, include_dismissed=False):
        if type(limit) is not int or not 1 <= limit <= 100 or type(include_dismissed) is not bool:
            raise InboxError('invalid_payload', 'limit must be 1–100 and include_dismissed must be boolean')
        if cursor is not None and (not isinstance(cursor, str) or not re.fullmatch(r'[1-9][0-9]{0,17}', cursor)):
            raise InboxError('invalid_cursor', 'Invalid result cursor')
        with self._connection(session_id) as (db, ctx):
            rows, counts, prefs = [], {'unread':0,'viewed':0,'read':0,'dismissed':0}, dict(_DEFAULTS)
            if db:
                for r in db.execute('SELECT status,dismissed,count(*) AS n FROM results WHERE chat_id=? GROUP BY status,dismissed', (ctx['chat_id'],)):
                    counts['dismissed' if r['dismissed'] else r['status']] += r['n']
                rows = db.execute('SELECT * FROM results WHERE chat_id=? AND (? OR dismissed=0) AND (? IS NULL OR seq<?) ORDER BY seq DESC LIMIT ?',
                    (ctx['chat_id'], int(include_dismissed), cursor, int(cursor) if cursor else None, limit+1)).fetchall()
                prefs = self._prefs(db, ctx['chat_id'])
            more = len(rows) > limit
            return {'schema':1, 'context':self._context(ctx), 'results':[self._result(r) for r in rows[:limit]],
                    'counts':counts, 'attention':prefs,
                    'next_cursor':str(rows[limit-1]['seq']) if more else None}

    def get(self, session_id, result_id):
        _id(result_id)
        with self._connection(session_id) as (db, ctx):
            row = db.execute('SELECT * FROM results WHERE id=? AND chat_id=?', (result_id,ctx['chat_id'])).fetchone() if db else None
            return {'schema':1, 'context':self._context(ctx), 'id':result_id,
                    'exists':row is not None, 'result':self._result(row) if row else None}

    def publish(self, session_id, *, title, body, kind):
        _text(title, 'title', 300)
        _text(body, 'body', 100000)
        if kind not in ('progress','partial','blocked','final'):
            raise InboxError('invalid_payload', 'kind must declare progress, partial, blocked or final')
        now = datetime.now(timezone.utc).isoformat()
        result_id = uuid.uuid4().hex
        with self._connection(session_id, write=True) as (db, ctx):
            if db.execute('SELECT count(*) FROM results WHERE chat_id=?', (ctx['chat_id'],)).fetchone()[0] >= 1000:
                raise InboxError('result_limit', 'This chat has 1000 saved results; delete some before publishing more')
            db.execute('INSERT INTO results(id,chat_id,session_id,title,body,kind,status,dismissed,revision,created_at,updated_at) VALUES (?,?,?,?,?,?,?,0,1,?,?)',
                       (result_id,ctx['chat_id'],session_id,title,body,kind,'unread',now,now))
        saved = self.get(session_id, result_id)['result']
        if saved is None:
            raise InboxError('publication_unconfirmed', 'Output was committed but its row could not be read back; do not publish it again automatically')
        return saved

    def mutate(self, session_id, result_id, expected_revision, action):
        _id(result_id)
        _revision(expected_revision)
        if action not in ('view','read','dismiss','restore','delete'):
            raise InboxError('invalid_action', 'Unsupported result action')
        # Missing/wrong-chat targets do not initialize any state.
        if not self.get(session_id, result_id)['exists']:
            raise InboxError('result_not_found', 'Result is unavailable in this chat')
        with self._connection(session_id, write=True) as (db, ctx):
            row = db.execute('SELECT * FROM results WHERE id=? AND chat_id=?', (result_id,ctx['chat_id'])).fetchone()
            if row is None:
                raise InboxError('result_not_found', 'Result is unavailable in this chat')
            if row['revision'] != expected_revision:
                raise InboxError('revision_conflict', 'This result changed; refresh and review before trying again')
            if action == 'delete':
                db.execute('DELETE FROM results WHERE id=? AND chat_id=?', (result_id,ctx['chat_id']))
                result = {'deleted_id':result_id, 'deleted_revision':expected_revision}
            else:
                status = 'read' if action == 'read' else 'viewed' if action == 'view' and row['status'] == 'unread' else row['status']
                dismissed = 1 if action == 'dismiss' else 0 if action == 'restore' else row['dismissed']
                if status != row['status'] or dismissed != row['dismissed']:
                    db.execute('UPDATE results SET status=?,dismissed=?,revision=revision+1,updated_at=? WHERE id=? AND chat_id=?',
                               (status,dismissed,datetime.now(timezone.utc).isoformat(),result_id,ctx['chat_id']))
                result = self._result(db.execute('SELECT * FROM results WHERE id=? AND chat_id=?', (result_id,ctx['chat_id'])).fetchone())
        return result

    def attention(self, session_id):
        with self._connection(session_id) as (db, ctx):
            return {'schema':1, 'context':self._context(ctx),
                    'attention':self._prefs(db, ctx['chat_id']) if db else dict(_DEFAULTS)}

    def set_attention(self, session_id, expected_revision, mode, updates_visible):
        _revision(expected_revision)
        if mode not in ('quiet','off') or type(updates_visible) is not bool:
            raise InboxError('invalid_payload', 'mode must be quiet/off and updates_visible must be boolean')
        with self._connection(session_id, write=True) as (db, ctx):
            before = self._prefs(db, ctx['chat_id'])
            if before['revision'] != expected_revision:
                raise InboxError('revision_conflict', 'Attention preferences changed; refresh before saving')
            db.execute('INSERT OR REPLACE INTO attention(chat_id,mode,updates_visible,revision) VALUES (?,?,?,?)',
                       (ctx['chat_id'], mode, int(updates_visible), expected_revision+1))
            result = self._prefs(db, ctx['chat_id'])
        return result

    @staticmethod
    def _prefs(db, chat_id):
        row = db.execute('SELECT mode,updates_visible,revision FROM attention WHERE chat_id=?', (chat_id,)).fetchone()
        return {'mode':row['mode'], 'updates_visible':bool(row['updates_visible']), 'revision':row['revision']} if row else dict(_DEFAULTS)


def publish_important_result(*, current_session_id, title, body, kind):
    """Native publisher contract: current_session_id comes ONLY from host context.

    Tool schemas must expose title/body/kind, never current_session_id or home.
    Owner wires this function after verifying native context/session provenance.
    A final kind is the assistant's declaration, never verified task completion.
    """
    inbox = ResultInbox(get_hermes_home())
    result = inbox.publish(current_session_id, title=title, body=body, kind=kind)
    return {'ok':True, 'result':result,
            'directive':f'::elm-result{{id="{result["id"]}"}}',
            'meaning':'Saved assistant output only; not proof the user read it or the original request is complete.'}
