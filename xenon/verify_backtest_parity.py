"""Verify historical-port indicators against the frozen prospective detector."""
import pathlib,sys,json,datetime as dt
import pandas as pd
from freqtrade.enums import RunMode
P=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(P/'strategies'))
from XenonFVG import XenonFVG,decode
from XenonFVGBacktest import XenonFVGBacktest
out={'status':'PASS','scope':'Exact signal/tag/geometry parity, not fill or PnL equivalence','datasets':{}}
for name in ['native_m15','august_m1']:
 root=P/'.runtime/backtest'/name;cfg=json.loads((root/'config.json').read_text());cfg['runmode']=RunMode.BACKTEST;s=XenonFVGBacktest(cfg);s.bot_start();live=XenonFVG({'dry_run':True});coins={}
 for coin in ['BTC','ETH','SOL','HYPE']:
  pair=coin+'/USDC:USDC';df=pd.read_feather(root/'data/futures'/f'{coin}_USDC_USDC-15m-futures.feather');a=live.populate_indicators(df.copy(),{'pair':pair});b=s.populate_indicators(df.copy(),{'pair':pair})
  for k in ['fvg_direction','fvg_tag','fvg_limit','fvg_stop','fvg_target']:pd.testing.assert_series_equal(a[k],b[k],check_dtype=False)
  flags=b.loc[b.fvg_direction!=0];coins[coin]={'bars':len(df),'eligible_signals':len(flags),'tag_geometry':'PASS'}
  for n in [len(df)//2,len(df)-1]:
   prefix=s.populate_indicators(df.iloc[:n].copy(),{'pair':pair});pd.testing.assert_series_equal(prefix.fvg_tag,b.fvg_tag.iloc[:n],check_dtype=False)
 out['datasets'][name]=coins
(P/'.runtime/backtest/parity.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
