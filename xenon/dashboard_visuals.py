"""Read-only strategy drawings and public candles. No execution/control side effects."""
import concurrent.futures,json,pathlib,time,urllib.request
NATIVE=pathlib.Path(__file__).resolve().parent/'.runtime/fvg-visual'
COINS=('BTC','ETH','SOL','HYPE');STEP=900000
_cache={};_last=0

def public_candles(coin,now):
 try:
  payload={'type':'candleSnapshot','req':{'coin':coin,'interval':'15m','startTime':now-2*STEP,'endTime':now}}
  req=urllib.request.Request('https://api.hyperliquid.xyz/info',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=3) as response:raw=json.load(response)
  return coin,{'observed_ms':int(time.time()*1000),'candles':[{'t':x['t'],**{k:float(x[k]) for k in ('o','h','l','c','v')},'closed':x['t']+STEP<=now,'source':'hyperliquid_public_candle'} for x in raw if x['t']<=now]}
 except Exception:return coin,None

def collect(root=None):
 global _last
 P=pathlib.Path(root) if root else pathlib.Path('/workspace/trading-review/hyperliquid/intraday-1000/live')
 now=int(time.time()*1000)
 if time.monotonic()-_last>5:
  with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
   for coin,result in pool.map(lambda c:public_candles(c,now),COINS):
    if result:_cache[coin]=result
  _last=time.monotonic()
 try:shadow=json.loads((P/'fvg-forward.json').read_text())
 except (OSError,ValueError):shadow={}
 output={}
 for coin in COINS:
  try:view=json.loads((NATIVE/(coin+'.json')).read_text())
  except (OSError,ValueError):view=None
  try:decisions=json.loads((NATIVE/(coin+'-decisions.json')).read_text())[-80:]
  except (OSError,ValueError):decisions=[]
  bars={x['t']:x for x in (view or {}).get('candles',[])}
  if not bars:
   try:bars={x['t']:{'t':x['t'],**{k:float(x[k]) for k in ('o','h','l','c','v')},'closed':x['t']+STEP<=now,'source':'public_collector'} for x in json.loads((P/'data'/f'{coin}-15m.json').read_text())[-600:] if x['t']<=now}
   except (OSError,ValueError):pass
  market=_cache.get(coin,{})
  # Display candles can update before strategy analysis. Confirmation uses the
  # native trace exclusively, never this public forming candle.
  for x in market.get('candles',[]):bars[x['t']]=x
  for x in bars.values():x['closed']=x['t']+STEP<=now
  raw=shadow.get('positions',{}).get(coin) or shadow.get('pending',{}).get(coin)
  output[coin]={'analysis':{k:v for k,v in (view or {}).items() if k!='candles'} if view else None,'decisions':decisions,'candles':sorted(bars.values(),key=lambda x:x['t'])[-600:],'market_observed_ms':market.get('observed_ms'),'shadow_plan':raw,'shadow_state':'position' if coin in shadow.get('positions',{}) else 'pending' if coin in shadow.get('pending',{}) else 'waiting'}
 return {'schema':1,'mode':'OBSERVATION_ONLY','observed_ms':now,'timeframe':'15m','coins':output}
