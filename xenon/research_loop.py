"""Durable research queue and append-only experiment memory for scheduled agents.
No trading credentials, model-produced executable code, or deployment actions.
"""
import argparse,contextlib,hashlib,json,pathlib,sqlite3,time,uuid,math
from video_intake import register
ROOT=pathlib.Path(__file__).resolve().parent;RUNTIME=ROOT/'.runtime';DB=RUNTIME/'video-intake.sqlite'
@contextlib.contextmanager
def database(path=None):
 path=pathlib.Path(path or DB);path.parent.mkdir(parents=True,exist_ok=True)
 with sqlite3.connect(path,timeout=10) as db:
  db.row_factory=sqlite3.Row
  db.execute('CREATE TABLE IF NOT EXISTS jobs(sha TEXT PRIMARY KEY,path TEXT,state TEXT,lease_until INTEGER,token TEXT,attempts INTEGER,last_error TEXT,updated_ms INTEGER)')
  db.execute('CREATE TABLE IF NOT EXISTS experiments(id TEXT PRIMARY KEY,sha TEXT,parent TEXT,hypothesis TEXT,artifact TEXT,artifact_sha TEXT,result TEXT,created_ms INTEGER)')
  yield db

def enqueue(path,db_path=None):
 item=register(path,db_path);now=int(time.time()*1000)
 with database(db_path) as db:db.execute('INSERT OR IGNORE INTO jobs VALUES(?,?,?,0,NULL,0,NULL,?)',(item['sha256'],str(pathlib.Path(path).resolve()),'queued',now))
 return item

def claim(db_path=None,now=None):
 now=int(time.time()*1000) if now is None else now;token=uuid.uuid4().hex
 with database(db_path) as db:
  db.execute('BEGIN IMMEDIATE')
  row=db.execute("SELECT * FROM jobs WHERE (state='queued' OR (state='processing' AND lease_until<?)) AND attempts<3 ORDER BY updated_ms LIMIT 1",(now,)).fetchone()
  if not row:return None
  db.execute("UPDATE jobs SET state='processing',lease_until=?,token=?,attempts=attempts+1,updated_ms=? WHERE sha=?",(now+3600000,token,now,row['sha']))
  return dict(row)|{'token':token,'lease_until':now+3600000}

def finish(sha,token,artifact,db_path=None):
 artifact=pathlib.Path(artifact).resolve();data=json.loads(artifact.read_text())
 if data.get('source_sha256')!=sha:raise ValueError('Source hash mismatch')
 for field in ('source_rules','assumptions','unresolved','evidence'):
  if not isinstance(data.get(field),list):raise ValueError('Missing structured '+field)
 for rule in data['source_rules']:
  if not isinstance(rule.get('text'),str) or not isinstance(rule.get('start_s'),(int,float)) or not isinstance(rule.get('end_s'),(int,float)) or not 0<=rule['start_s']<=rule['end_s']:raise ValueError('Source rule requires valid timestamp evidence')
 state='blocked_rules' if data['unresolved'] else 'analysis_ready'
 with database(db_path) as db:
  cur=db.execute("UPDATE jobs SET state=?,token=NULL,lease_until=0,last_error=NULL,updated_ms=? WHERE sha=? AND token=? AND state='processing' AND lease_until>=?",(state,int(time.time()*1000),sha,token,int(time.time()*1000)))
  if cur.rowcount!=1:raise ValueError('Expired or foreign lease')
 return {'state':state,'artifact':str(artifact),'execution_enabled':False}

def record_experiment(sha,hypothesis,artifact,parent=None,db_path=None):
 p=pathlib.Path(artifact).resolve();raw=p.read_bytes();result=json.loads(raw)
 # A held-out period must be consumed once per lineage. Returning to it after
 # seeing the answer cannot create a new independent validation result.
 required=('development_id','validation_id','data_sha256','variant_id','net_after_costs','stress_net','trade_count','lookahead_pass','native_lifecycle_pass')
 if any(k not in result for k in required):raise ValueError('Incomplete evaluation evidence')
 if result['development_id']==result['validation_id']:raise ValueError('Development and validation overlap')
 if any(isinstance(result[k],bool) or not isinstance(result[k],(int,float)) or not math.isfinite(result[k]) for k in ('net_after_costs','stress_net')):raise ValueError('Invalid performance')
 if isinstance(result['trade_count'],bool) or not isinstance(result['trade_count'],int) or result['trade_count']<0:raise ValueError('Invalid sample size')
 if any(not isinstance(result[k],bool) for k in ('lookahead_pass','native_lifecycle_pass')):raise ValueError('Invalid test result')
 with database(db_path) as db:
  previous=[json.loads(r[0]) for r in db.execute('SELECT result FROM experiments WHERE sha=?',(sha,))]
  if len(previous)>=3:raise ValueError('Three-variant research budget exhausted; new data required')
  if any(x['validation_id']==result['validation_id'] and x['data_sha256']==result['data_sha256'] for x in previous):raise ValueError('Validation set already consumed; acquire new untouched data')
  if parent and not db.execute('SELECT 1 FROM experiments WHERE id=? AND sha=?',(parent,sha)).fetchone():raise ValueError('Unknown parent experiment')
  id=uuid.uuid4().hex;db.execute('INSERT INTO experiments VALUES(?,?,?,?,?,?,?,?)',(id,sha,parent,hypothesis,str(p),hashlib.sha256(raw).hexdigest(),json.dumps(result),int(time.time()*1000)))
 return {'id':id,'status':'recorded','execution_enabled':False}

def status(db_path=None):
 with database(db_path) as db:return {'source_mode':'user_supplied_only','executor':'scheduled_agent','jobs':[dict(r) for r in db.execute('SELECT sha,state,attempts,last_error,updated_ms FROM jobs ORDER BY updated_ms DESC')],'experiments':[dict(r) for r in db.execute('SELECT id,sha,hypothesis,result,created_ms FROM experiments ORDER BY created_ms DESC LIMIT 30')]}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['enqueue','claim','status','finish','record']);p.add_argument('--file');p.add_argument('--sha');p.add_argument('--token');p.add_argument('--hypothesis');p.add_argument('--parent');a=p.parse_args()
 if a.action=='enqueue':out=enqueue(a.file)
 elif a.action=='claim':out=claim()
 elif a.action=='finish':out=finish(a.sha,a.token,a.file)
 elif a.action=='record':out=record_experiment(a.sha,a.hypothesis,a.file,a.parent)
 else:out=status()
 print(json.dumps(out))
