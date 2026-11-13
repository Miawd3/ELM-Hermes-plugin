"""Explicit local operator bridge for stock unified sessions; never a model tool."""
import argparse
import json
from .stock_store import Store, session_key


def main(argv=None, store=None):
    parser=argparse.ArgumentParser(description='Grant ELM to ONE exact Hermes session in the active profile. Any authenticated client accessing that same session can use this grant. This does not identify a human or exclude ACP. Approved memory may reach the chat provider.')
    parser.add_argument('session',help='Exact saved session ID, not its title; no wildcard')
    parser.add_argument('--allow-session-clients',action='store_true',help='Acknowledge same-session client access')
    parser.add_argument('--revoke',action='store_true')
    parser.add_argument('--hours',type=int,default=24,help='Expiry, 1–168 hours (default 24)')
    parser.add_argument('--project',help='Optional exact project scope')
    parser.add_argument('--user',action='store_true',help='Allow profile-wide user facts')
    parser.add_argument('--capture',action='store_true',help='Save plaintext turns locally')
    parser.add_argument('--agent',action='store_true',help='Allow query-only model calls; fees may apply')
    parser.add_argument('--organizer',action='store_true',help='Allow explicit source extraction calls; fees may apply')
    args=parser.parse_args(argv)
    store=store or Store()
    if args.revoke:
        result=store.settings(session_key(args.session,'cli'),{'enabled':False})
    else:
        if not args.allow_session_clients: parser.error('--allow-session-clients is required; read the trust warning in --help')
        if args.session.strip()!=args.session or any(c in args.session for c in '*?\x00\n\r'): parser.error('use one exact session ID')
        result=store.grant_local(args.session,hours=args.hours,project=args.project,user=args.user,capture=args.capture,agent=args.agent,organizer=args.organizer)
    print(json.dumps(result))

if __name__=='__main__': main()
