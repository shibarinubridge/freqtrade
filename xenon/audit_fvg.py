"""Local audit against user-held research data; no raw dataset redistribution."""
import argparse,importlib.util,json,pathlib,sys,datetime as dt
import pandas as pd
P=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(P/'strategies'))
from fvg_rules import detect
from XenonFVG import XenonFVG,decode,planned_rr
parser=argparse.ArgumentParser();parser.add_argument('--reference',required=True);args=parser.parse_args()
spec=importlib.util.spec_from_file_location('reference_fvg',args.reference);r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
out={'scope':'Detector/indicator parity only, not PnL equivalence','coins':{},'checks':0}
for coin in r.COINS:
 rows=r.load(coin);expected,counts=r.detect(coin,rows);actual,actualcounts=detect(coin,rows);assert actual==expected and actualcounts==counts;out['checks']+=2
 for n in [600,1000,2000,len(rows)-1]:
  prefix,_=detect(coin,rows[:n]);filtered={t:v for t,v in actual.items() if t<=rows[n-1]['end']};assert prefix==filtered;out['checks']+=1
 df=pd.DataFrame([{'date':pd.to_datetime(x['t'],unit='ms',utc=True),'open':x['o'],'high':x['h'],'low':x['l'],'close':x['c'],'volume':x['v']} for x in rows]);s=XenonFVG({'dry_run':True});analyzed=s.populate_entry_trend(s.populate_indicators(df,{'pair':coin+'/USDC:USDC'}),{})
 kept=0
 for i,x in analyzed.iterrows():
  if x.enter_long or x.enter_short:
   o=decode(x.enter_tag);assert o['signal_time']==int(x.date.timestamp()*1000)+900000;assert o['signal_time'] in expected;original=expected[o['signal_time']][0]['order'];assert planned_rr(original)>=1
   for k in ['entry_limit','stop','target']:assert abs(o[k]-original[k])<=max(1e-9,abs(original[k])*1e-10)
   kept+=1;out['checks']+=6
 expected_kept=sum(planned_rr(e['order'])>=1 for items in expected.values() for e in items);assert kept==expected_kept;out['checks']+=1
 out['coins'][coin]={'candles':len(rows),'reference_orders':sum(map(len,expected.values())),'eligible_minimum1R_all_taker_costs':kept}
out['status']='PASS';out['at_utc']=dt.datetime.now(dt.timezone.utc).isoformat();(P/'.runtime/fvg-signal-parity.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
