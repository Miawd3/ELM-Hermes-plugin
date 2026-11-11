"""Independent synthetic adversarial tests. All roots disposable; no network."""
import copy, hashlib, json, os, sys, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
BASE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(BASE), str(BASE.parents[1]), str(BASE.parents[1]/'engine')]
from elm_memory import governance as g
from elm_memory.locking import WriterLock
from elm_plugin import governance_reconcile_worker as worker
from elm_plugin.submission_reconciliation import observe_submission
from elm_plugin.engine import ElmError

def deny(event, args):
    if event in {'socket.connect','socket.getaddrinfo','socket.bind'}: raise RuntimeError('network denied')
sys.addaudithook(deny)

class CanonicalAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'.elm').mkdir(); (self.root/'20_projects/orion').mkdir(parents=True)
        identity = g.bootstrap_root_identity(self.root, apply=True, creator='synthetic-auditor',lock_timeout=0,recover_stale=False)
        self.payload = dict(submission_id=g.new_id('submission'), project='orion',subject='synthetic',predicate='prefers',object='blue',valid_from='2026-11-06T00:00:00Z',sensitivity='restricted',rationale='Synthetic audit only',source_refs=[],evidence=[])
        self.request = dict(root=str(self.root),root_id=identity['root_id'],identity_sha256=hashlib.sha256(g.root_identity_path(self.root).read_bytes()).hexdigest(),project='orion',submission_id=self.payload['submission_id'],payload=self.payload)
        self.binding=SimpleNamespace(path=self.root,**{k:self.request[k] for k in ('root_id','identity_sha256','project')})
    def submit(self, payload=None):
        value=payload or self.payload
        return g.submit_proposal_bundle(self.root,request=value,request_bytes=len(json.dumps(value).encode()),allowed_projects={'orion'},limits=g.ProposalLimits(),lock_timeout=0,recover_stale=False)
    def snapshot(self):
        return {str(p.relative_to(self.root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()}
    def observe(self):
        before=self.snapshot(); result=worker.inspect(self.request); self.assertEqual(before,self.snapshot()); return result
    def test_absent_never_permission(self):
        self.assertEqual(self.observe()['classification'],'absent_uncertain')
    def test_matched_repeat_and_disposable_projection(self):
        self.submit()
        for data in [None,b'invalid SQLite projection',b'forged accepted status']:
            if data is not None: (self.root/'.elm/index.sqlite').write_bytes(data)
            for i in range(2): self.assertEqual(self.observe()['classification'],'matched')
    def test_real_isolated_subprocess(self):
        self.submit(); result=observe_submission(self.root,self.binding,dict(submission_id=self.payload['submission_id'],payload=json.dumps(self.payload)))
        self.assertEqual(result['classification'],'matched')
    def test_same_id_wrong_digest(self):
        self.submit({**self.payload,'object':'red'})
        self.assertEqual(self.observe()['reason'],'payload_digest_mismatch')
    def test_identity_change(self):
        self.request['identity_sha256']='0'*64
        self.assertEqual(self.observe()['reason'],'root_identity_mismatch')
    def test_retired_id(self):
        p=self.submit(); g.delete_item(self.root,item_id=p['proposal_id'],actor='audit',reason_code='user_request',lock_timeout=0,recover_stale=False)
        self.assertEqual(self.observe()['reason'],'submission_id_retired')
    def test_canonical_corruption(self):
        p=self.submit(); (self.root/p['path']).write_text('{}')
        self.assertEqual(self.observe()['reason'],'canonical_state_invalid')
    def test_duplicate_submission(self):
        p=self.submit(); path=self.root/p['path']; data=json.loads(path.read_text()); data['proposal_id']=g.new_id('proposal'); path.with_name(data['proposal_id']+'.json').write_text(json.dumps(data))
        self.assertEqual(self.observe()['classification'],'unavailable')
    def test_prepared_and_committed_journals(self):
        p=self.submit(); target=self.root/p['path']; tid=g.new_id('transaction'); journal=g._journal_path(self.root,tid)
        data=dict(format_version=1,record_type='transaction',transaction_id=tid,operation='proposal-submit',actor='audit',created_at=g.utc_now(),state='prepared',changes=[dict(target=p['path'],action='write',before_exists=False,before_sha256=None,after_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),backup=None)])
        journal.parent.mkdir(exist_ok=True,parents=True)
        for state in ['prepared','committed']:
            data['state']=state; journal.write_text(json.dumps(data))
            self.assertEqual(self.observe()['reason'],'unfinished_governance_transaction')
    def test_busy_and_stale_locks_not_recovered(self):
        self.submit()
        with WriterLock(self.root,'synthetic-test',timeout=0): self.assertEqual(self.observe()['reason'],'writer_lock_unavailable')
        lock=self.root/'.elm/writer.lock'; lock.write_text(json.dumps(dict(pid=999999999,host='unknown',token='synthetic'))); os.utime(lock,(1,1))
        self.assertEqual(self.observe()['reason'],'writer_lock_unavailable'); self.assertTrue(lock.exists())
    def test_accepted_status_not_acceptance_action(self):
        p=self.submit(); g.accept_proposal(self.root,proposal_id=p['proposal_id'],actor='synthetic-audit',authority='user_ratified',lock_timeout=0,recover_stale=False)
        r=self.observe(); self.assertEqual(r['classification'],'matched');self.assertEqual(r['observed_canonical_status'],'accepted');self.assertIs(r['acceptance_performed'],False)
    def test_terminal_evidence_redaction(self):
        self.payload['evidence']=[dict(kind='document_section',source_uri='urn:synthetic:audit',content_sha256='1'*64,excerpt_sha256='2'*64,sensitivity='restricted')]
        p=self.submit(); g.accept_proposal(self.root,proposal_id=p['proposal_id'],actor='synthetic-audit',authority='user_ratified',lock_timeout=0,recover_stale=False)
        g.delete_item(self.root,item_id=p['evidence_ids'][0],actor='audit',reason_code='user_request',lock_timeout=0,recover_stale=False)
        self.assertEqual(self.observe()['classification'],'unverifiable')
    def test_prior_response_other_payload_same_ids_refused(self):
        self.submit(); prior=self.observe()
        row=dict(submission_id=self.payload['submission_id'],payload=json.dumps({**self.payload,'object':'changed payload'}))
        with patch('elm_plugin.submission_reconciliation.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(prior))):
            with self.assertRaises(ElmError): observe_submission(self.root,self.binding,row)
    def test_malformed_and_misbound_responses(self):
        self.submit(); good=self.observe(); row=dict(submission_id=self.payload['submission_id'],payload=json.dumps(self.payload))
        for change in [dict(request_sha256='0'*64),dict(format='wrong'),dict(submission_id=g.new_id('submission')),dict(authoritative_snapshot=False),dict(submission_performed=True),dict(proposal_id=None),dict(observed_canonical_status=None),dict(classification='invalid'),dict(extra=True)]:
            result={**good,**change}
            with self.subTest(change=change),patch('elm_plugin.submission_reconciliation.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(result))):
                with self.assertRaises(ElmError):observe_submission(self.root,self.binding,row)

from test_operator_review import OperatorReview
from elm_plugin import operator_review_store as review_store
from elm_plugin.operator_review import ReviewBridgeControl
from elm_plugin.episode_capture import CaptureRefused

class BridgeAudit(unittest.TestCase):
    setUp=OperatorReview.setUp
    start=OperatorReview.start
    prepare=OperatorReview.prepare
    semantics=OperatorReview.semantics
    add_source=OperatorReview.add_source
    response=OperatorReview.response
    accept_span=OperatorReview.accept_span
    rows=OperatorReview.rows
    restart=OperatorReview.restart
    restart_inbox=OperatorReview.restart_inbox
    def setup_review(self):
        self.start(); root=self.binding.path
        (root/'.elm').mkdir(parents=True); (root/'20_projects/orion').mkdir(parents=True)
        g.bootstrap_root_identity(root,apply=True,creator='synthetic',lock_timeout=0,recover_stale=False)
        path=g.root_identity_path(root); identity=json.loads(path.read_text()); identity['root_id']=self.binding.root_id; path.write_text(json.dumps(identity))
        self.binding.identity_sha256=hashlib.sha256(path.read_bytes()).hexdigest()
        return self.prepare()
    def engine_commit(self, *args, **kwargs):
        payload=kwargs['request']
        result=g.submit_proposal_bundle(self.binding.path,request=payload,request_bytes=len(json.dumps(payload).encode()),allowed_projects={'orion'},limits=g.ProposalLimits(),lock_timeout=0,recover_stale=False)
        raise ElmError('lost_reply','synthetic committed then lost reply')
    def test_lost_reply_restart_match_repeated_no_resend(self):
        plan=self.setup_review()
        with patch('elm_plugin.operator_review.run_engine',side_effect=self.engine_commit) as send:
            self.assertEqual(self.bridge.submit(plan['review_id'],plan['plan_sha256'],confirm=True)['state'],'unknown')
            self.restart()
            for _ in range(2):
                result=self.bridge.reconcile(plan['review_id'],plan['plan_sha256'])
                self.assertEqual(result['state'],'submitted'); self.assertFalse(result['accepted_memory']); self.assertFalse(result['retry_permitted'])
            self.bridge.submit(plan['review_id'],plan['plan_sha256'],confirm=True)
            self.assertEqual(send.call_count,1)
    def test_absent_intent_stays_blocked_after_restart(self):
        plan=self.setup_review()
        with self.inbox.control.transaction() as con:
            row=review_store.records(con)[0];row['state']='submitting';review_store.save(con,row)
        self.restart()
        with patch('elm_plugin.operator_review.run_engine') as send:
            result=self.bridge.reconcile(plan['review_id'],plan['plan_sha256'])
            self.assertEqual(result['state'],'submitting');self.assertEqual(result['reconciliation']['classification'],'absent_uncertain')
            with self.assertRaises(CaptureRefused):self.bridge.submit(plan['review_id'],plan['plan_sha256'],confirm=True)
            send.assert_not_called()
    def test_prepared_and_wrong_plan_refuse_before_reader(self):
        plan=self.setup_review()
        with patch('elm_plugin.operator_review.observe_submission') as reader:
            for digest in [plan['plan_sha256'],'0'*64]:
                with self.assertRaises(CaptureRefused):self.bridge.reconcile(plan['review_id'],digest)
            reader.assert_not_called()
    def test_revoked_unknown_stays_scrubbed_and_blocked(self):
        plan=self.setup_review()
        with patch('elm_plugin.operator_review.run_engine',side_effect=ElmError('timeout','synthetic')):
            self.bridge.submit(plan['review_id'],plan['plan_sha256'],confirm=True)
        ReviewBridgeControl(self.home,self.binding).revoke(plan['review_id'])
        with patch('elm_plugin.operator_review.observe_submission') as reader:
            with self.assertRaises(CaptureRefused):self.bridge.reconcile(plan['review_id'],plan['plan_sha256'])
            reader.assert_not_called()
        row=self.rows()[0];self.assertEqual(row['state'],'revoked_unknown');self.assertEqual(row['payload'],'{}')
    def test_response_failure_keeps_unknown(self):
        plan=self.setup_review()
        with patch('elm_plugin.operator_review.run_engine',side_effect=ElmError('timeout','synthetic')):
            self.bridge.submit(plan['review_id'],plan['plan_sha256'],confirm=True)
        with patch('elm_plugin.submission_reconciliation.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout='{}')):
            with self.assertRaises(ElmError):self.bridge.reconcile(plan['review_id'],plan['plan_sha256'])
        self.assertEqual(self.rows()[0]['state'],'unknown')

del OperatorReview
if __name__=='__main__':unittest.main(verbosity=2)

