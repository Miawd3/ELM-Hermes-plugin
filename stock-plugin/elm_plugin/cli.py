"""`hermes elm ...`: grant ELM to one exact chat from your own terminal.

Hermes itself selects the profile (`hermes -p NAME elm grant`), so no HERMES_HOME or
Python setup is needed. The trust model is unchanged from `python -m elm_plugin.local_grant`:
only someone at this computer's terminal can grant, and only one exact chat at a time.
"""
import datetime
import sys

TRUST_NOTE = ('Any app connected to this same chat (Desktop, TUI or an editor client) can use the grant. '
              'Approved memories are added to that chat and may be sent to its model provider.')


def recent_sessions(limit=15):
    """Recent chats of the active profile, newest first. Read-only."""
    from hermes_state import SessionDB
    db = SessionDB(read_only=True)
    try:
        rows = db.list_sessions_rich(exclude_sources=['tool'], limit=limit, order_by_last_active=True)
    finally:
        close = getattr(db, 'close', None)
        if close:
            close()
    result = []
    for row in rows:
        sid = row.get('id')
        if not isinstance(sid, str) or not sid:
            continue
        label = (row.get('title') or row.get('preview') or '(untitled)').replace('\n', ' ').strip()
        when = row.get('last_active') or row.get('started_at')
        try:
            when = datetime.datetime.fromtimestamp(float(when)).strftime('%Y-%m-%d %H:%M')
        except (TypeError, ValueError, OverflowError, OSError):
            when = ''
        result.append({'id': sid, 'label': label[:60], 'when': when, 'source': row.get('source') or ''})
    return result


def _print_sessions(rows):
    for number, row in enumerate(rows, 1):
        print(f'{number:>3}. {row["when"]:<16}  {row["source"]:<8} {row["label"]}')
        print(f'     {row["id"]}')


def _pick(rows):
    if not rows:
        print('No chats found in this profile. Send a message in the chat first, then retry.')
        return None
    _print_sessions(rows)
    if not sys.stdin.isatty():
        print('Pass the chat ID: hermes elm grant <ID>')
        return None
    answer = input('Grant ELM to which chat? Number (Enter to cancel): ').strip()
    if not answer.isdigit() or not 1 <= int(answer) <= len(rows):
        print('Cancelled. Nothing was changed.')
        return None
    return rows[int(answer) - 1]['id']


def _confirm(args):
    if args.yes:
        return True
    print(TRUST_NOTE)
    if args.agent or args.organizer:
        print('Agent/organizer options allow model calls that may cost money.')
    if args.capture:
        print('Capture saves each completed turn as plain text on this computer.')
    if not sys.stdin.isatty():
        print('Add --yes to confirm non-interactively.')
        return False
    return input('Continue? [y/N] ').strip().lower() in ('y', 'yes')


def _describe(settings):
    on = [name for name, key in (('project ' + str(settings.get('project')), 'project'), ('shared user memory', 'user_scope'),
                                 ('capture', 'capture'), ('search agent', 'agent'), ('organizer', 'organizer'))
          if settings.get(key)]
    return ', '.join(on) if on else 'this chat only; no sharing, capture or model calls'


def _listed(limit=15):
    try:
        return recent_sessions(limit)
    except Exception as exc:  # session store layout is host-owned; degrade to manual IDs
        print(f'Could not list chats ({type(exc).__name__}). Use `hermes sessions list` and pass the ID.')
        return None


def plugin_version():
    from pathlib import Path
    manifest = Path(__file__).resolve().parent.parent / 'plugin.yaml'
    try:
        for line in manifest.read_text(encoding='utf-8').splitlines():
            if line.startswith('version:'):
                return line.split(':', 1)[1].strip()
    except OSError:
        pass
    return 'unknown'


def hermes_version():
    from importlib import metadata
    try:
        version = metadata.version('hermes-agent')
    except metadata.PackageNotFoundError:
        version = '0.0.0'
    return version if version != '0.0.0' else '(see `hermes version`)'


