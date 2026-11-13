"""User-supplied video inventory; registration does not claim analysis/testing."""
import argparse,hashlib,json,pathlib,sqlite3,time
ROOT=pathlib.Path(__file__).resolve().parent
POLICY=ROOT/'video-learning.json'
def register(path,db_path=None):
 path=pathlib.Path(path).resolve(strict=True)
 if not path.is_file():raise ValueError('Video must be a local file')
 digest=hashlib.sha256()
 with path.open('rb') as source:
  for chunk in iter(lambda:source.read(1048576),b''):digest.update(chunk)
 sha=digest.hexdigest();db_path=pathlib.Path(db_path or ROOT/'.runtime/video-intake.sqlite');db_path.parent.mkdir(parents=True,exist_ok=True)
 with sqlite3.connect(db_path) as db:
  db.execute('CREATE TABLE IF NOT EXISTS videos(sha256 TEXT PRIMARY KEY,name TEXT,path TEXT,bytes INTEGER,registered_ms INTEGER,status TEXT)')
  cursor=db.execute('INSERT OR IGNORE INTO videos VALUES(?,?,?,?,?,?)',(sha,path.name,str(path),path.stat().st_size,int(time.time()*1000),'registered'))
  status=db.execute('SELECT status FROM videos WHERE sha256=?',(sha,)).fetchone()[0]
 return {'sha256':sha,'file':path.name,'status':status,'duplicate':cursor.rowcount==0,'source':'user_supplied','execution_enabled':False}
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('file');args=parser.parse_args();print(json.dumps(register(args.file)))
