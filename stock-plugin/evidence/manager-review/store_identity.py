from pathlib import Path
exec((Path(__file__).with_name('verify.py')).read_text().split('with tempfile')[0])
with tempfile.TemporaryDirectory() as td:
 p=td+'/db';s=Store(lambda:sqlite3.connect(p));sid=session_key('a','cli');s.grant_local('a',project='first');r=s.insert(sid,'reference','old',approved=False);snap=s.manager_snapshot(sid,'pending')
 with sqlite3.connect(p) as db:db.execute("UPDATE stock_read_epoch SET identity=?",('f'*32,))
 for op in [lambda:s.insert(sid,'project','new',approved=True,expected_revision=snap['revision'],expected_store=snap['store_identity']),lambda:s.change(sid,r['id'],'approve',expected_revision=snap['revision'],expected_record=snap['records'][0]['version'],expected_store=snap['store_identity'])]:
  try:op()
  except Denied as e:assert str(e)=='memory_changed_retry'
  else:raise AssertionError('replacement bypass')
 print('PASS: save and record mutation reject replaced database identity')
