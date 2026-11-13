"""Explicit local operator bridge for stock unified sessions; never a model tool."""
import argparse
import json
from pathlib import Path
from .stock_store import Store, session_key


def main(argv=None, store=None):
    parser=argparse.ArgumentParser(description='Grant ELM to ONE exact Hermes session in the active profile. Any authenticated client accessing that same session can use this grant. This does not identify a human or exclude ACP. Approved memory may reach the chat provider.')
    parser.add_argument('session',nargs='?',help='Exact saved session ID, not its title; no wildcard')
    parser.add_argument('--allow-session-clients',action='store_true',help='Acknowledge same-session client access')
    parser.add_argument('--revoke',action='store_true')
    parser.add_argument('--hours',type=int,default=24,help='Expiry, 1–168 hours (default 24)')
    parser.add_argument('--project',help='Optional exact project scope')
    parser.add_argument('--user',action='store_true',help='Allow profile-wide user facts')
    parser.add_argument('--capture',action='store_true',help='Save plaintext turns locally')
    parser.add_argument('--agent',action='store_true',help='Allow query-only model calls; fees may apply')
    parser.add_argument('--organizer',action='store_true',help='Allow explicit source extraction calls; fees may apply')
    parser.add_argument('--show-home',action='store_true',help='Print resolved Hermes profile path without reading or writing memory')
    parser.add_argument('--expect-home',help='Required profile-home path; refuse a mismatched Hermes environment before opening storage')
    args=parser.parse_args(argv)
    # Plain Python does not execute Hermes CLI profile selection. Resolve the public
    # host context and compare BEFORE constructing/opening a persistent store.
    from hermes_constants import get_hermes_home
    actual=Path(get_hermes_home()).expanduser().resolve()
    if args.show_home:
        print(json.dumps({'hermes_home':str(actual)}))
        return
    if not args.session: parser.error('an exact session ID is required')
    if not args.expect_home: parser.error('--expect-home is required; use --show-home and verify the Desktop profile first')
    expected=Path(args.expect_home).expanduser()
    if not expected.is_absolute(): parser.error('--expect-home must be an absolute profile path')
    if expected.resolve()!=actual: parser.error('profile_home_mismatch; no memory changes were made')
    if not actual.is_dir(): parser.error('profile_home_missing; no memory changes were made')
    if args.session.strip()!=args.session or any(c in args.session for c in '*?\x00\n\r'): parser.error('use one exact session ID')
    store=Store() if store is None else store
    if args.revoke:
        result=store.settings(session_key(args.session,'cli'),{'enabled':False})
    else:
        if not args.allow_session_clients: parser.error('--allow-session-clients is required; read the trust warning in --help')
        result=store.grant_local(args.session,hours=args.hours,project=args.project,user=args.user,capture=args.capture,agent=args.agent,organizer=args.organizer)
    print(json.dumps({'hermes_home':str(actual),'result':result}))

if __name__=='__main__': main()
