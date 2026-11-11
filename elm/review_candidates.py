"""Explicit local durable-inbox workflow. May scrub withdrawn/expired records.

Not a provider/model tool. Explicit reviewed submit creates only a local pending governance proposal.
Never accepts memory, sends externally, or invokes a model.
"""
import argparse
import hashlib
import sqlite3
import sys
sys.dont_write_bytecode = True
from elm_plugin.operator_review import OperatorReviewBridge, ReviewBridgeControl
from elm_plugin.candidate_inbox import DurableCandidateInbox, CandidateInboxControl
from elm_plugin.episode_capture import CaptureRefused, EpisodeCapture
from elm_plugin.episode_inspect import EpisodeInspection
from elm_plugin.episode_recall import encoded, EpisodeRecall
from elm_plugin.engine import ElmError


class _ExistingCapture:
    """Only the non-initializing guard needed by recall and inbox validation."""
    _guard = EpisodeCapture._guard

    def __init__(self, inspector):
        inspector._guard(require_capture=True, require_store=True)
        for key in ('home', 'binding', 'config', 'scope', 'path', 'clock'):
            setattr(self, key, getattr(inspector, key))
        self.config_path = self.home / 'elm_episode_capture.json'
        self.config_digest = hashlib.sha256(inspector.raw_configs['elm_episode_capture.json']).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Review quarantined exact spans. Citation is not truth. '
        'Reads may persist revocation/expiry; no canonical acceptance. Explicit operator-submit creates a local pending proposal.')
    parser.add_argument('--hermes-home', required=True)
    parser.add_argument('--root-id', required=True)
    parser.add_argument('--project', required=True)
    sub = parser.add_subparsers(dest='operation', required=True)
    sub.add_parser('list', help='Content-free inventory, with current source validation')
    prepare = sub.add_parser('prepare', help='Persist a pending batch and display bounded source input locally')
    prepare.add_argument('--locator', action='append', required=True)
    prepare.add_argument('--request-key', required=True)
    prepare.add_argument('--include-source-text', action='store_true', required=True)
    validate = sub.add_parser('validate', help='Read manually supplied JSON from stdin, validate and persist spans')
    validate.add_argument('--batch-id', required=True)
    validate.add_argument('--include-source-text', action='store_true', required=True)
    review = sub.add_parser('review', help='Display validated spans and full current selected messages locally')
    review.add_argument('--batch-id', required=True)
    review.add_argument('--include-source-text', action='store_true', required=True)
    revoke = sub.add_parser('revoke', help='Scrub one batch even after opt-out; retain replay tombstone')
    revoke.add_argument('--batch-id', required=True)
    revoke.add_argument('--confirm-revoke', action='store_true', required=True)
    revoke_all = sub.add_parser('revoke-all', help='Scrub all batches even after opt-out; retain replay tombstones')
    revoke_all.add_argument('--confirm-revoke', action='store_true', required=True)
    op_prepare = sub.add_parser('operator-prepare', help='Supply explicit meaning/scope JSON on stdin; persist a review plan')
    op_prepare.add_argument('--batch-id', required=True)
    op_prepare.add_argument('--candidate-id', required=True)
    op_prepare.add_argument('--request-key', required=True)
    op_prepare.add_argument('--replaces-review-id')
    op_prepare.add_argument('--include-source-text', action='store_true', required=True)
    op_inspect = sub.add_parser('operator-inspect', help='Read live full context, meaning, and confirmation digest')
    op_inspect.add_argument('--review-id', required=True)
    op_inspect.add_argument('--include-source-text', action='store_true', required=True)
    sub.add_parser('operator-list', help='Content-free review/outcome inventory')
    op_submit = sub.add_parser('operator-submit', help='Explicitly confirm reviewed context and semantics; create only a pending governance proposal')
    op_submit.add_argument('--review-id', required=True)
    op_submit.add_argument('--plan-sha256', required=True)
    op_submit.add_argument('--confirm-reviewed-meaning-scope-and-context', action='store_true', required=True)
    op_reconcile = sub.add_parser('operator-reconcile', help='Observe canonical state for a persisted uncertain submission; never resend')
    op_reconcile.add_argument('--review-id', required=True)
    op_reconcile.add_argument('--plan-sha256', required=True)
    op_revoke = sub.add_parser('operator-revoke', help='Scrub local interpretation; canonical proposals survive')
    op_revoke.add_argument('--review-id', required=True)
    op_revoke.add_argument('--confirm-revoke', action='store_true', required=True)
    op_revoke_all = sub.add_parser('operator-revoke-all', help='Scrub all local interpretations; canonical proposals survive')
    op_revoke_all.add_argument('--confirm-revoke', action='store_true', required=True)
    args = parser.parse_args(argv)
    try:
        # Reuse the explicit, symlink-safe, non-initializing profile reader.
        inspector = EpisodeInspection(args.hermes_home, root_id=args.root_id, project=args.project)
        if args.operation in ('operator-revoke', 'operator-revoke-all'):
            result = ReviewBridgeControl(inspector.home, inspector.binding).revoke(getattr(args, 'review_id', None))
        elif args.operation in ('revoke', 'revoke-all'):
            result = CandidateInboxControl(inspector.home, inspector.binding).revoke(getattr(args, 'batch_id', None))
        else:
            if inspector.capture_state != 'enabled' or inspector.recall_state != 'enabled':
                CandidateInboxControl(inspector.home, inspector.binding).revoke()
                raise CaptureRefused('inbox_capture_or_recall_disabled')
            recall, _ = EpisodeRecall.from_capture(_ExistingCapture(inspector))
            inbox, reason = DurableCandidateInbox.from_recall(recall)
            if inbox is None:
                raise CaptureRefused('inbox_' + reason)
            if args.operation.startswith('operator-'):
                bridge, reason = OperatorReviewBridge.from_inbox(inbox)
                if bridge is None:
                    raise CaptureRefused('operator_review_' + reason)
                if args.operation == 'operator-list':
                    result = bridge.list_reviews()
                elif args.operation == 'operator-inspect':
                    result = bridge.inspect(args.review_id)
                elif args.operation == 'operator-reconcile':
                    result = bridge.reconcile(args.review_id, args.plan_sha256)
                elif args.operation == 'operator-submit':
                    result = bridge.submit(args.review_id, args.plan_sha256,
                                           confirm=args.confirm_reviewed_meaning_scope_and_context)
                else:
                    from elm_plugin.batch_extraction import _decode, MAX_RESPONSE_BYTES
                    raw = sys.stdin.buffer.read(MAX_RESPONSE_BYTES + 1)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise CaptureRefused('operator_semantics_too_large')
                    result = bridge.prepare(args.batch_id, args.candidate_id, _decode(raw.decode('utf-8')),
                                            request_key=args.request_key, replaces_review_id=args.replaces_review_id)
            elif args.operation == 'list':
                result = inbox.list_batches()
            elif args.operation == 'prepare':
                result = inbox.prepare(args.locator, request_key=args.request_key)
            elif args.operation == 'validate':
                from elm_plugin.batch_extraction import MAX_RESPONSE_BYTES
                raw = sys.stdin.buffer.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise CaptureRefused('extractor_response_too_large')
                result = inbox.validate(args.batch_id, raw.decode('utf-8'))
            else:
                result = inbox.review(args.batch_id)
        print(encoded(result))
        return 0
    except (CaptureRefused, ElmError, OSError, sqlite3.Error, ValueError, TypeError, KeyError, UnicodeError) as exc:
        code = str(exc) if isinstance(exc, CaptureRefused) else 'inbox_unavailable'
        print(encoded({'error': code, 'contents_included': False, 'canonical_write': 'unknown_if_submission_started' if args.operation == 'operator-submit' else False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
