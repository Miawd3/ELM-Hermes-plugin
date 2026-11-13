import sys,tempfile,sqlite3,time,statistics,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from elm_plugin.stock_store import Store,session_key
with tempfile.TemporaryDirectory() as d:
 s=Store(lambda: sqlite3.connect(d+'/db')); a=session_key('a','desktop');b=session_key('b','desktop')
 s.settings(a,{'enabled':True});s.settings(b,{'enabled':True})
 exact=s.insert(a,'reference','Door unlock code 7142',approved=True)['id']
 for i in range(20):s.insert(a,'reference',f'Door decoration {i}',approved=True)
 assert s.records(a,'door unlock code')[0]['id']==exact
 assert s.records(a,'door door door unlock code')[0]['id']==exact
 secret=s.insert(b,'reference','Door unlock code secret',approved=True)['id']
 assert secret not in [x['id'] for x in s.records(a,'door unlock code')]
 pending=s.insert(a,'reference','Door unlock code pending')['id']
 assert pending not in [x['id'] for x in s.records(a,'door unlock code')]
 literal=s.insert(a,'reference','foo_bar example',approved=True)['id'];s.insert(a,'reference','fooXbar',approved=True)
 assert [x['id'] for x in s.records(a,'foo_bar')]==[literal]
 unicode=s.insert(a,'reference','ДВЕРЬ ключ код',approved=True)['id']
 assert s.records(a,'дверь КЛЮЧ код')[0]['id']==unicode
 assert secret not in [x["id"] for x in s.records(a,"%_' OR 1=1 --")]
 allrows=s.records(a,'door',limit=50)
 assert s.records(a,'door',limit=12)+s.records(a,'door',limit=12,offset=12)==allrows
 # Equal coverage retains recency and empty query unchanged.
 newest=s.insert(a,'reference','door recently repainted',approved=True)['id']
 assert s.records(a,'door')[0]['id']==newest
 assert s.records(a,'')[0]['id']==newest
 print('9 adversarial/behavior checks passed')
 # Synthetic SQL latency comparison, no runtime quality interpretation.
 with s.open() as db:
  db.executemany('INSERT INTO stock_records VALUES(?,?,?,?,?,?,?,?,?,?,?)',[(f'p{i}','chat:'+a,'reference',f'door unlock {i}','[]','approved',a,None,1,i,f'door unlock {i}') for i in range(100000)])
 with s.open() as db:
  args=['chat:'+a,'approved','%door%','%unlock%','%code%'];pred="search_text LIKE ? ESCAPE '\\'"
  where='scope IN (?) AND status=? AND ('+' OR '.join([pred]*3)+')'
  q='SELECT id,kind,content,tags,source_id,scope FROM stock_records WHERE '+where+' ORDER BY '
  rank='('+' + '.join(['CASE WHEN '+pred+' THEN 1 ELSE 0 END']*3)+') DESC,'
  for label,sql,par in [('old',q+'updated DESC,id DESC LIMIT 12',args),('new',q+rank+'updated DESC,id DESC LIMIT 12',args+['%door%','%unlock%','%code%'])]:
   ms=[]
   for _ in range(6):
    t=time.perf_counter();db.execute(sql,par).fetchall();ms.append((time.perf_counter()-t)*1000)
   print(label,'median_ms',round(statistics.median(ms[1:]),2),'runs',ms)
