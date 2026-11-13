"""Bounded public-to-owner research telemetry; never publishes source paths/tokens."""
import json,pathlib,sqlite3,time
ROOT=pathlib.Path(__file__).resolve().parent/'.runtime'
def collect():
 result={'executor':'scheduled_agent','scheduled':False,'last_run_confirmed':False,'queue':{},'experiments':0,'observed_ms':int(time.time()*1000)}
 try:
  worker=json.loads((ROOT/'research-worker.json').read_text());result.update({k:worker[k] for k in ('scheduled','next_run','last_run_confirmed') if k in worker})
  with sqlite3.connect(f'file:{ROOT}/video-intake.sqlite?mode=ro',uri=True) as db:
   result['queue']=dict(db.execute('SELECT state,COUNT(*) FROM jobs GROUP BY state'));result['experiments']=db.execute('SELECT COUNT(*) FROM experiments').fetchone()[0]
 except (OSError,ValueError,sqlite3.Error):result['status_error']='RESEARCH_STATUS_UNAVAILABLE'
 return result
