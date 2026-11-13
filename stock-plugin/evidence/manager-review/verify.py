import sys,sqlite3,tempfile,json,threading,time,shlex
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from elm_plugin.stock_store import Store,session_key,Denied
from elm_plugin.stock_runtime import Runtime
with tempfile.TemporaryDirectory() as td:
 p=td+'/test.db'
 def connect():
  db=sqlite3.connect(p);db.execute('PRAGMA journal_mode=WAL');return db
 s=Store(connect);sid=session_key('a','cli');s.grant_local('a',project='p');r=s.insert(sid,'project','reviewed text',approved=False)
 snap=s.manager_snapshot(sid,'pending');s.change(sid,r['id'],'edit','UNREVIEWED')
 try:s.change(sid,r['id'],'approve',expected_revision=snap['revision'],expected_record=snap['records'][0]['version'])
 except Denied:pass
 else:raise AssertionError('stale approval accepted')
 print('PASS: reviewed-content guard rejects concurrent edit')
 original=s.state;counter=[0];started=threading.Event();done=threading.Event();threads=[]
 def writer():
  started.set()
  with connect() as db:db.execute('UPDATE stock_sessions SET enabled=0,revision=revision+1 WHERE session=?',(sid,))
  done.set()
 def state(db,sid,require=True):
  counter[0]+=1
  if counter[0]==2:
   t=threading.Thread(target=writer);threads.append(t);t.start();assert started.wait(1);time.sleep(.08);assert not done.is_set()
  return original(db,sid,require)
 s.state=state;snap=s.manager_snapshot(sid,'pending');assert len(snap['records'])==1
 for t in threads:t.join(2)
 assert done.is_set();s.state=original
 try:s.manager_snapshot(sid)
 except Denied:pass
 else:raise AssertionError('revoked read accepted')
 print('PASS: manager snapshot serializes concurrent revocation; subsequent read denied')
 s.grant_local('a');rt=Runtime(object(),s)
 def cmd(payload,sess='a'):
  return json.loads(rt.command('manager '+shlex.quote(json.dumps(payload)),session_id=sess,platform='local'))
 bad=[None,[],{}, {'action':'list','status':'approved','offset':True},{'action':'list','status':'approved','offset':-1},{'action':'list','status':'approved','offset':0,'session':'b'},{'action':['list']}]
 for payload in bad:assert 'error' in cmd(payload),payload
 assert 'error' in cmd({'action':'list','status':'approved','offset':0},'b')
 assert len(cmd({'action':'list','status':'approved','offset':0})['records'])==0
 print('PASS: 8 malformed/unauthorized manager payloads denied without data')
