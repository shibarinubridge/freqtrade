"""Best-effort observation output; never changes order approval or signal rules."""
import copy,datetime as dt,json,pathlib,time
ROOT=pathlib.Path(__file__).resolve().parents[1]/'.runtime/fvg-visual'
def atomic(path,data):
 ROOT.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,allow_nan=False));tmp.replace(path)
def publish(coin,view,rows,boot_ms,version):
 try:
  now=int(time.time()*1000);path=ROOT/(coin+'.json');prior={}
  if path.exists():prior={e['id']:e.get('observed_ms') for e in json.loads(path.read_text()).get('events',[])}
  out=copy.deepcopy(view);out.update(source='freqtrade_strategy_runtime',captured_ms=now,boot_ms=boot_ms,strategy='XenonFVG',strategy_version=version)
  out['events']=[e for e in out['events'] if e['available_ms']<=now]
  for e in out['events']:e.update(observed_ms=prior.get(e['id']) or now,origin='historical_reconstruction' if e['available_ms']<boot_ms else 'strategy_observation')
  out['candles']=[{'t':r['t'],'o':r['o'],'h':r['h'],'l':r['l'],'c':r['c'],'v':r['v'],'closed':True} for r in rows[-600:] if r['end']<=now]
  atomic(path,out)
 except Exception:pass

def decision(pair,kind,reason,tag=None,extra=None):
 try:
  now=int(time.time()*1000);coin=pair.split('/')[0];path=ROOT/(coin+'-decisions.json');history=json.loads(path.read_text()) if path.exists() else []
  base={'kind':kind,'reason':reason,'tag':tag,'extra':extra or {}}
  if history and all(history[-1].get(k)==v for k,v in base.items()):return
  base.update(id=f'{coin}:{now}:{kind}',observed_ms=now,origin='strategy_callback');history.append(base);atomic(path,history[-80:])
 except Exception:pass
