"""Synthetic latency/target-placement probe; not a quality benchmark.
Run from stock-plugin: python tests/search_ranking_probe.py
"""
import json,sqlite3,tempfile,time,statistics,sys,runpy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from elm_plugin.stock_store import Store,session_key
OldStore=runpy.run_path(str(Path(__file__).resolve().parents[1]/'evidence/search-ranking-baseline.py'))['Store']
out=[]
for n in (1000,10000):
 with tempfile.TemporaryDirectory() as d:
  store=Store(lambda:sqlite3.connect(Path(d)/'db'));sid=session_key('probe','cli');store.settings(sid,{'enabled':True})
  with store.open() as db:
   db.executemany('INSERT INTO stock_records VALUES(?,?,?,?,?,?,?,?,?,?,?)',[(str(i),'chat:'+sid,'reference','door unlock code violet' if i==0 else f'door decorative item {i}','[]','approved',sid,None,i,i,'door unlock code violet []' if i==0 else f'door decorative item {i} []') for i in range(n)])
  baseline=OldStore(store.connection)
  old=[];new=[]
  for i in range(12):
   t=time.perf_counter()
   ids=baseline.records(sid,'door unlock code')
   old.append((time.perf_counter()-t)*1000)
   t=time.perf_counter();rows=store.records(sid,'door unlock code');new.append((time.perf_counter()-t)*1000)
  out.append(dict(records=n,baseline_target_present=any(r['id']=='0' for r in ids),ranked_target_first=rows[0]['id']=='0',baseline_p50_ms=statistics.median(old),ranked_p50_ms=statistics.median(new),note='Warm synthetic common-term workload; same full Store.records API, database, query and limit. Not end-to-end app performance.'))
print(json.dumps(out,indent=2))