def doctor(store):
    """Privacy-safe status for bug reports: versions, paths and counts. No memory text or chat IDs."""
    import platform
    from hermes_constants import display_hermes_home
    print(f'ELM {plugin_version()} on Hermes {hermes_version()} ({platform.system()} {platform.release()}, Python {platform.python_version()})')
    print(f'Profile: {display_hermes_home()}')
    from .stock_runtime import provider_selected
    print('Memory slot: ELM is the memory provider (memory.provider: elm)' if provider_selected()
          else 'Memory slot: not selected; recall runs through plugin hooks (hermes memory setup elm to switch)')
    try:
        health = store.health()
    except Exception as exc:
        print(f'Storage: ERROR {type(exc).__name__}: {str(exc)[:200]}')
        return 1
    records = health.pop('records')
    print('Storage: ok' if health['integrity'] == 'ok' else f"Storage: integrity {health['integrity']}")
    for key, value in health.items():
        if key != 'integrity':
            print(f'  {key.replace("_", " ")}: {value}')
    print(f"  records: {records['approved']} approved, {records['pending']} pending, {records['trash']} in trash")
    print('Contains counts only; safe to paste into a bug report.')
    return 0


def run(args, store_factory):
    from hermes_constants import display_hermes_home
    store = store_factory()
    if args.elm_command == 'doctor':
        return doctor(store)
    if args.elm_command == 'sessions':
        rows = _listed(args.limit)
        if rows is None:
            return 1
        _print_sessions(rows) if rows else print('No chats found in this profile.')
        return 0
    session = args.session
    if session is None:
        rows = _listed()
        session = None if rows is None else _pick(rows)
        if session is None:
            return 1
    if session.strip() != session or any(c in session for c in '*?\x00\n\r'):
        print('Use one exact chat ID.')
        return 2
    if args.elm_command == 'revoke':
        store.revoke_local(session)
        print(f'ELM is off for chat {session}. Saved memories are kept.')
        return 0
    if not _confirm(args):
        print('Cancelled. Nothing was changed.')
        return 1
    result = store.grant_local(session, hours=args.hours, project=args.project, user=args.user,
                               capture=args.capture, agent=args.agent, organizer=args.organizer)
    expires = datetime.datetime.fromtimestamp(result['expires']).strftime('%Y-%m-%d %H:%M')
    print(f'ELM granted to chat {session} until {expires} (profile: {display_hermes_home()}).')
    print(f'Access: {_describe(result["settings"])}.')
    print('Back in the chat, refresh Settings -> Plugins -> ELM or send /elm status.')
    return 0


def setup_cli(parser, store_or_factory):
    factory = store_or_factory if callable(store_or_factory) and not hasattr(store_or_factory, 'open') else (lambda: store_or_factory)
    subs = parser.add_subparsers(dest='elm_command')
    grant = subs.add_parser('grant', help='Turn ELM on for one exact chat (renewing replaces all options)')
    grant.add_argument('session', nargs='?', help='Chat ID; omit to pick from recent chats')
    grant.add_argument('--hours', type=int, default=24, help='Expiry, 1-168 hours (default 24)')
    grant.add_argument('--project', help='Share project memories with other chats granted the same project')
    grant.add_argument('--user', action='store_true', help='Share user facts with other chats that allow it')
    grant.add_argument('--capture', action='store_true', help='Save completed turns locally as plain text')
    grant.add_argument('--agent', action='store_true', help='Allow the search agent (query-only model calls)')
    grant.add_argument('--organizer', action='store_true', help='Allow the organizer (model calls on selected sources)')
    grant.add_argument('-y', '--yes', '--allow-session-clients', dest='yes', action='store_true',
                       help='Skip the confirmation prompt')
    revoke = subs.add_parser('revoke', help='Turn ELM off for one chat (saved memories are kept)')
    revoke.add_argument('session', nargs='?', help='Chat ID; omit to pick from recent chats')
    subs.add_parser('doctor', help='Show versions, storage health and counts (safe for bug reports)')
    sessions = subs.add_parser('sessions', help='List recent chats with their IDs')
    sessions.add_argument('--limit', type=int, default=15)

    def handler(args):
        if not getattr(args, 'elm_command', None):
            parser.print_help()
            return 0
        try:
            return run(args, factory)
        except (ValueError, TypeError) as exc:
            print(f'ELM: {exc}. Nothing was changed.')
            return 2
    parser.set_defaults(func=handler)
    return parser
