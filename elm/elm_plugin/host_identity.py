"""Read-only adapter to host-owned chat and project metadata.

No CWD inference, active-sidebar inference, message parsing or caller grants.
Host qualification is release-specific; symbol presence does not prove compatibility.
Missing host metadata fails closed. It never creates or migrates a host database.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3


class IdentityError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _identifier(value):
    if not isinstance(value, str) or not value or len(value) > 256 or any(ord(c) < 32 for c in value):
        raise IdentityError('invalid_session', 'A valid host-owned session ID is required')
    return value


class HostIdentity:
    def __init__(self, home):
        self.home = Path(home).resolve()

    def _projects(self):
        path = self.home / 'projects.db'
        if not path.is_file():
            return None
        conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only=ON')
        return conn

    def list_projects(self):
        from hermes_cli import projects_db

        try:
            conn = self._projects()
            if conn is None:
                return []
            with closing(conn):
                return [{'id': p.id, 'name': p.name} for p in projects_db.list_projects(conn)]
        except sqlite3.Error as exc:
            raise IdentityError('host_metadata_unavailable', 'Cannot read current host workspaces') from exc

    def resolve(self, session_id):
        session_id = _identifier(session_id)
        try:
            from hermes_state import SessionDB
            from hermes_cli import projects_db
        except ImportError as exc:
            raise IdentityError('host_api_unsupported',
                                'This host lacks the required workspace ownership API') from exc
        if not callable(getattr(projects_db, 'resolve_session_project', None)):
            raise IdentityError('host_api_unsupported',
                                'This host lacks the required workspace ownership API')
        path = self.home / 'state.db'
        if not path.is_file():
            raise IdentityError('session_unavailable', 'This profile has no stored chat to bind')
        try:
            with closing(SessionDB(path, read_only=True)) as db:
                if db.get_session(session_id) is None:
                    raise IdentityError('session_unavailable', 'The chat does not belong to this profile')
                lineage = db.get_compression_lineage(session_id)
                if session_id not in lineage or len(lineage) > 100:
                    raise IdentityError('lineage_unavailable', 'Cannot verify the current chat lineage')
                # The public host method may include future continuation rows. They
                # cannot change authority for an earlier still-running session.
                lineage = lineage[:lineage.index(session_id) + 1]
            project = None
            conn = self._projects()
            if conn is not None:
                with closing(conn):
                    binding = projects_db.resolve_session_project(conn, lineage)
                    if binding and binding['project_id']:
                        project = projects_db.get_project(conn, binding['project_id'])
                        if project is None or project.archived:
                            raise IdentityError('project_unavailable', 'The bound workspace is unavailable')
            result = {'session_id': session_id, 'chat_id': lineage[0],
                      'project_id': project.id if project else None,
                      'project_name': project.name if project else None,
                      'profile_home': str(self.home)}
            result['fingerprint'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
            return result
        except sqlite3.Error as exc:
            raise IdentityError('host_metadata_unavailable', 'Cannot read current host scope metadata') from exc
