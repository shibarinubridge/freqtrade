"""Public OHLCV annual-profile history collector. No trading credentials/actions."""
import concurrent.futures,datetime as dt,json,pathlib,time,urllib.request,os
P=pathlib.Path(__file__).resolve().parent/'.runtime/chart-history';COINS=('BTC','ETH','SOL','HYPE')
def fetch(coin):
 now=int(time.time()*1000);year=dt.datetime.fromtimestamp(now/1000,dt.timezone.utc).year;start=int(dt.datetime(year,1,1,tzinfo=dt.timezone.utc).timestamp()*1000);day=now//86400000*86400000;rows=[]
 for interval,begin,step in [('1d',start,86400000),('1h',day,3600000)]:
  req=urllib.request.Request('https://api.hyperliquid.xyz/info',data=json.dumps({'type':'candleSnapshot','req':{'coin':coin,'interval':interval,'startTime':begin,'endTime':now}}).encode(),headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=8) as r:raw=json.load(r)
  rows += [{'t':x['t'],'step':step,'low':float(x['l']),'high':float(x['h']),'volume':float(x['v'])} for x in raw if x['t']>=begin and x['t']+step<=now and (interval=='1h' or x['t']<day)]
 P.mkdir(parents=True,exist_ok=True);out={'coin':coin,'source':'Hyperliquid public candleSnapshot','method':'D1 + current-day closed H1','captured_ms':now,'rows':sorted(rows,key=lambda x:x['t'])};tmp=P/(coin+'.tmp');tmp.write_text(json.dumps(out));tmp.replace(P/(coin+'.json'));return {'coin':coin,'rows':len(rows)}
def once():
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  for c in COINS:
   pass
  futures={pool.submit(fetch,c):c for c in COINS}
  for f,c in futures.items():
   try:print(json.dumps(f.result()),flush=True)
   except Exception as e:print(json.dumps({'coin':c,'error':type(e).__name__}),flush=True)
if __name__=='__main__':
 import sys
 if '--run' in sys.argv:
  P.mkdir(parents=True,exist_ok=True);(P/'collector.pid').write_text(str(os.getpid()));last=0
  while True:
   if time.time()-last>=3600:once();last=time.time()
   time.sleep(60)
 else:once()
