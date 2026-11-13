import contextlib,io,json,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from elm_plugin.local_grant import main

class GrantCliTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name)
  self.module=types.SimpleNamespace(get_hermes_home=lambda:self.home)
  self.store=MagicMock();self.store.grant_local.return_value={'expires':123}
 def tearDown(self):self.tmp.cleanup()
 def run_cli(self,args):
  out=io.StringIO()
  with patch.dict('sys.modules',hermes_constants=self.module),contextlib.redirect_stdout(out),contextlib.redirect_stderr(io.StringIO()):
   main(args,store=self.store)
  return json.loads(out.getvalue())
 def test_show_home_has_no_database_access(self):
  self.assertEqual(self.run_cli(['--show-home'])['hermes_home'],str(self.home.resolve()))
  self.assertEqual(self.store.mock_calls,[])
 def test_expected_home_required(self):
  with self.assertRaises(SystemExit):self.run_cli(['sid','--allow-session-clients'])
  self.assertEqual(self.store.mock_calls,[])
 def test_mismatch_refuses_before_storage(self):
  with self.assertRaises(SystemExit):self.run_cli(['sid','--expect-home',str(self.home/'wrong'),'--allow-session-clients'])
  self.assertEqual(self.store.mock_calls,[])
 def test_relative_path_refused(self):
  with self.assertRaises(SystemExit):self.run_cli(['sid','--expect-home','.','--allow-session-clients'])
  self.assertEqual(self.store.mock_calls,[])
 def test_exact_home_grants_and_prints_target(self):
  result=self.run_cli(['sid','--expect-home',str(self.home),'--allow-session-clients'])
  self.assertEqual(result['hermes_home'],str(self.home));self.store.grant_local.assert_called_once()
 def test_revoke_also_requires_correct_home(self):
  with self.assertRaises(SystemExit):self.run_cli(['sid','--revoke','--expect-home',str(self.home/'wrong')])
  self.assertEqual(self.store.mock_calls,[])
 def test_acknowledgment_still_required(self):
  with self.assertRaises(SystemExit):self.run_cli(['sid','--expect-home',str(self.home)])
  self.assertEqual(self.store.mock_calls,[])
