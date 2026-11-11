"""Human future-container defaults. No memory initialization or host config writes.

Adapted from a Gemini proposal; owner corrected transaction, corruption and wire
contracts before integration. Creation proof belongs to private_creation.py.
"""
import json
import sqlite3
from contextlib import closing
from .result_inbox import ResultInbox, InboxError, _revision


def _defaults():
    def entry(reads):
        return {'workspace_reads': reads, 'conversation': {'provider': '', 'model': ''},
                'memory': {'mode': 'host', 'provider': '', 'model': '', 'allow_host_fallback': False}}
    return {'private_chat': entry(False), 'private_workspace': entry(True), 'cap_enabled': False}


def _string(value):
    if (not isinstance(value, str) or len(value) > 256 or value != value.strip()
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise InboxError('invalid_payload', 'Route identifiers must be exact unpadded strings, at most256 characters')
    try:
        value.encode('utf-8')
    except UnicodeError:
        raise InboxError('invalid_payload','Route identifiers must be valid Unicode') from None
    return value


def validate_settings(data):
    if type(data) is not dict or set(data) != {'private_chat', 'private_workspace', 'cap_enabled'}:
        raise InboxError('invalid_payload', 'Only the declared private defaults are accepted')
    if type(data['cap_enabled']) is not bool:
        raise InboxError('invalid_payload', 'cap_enabled must be boolean')
    if data['cap_enabled']:
        raise InboxError('unsupported_cap', 'This host has no qualified per-attempt hard-cap gate; cap remains OFF')
    for kind in ('private_chat', 'private_workspace'):
        e = data[kind]
        if type(e) is not dict or set(e) != {'workspace_reads', 'conversation', 'memory'} or type(e['workspace_reads']) is not bool:
            raise InboxError('invalid_payload', 'Invalid private-container defaults')
        c, m = e['conversation'], e['memory']
        if type(c) is not dict or set(c) != {'provider', 'model'}:
            raise InboxError('invalid_payload', 'Invalid conversation route')
        if type(m) is not dict or set(m) != {'mode', 'provider', 'model', 'allow_host_fallback'}:
            raise InboxError('invalid_payload', 'Invalid memory route')
        for route in (c, m):
            _string(route['provider']); _string(route['model'])
            if bool(route['provider']) != bool(route['model']):
                raise InboxError('invalid_payload', 'Select both exact provider and model, or neither')
        if m['mode'] not in ('host', 'follow_chat', 'separate') or type(m['allow_host_fallback']) is not bool:
            raise InboxError('invalid_payload', 'Invalid memory mode/fallback consent')
        if (m['mode'] == 'separate') != bool(m['provider']):
            raise InboxError('invalid_payload', 'Only separate memory routing accepts explicit route IDs')
    return json.loads(json.dumps(data, allow_nan=False))


def _decode(raw):
    def unique(pairs):
        obj = {}
        for k, v in pairs:
            if k in obj: raise ValueError('duplicate settings field')
            obj[k] = v
        return obj
    try:
        return validate_settings(json.loads(raw, object_pairs_hook=unique))
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        raise InboxError('corrupt_settings', 'Private controls are unreadable; no generation or defaults applied') from exc


class PrivateControls(ResultInbox):
    @staticmethod
    def _tables(db):
        # execute(), NOT executescript(): retain the inherited BEGIN IMMEDIATE/CAS.
        db.execute('CREATE TABLE IF NOT EXISTS private_defaults (id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT NOT NULL,revision INTEGER NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS private_chat_models (chat_id TEXT PRIMARY KEY,payload TEXT NOT NULL,revision INTEGER NOT NULL,kind TEXT NOT NULL)')

    @staticmethod
    def _exists(db, table):
        return db is not None and db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None

    def _read_defaults(self, db):
        row = db.execute('SELECT payload,revision FROM private_defaults WHERE id=1').fetchone() if self._exists(db, 'private_defaults') else None
        if row is None: return {'revision': 1, 'configured': False, 'settings': _defaults()}
        _revision(row['revision'])
        return {'revision': row['revision'], 'configured': True, 'settings': _decode(row['payload'])}

    def read(self, session_id):
        with self._connection(session_id) as (db, _):
            return self._read_defaults(db)

    def save(self, session_id, expected_revision, settings):
        _revision(expected_revision); clean = validate_settings(settings)
        with self._connection(session_id, write=True) as (db, _):
            self._tables(db)
            before = self._read_defaults(db)
            if before['revision'] != expected_revision:
                raise InboxError('revision_conflict', 'Defaults changed; refresh before explicitly saving')
            db.execute('INSERT INTO private_defaults VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,revision=excluded.revision',
                       (json.dumps(clean, allow_nan=False), expected_revision+1))
            saved = self._read_defaults(db)
        observed = self.read(session_id)
        if observed != saved:
            raise InboxError('publication_unconfirmed', 'Defaults committed but exact readback changed; do not retry automatically')
        return observed

    def chat_model_policy(self, session_id):
        with self._connection(session_id) as (db, ctx):
            row = db.execute('SELECT payload,revision,kind FROM private_chat_models WHERE chat_id=?', (ctx['chat_id'],)).fetchone() if self._exists(db, 'private_chat_models') else None
            if row is None: return None
            _revision(row['revision'])
            if row['kind'] not in ('private_chat', 'workspace_member'):
                raise InboxError('corrupt_settings', 'Unknown creation policy kind')
            return {'revision': row['revision'], 'kind': row['kind'], 'settings': _decode(row['payload'])}

    def bind_chat_model_policy(self, session_id, settings, kind='private_chat'):
        clean = validate_settings(settings)
        if kind not in ('private_chat', 'workspace_member'):
            raise InboxError('invalid_payload', 'Invalid creation policy kind')
        with self._connection(session_id, write=True) as (db, ctx):
            self._tables(db)
            if db.execute('SELECT 1 FROM private_chat_models WHERE chat_id=?', (ctx['chat_id'],)).fetchone():
                raise InboxError('already_bound', 'A bound chat policy is never silently replaced')
            db.execute('INSERT INTO private_chat_models VALUES(?,?,1,?)', (ctx['chat_id'], json.dumps(clean, allow_nan=False), kind))
        observed = self.chat_model_policy(session_id)
        if observed != {'revision': 1, 'kind': kind, 'settings': clean}:
            raise InboxError('publication_unconfirmed', 'Chat policy committed but readback is unconfirmed; do not repeat')
        return observed

    def workspace_model_policy(self, scope_id):
        """Profile-owned processing preference, never a content/recall grant."""
        from .workspace_service import scope_key
        self._guard()
        if not self.path.exists(): return None
        with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True)) as db:
            db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON')
            if db.execute('PRAGMA user_version').fetchone()[0]!=1:
                raise InboxError('invalid_ui_schema','Unsupported private-controls schema')
            if not self._exists(db,'private_workspaces'):return None
            for row in db.execute('SELECT id,payload FROM private_workspaces'):
                if scope_key('workspace',row['id'])==scope_id:
                    return {'revision':1,'kind':'workspace_member','settings':_decode(row['payload'])}
        return None

