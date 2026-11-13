"""Pull-based private relay for official FreqUI. The bot stays on loopback.

Browser session tokens authenticate only the hosted gateway. The real local API
credentials are injected here and never sent to the gateway or the browser.
"""
import base64,concurrent.futures,json,pathlib,re,sqlite3,sys,time,urllib.request,urllib.parse,urllib.error,termios
from adapter import Client,ModeError,NoRedirect
P=pathlib.Path(__file__).resolve().parent
READS=set('ping version show_config health status profit profit_all balance count entries exits mix_tags performance stats daily weekly monthly whitelist blacklist locks trades logs sysinfo plot_config pair_candles pair_history strategies exchanges markets edge historic_balance available_pairs'.split())
WRITES={'start','stop','pause','stopentry','stopbuy','pair_candles','pair_history'}
def allowed(method,path):
    u=urllib.parse.urlsplit(path)
    if u.scheme or u.netloc or len(path)>2500 or re.search(r'\.\.|%2e|//',path,re.I):return False
    if method=='GET':return u.path in READS or bool(re.fullmatch(r'strategy/[A-Za-z0-9_-]+|trade/[0-9]+',u.path))
    return method=='POST' and u.path in WRITES

class Relay:
    def __init__(self,auth_path=None,ledger=None):
        self.client=Client(auth_path);self.ledger=pathlib.Path(ledger) if ledger else P/'.runtime/native-relay.sqlite'
        with sqlite3.connect(self.ledger) as db:db.execute('CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY,status TEXT,result TEXT,http_status INTEGER)')
    def execute(self,job):
        method,path=job.get('method'),job.get('path','');id=job.get('id','')
        if not allowed(method,path):return {'id':id,'status':403,'data':{'detail':'Endpoint not exposed by the dry-run relay.'}}
        if int(time.time()*1000)>=job.get('deadline_ms',0):return {'id':id,'status':504,'data':{'detail':'Expired before execution; no operation attempted.'}}
        try:self.client.config()
        except Exception:return {'id':id,'status':503,'data':{'detail':'Hyperliquid dry-run mode is not verified.'}}
        reserved=False
        if method=='POST':
            with sqlite3.connect(self.ledger,timeout=5) as db:
                cur=db.execute('INSERT OR IGNORE INTO receipts VALUES(?,?,NULL,NULL)',(id,'started'));reserved=cur.rowcount==1
                if not reserved:
                    row=db.execute('SELECT status,result,http_status FROM receipts WHERE id=?',(id,)).fetchone()
                    return {'id':id,'status':row[2] or 503,'data':json.loads(row[1]) if row[1] else {'detail':'Previous execution is indeterminate; not repeated.'}}
        try:
            auth=json.loads(self.client.auth_path.read_text());token=base64.b64encode((auth['username']+':'+auth['password']).encode()).decode()
            body=json.dumps(job.get('body') or {}).encode() if method=='POST' else None
            req=urllib.request.Request('http://127.0.0.1:8091/api/v1/'+path,method=method,data=body,headers={'Authorization':'Basic '+token,'Content-Type':'application/json'})
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
            try:
                with opener.open(req,timeout=8) as response:status=response.status;raw=response.read(1500001)
            except urllib.error.HTTPError as e:status=e.code;raw=e.read(1500001)
            if len(raw)>1500000:status=413;data={'detail':'Response too large; reduce candle/trade count.'}
            else:
                text=raw.decode()
                for value in auth.values():
                    if isinstance(value,str) and len(value)>12:text=text.replace(value,'[REDACTED]')
                data=json.loads(text)
            if method=='GET' and path.split('?')[0]=='show_config' and status==200:
                # The HTTP gateway implements the pre-WebSocket API contract.
                data['xenon_upstream_api_version']=data.get('api_version');data['api_version']=2.19;data['xenon_transport']='private-http-relay'
            result={'id':id,'status':status,'data':data}
        except Exception:result={'id':id,'status':502,'data':{'detail':'Local Freqtrade RPC unavailable; request not retried.'}}
        if reserved:
            with sqlite3.connect(self.ledger,timeout=5) as db:db.execute('UPDATE receipts SET status=?,result=?,http_status=? WHERE id=?',('done',json.dumps(result['data']),result['status'],id))
        return result

    def run(self,url,token):
        assert urllib.parse.urlparse(url).hostname=='calm-frequi.lexnerg.chatgpt.site'
        opener=urllib.request.build_opener(NoRedirect());pending={};results=[]
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            while True:
                try:
                    for future in list(pending):
                        if future.done():
                            try:results.append(future.result())
                            except Exception:results.append({'id':pending[future],'status':502,'data':{'detail':'Local worker failed.'}})
                            del pending[future]
                    cfg=self.client.config()
                    outgoing=[];size=0
                    for r in results:
                        size+=len(json.dumps(r))
                        if size>1700000:break
                        outgoing.append(r)
                    request=urllib.request.Request(url+'/xenon/agent',data=json.dumps({'dry_run':True,'state':cfg.get('state'),'results':outgoing}).encode(),headers={'Content-Type':'application/json','OAI-Sites-Authorization':'Bearer '+token})
                    with opener.open(request,timeout=20) as response:body=json.load(response)
                    results=results[len(outgoing):]
                    for job in body.get('jobs',[]):
                        f=pool.submit(self.execute,job);pending[f]=job['id']
                    time.sleep(.65)
                except KeyboardInterrupt:return
                except Exception as e:
                    print('Native relay waiting:',type(e).__name__,flush=True);time.sleep(3)

if __name__=='__main__':
    if sys.stdin.isatty():
        attrs=termios.tcgetattr(0);attrs[3]&=~termios.ECHO;termios.tcsetattr(0,termios.TCSANOW,attrs)
    print('READY for private FreqUI connection JSON (hidden)',flush=True);c=json.loads(sys.stdin.readline());Relay().run(c['url'],c['token'])
