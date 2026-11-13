"""Convert existing immutable user research snapshots to native Freqtrade data."""
import json,pathlib,hashlib,datetime as dt
import pandas as pd
from freqtrade.data.history.datahandlers.featherdatahandler import FeatherDataHandler
from freqtrade.enums import CandleType
P=pathlib.Path(__file__).resolve().parent;R=P/'.runtime/backtest';R.mkdir(exist_ok=True)
ROOT=pathlib.Path('/workspace/trading-review');COINS=['BTC','ETH','SOL','HYPE']
for name in ['native_m15','august_m1']:
 out=R/name;out.mkdir(exist_ok=True);(out/'data').mkdir(exist_ok=True);handler=FeatherDataHandler(out/'data');opens={'prices':{},'main_times':{},'price_step':60000 if name=='august_m1' else 900000};manifest={}
 for coin in COINS:
  pair=coin+'/USDC:USDC';base=ROOT/'hyperliquid/intraday-1000' if name=='native_m15' else ROOT/'strategy-lab/amd-volume/data';path=base/(coin+('-15m.json' if name=='native_m15' else '-M1.json'));raw=json.loads(path.read_text());frame=pd.DataFrame(raw)
  if name=='native_m15':frame=frame.rename(columns={'o':'open','h':'high','l':'low','c':'close','v':'volume'})
  frame['date']=pd.to_datetime(frame['t'],unit='ms',utc=True)
  for k in ['open','high','low','close','volume']:frame[k]=frame[k].astype(float)
  frame=frame[['date','open','high','low','close','volume']].sort_values('date').drop_duplicates('date')
  opens['prices'][pair]=[[int(r.date.timestamp()*1000),float(r.open)] for r in frame.itertuples()]
  if name=='august_m1':
   handler.ohlcv_store(pair,'1m',frame,CandleType.FUTURES);groups=frame.set_index('date').resample('15min');count=groups.close.count();main=groups.agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).loc[count==15].reset_index()
  else:main=frame
  handler.ohlcv_store(pair,'15m',main,CandleType.FUTURES);opens['main_times'][pair]=[int(t.timestamp()*1000) for t in main.date]
  hp=base/(coin+('-1h.json' if name=='native_m15' else '-H1.json'));h=pd.DataFrame(json.loads(hp.read_text())).rename(columns={'o':'open','h':'high','l':'low','c':'close','v':'volume'});h['date']=pd.to_datetime(h.t,unit='ms',utc=True)
  for k in ['open','high','low','close','volume']:h[k]=h[k].astype(float)
  handler.ohlcv_store(pair,'1h',h[['date','open','high','low','close','volume']],CandleType.FUTURES)
  fp=base/(coin+'-funding.json');fund=json.loads(fp.read_text());rates=pd.DataFrame({'date':pd.to_datetime([(x.get('time',x.get('t'))//3600000)*3600000 for x in fund],unit='ms',utc=True),'funding_rate':[float(x.get('fundingRate',x.get('funding_rate'))) for x in fund]}).drop_duplicates('date');handler.ohlcv_store(pair,'1h',rates,CandleType.FUNDING_RATE)
  manifest[coin]={'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'price_rows':len(frame),'main_rows':len(main),'main_gap_count':int((main.date.diff().dropna()!=pd.Timedelta(minutes=15)).sum()),'source_minute_missing':None if name=='native_m15' else int((frame.date.max()-frame.date.min()).total_seconds()/60+1-len(frame))}
 (out/'opens.json').write_text(json.dumps(opens));(out/'data-manifest.json').write_text(json.dumps(manifest,indent=2))
 cfg=json.loads((P/'dry-run.example.json').read_text());cfg.update(strategy='XenonFVGBacktest',bot_name='FVG HISTORICAL ONLY',initial_state='stopped',datadir=str(out/'data'),user_data_dir=str(P/'user_data'),dataformat_ohlcv='feather',db_url='sqlite://',xenon_backtest_opens=str(out/'opens.json'),xenon_backtest_audit=str(out/'audit.json'),dry_run_wallet=1000)
 cfg['api_server'].update(enabled=False,username='unused-backtest',password='unused-backtest',jwt_secret_key='unused-backtest-not-a-service-000000000000');cfg['exchange']['ccxt_config'].update(verify=True,cafile='/etc/ssl/certs/ca-certificates.crt');cfg['cancel_open_orders_on_exit']=False
 (out/'config.json').write_text(json.dumps(cfg,indent=2));print(name,manifest)
