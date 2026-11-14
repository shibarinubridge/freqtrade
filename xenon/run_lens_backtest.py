"""Run the official engine on a frozen Lens hypothesis, never optimize holdout."""
import argparse
import json
import math
import pathlib
import subprocess
import sys

P=pathlib.Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--dataset',choices=['august_m1','native_m15'],required=True)
parser.add_argument('--risk',type=float,default=200,help='Fixed USDC planned loss at stop, not margin')
parser.add_argument('--coarse',action='store_true')
parser.add_argument('--stress',action='store_true')
parser.add_argument('--margin',type=float)
parser.add_argument('--leverage',type=float,default=2)
a=parser.parse_args()
if not math.isfinite(a.risk) or a.risk<=0:parser.error('Positive finite risk required')
if not math.isfinite(a.leverage) or not 1<=a.leverage<=5:parser.error('Leverage must be within 1–5x')
if a.margin is not None and (not math.isfinite(a.margin) or a.margin<=0):parser.error('Positive finite margin required')
source=P/'.runtime/backtest'/a.dataset
if not (source/'config.json').exists():parser.error('Prepare historical data first: xenon/prepare_backtest.py')
name=a.dataset+('_m15only' if a.coarse else '')+'_risk'+format(a.risk,'g')+('_stress' if a.stress else '')
if a.margin is not None:name+='_margin'+format(a.margin,'g')+'_lev'+format(a.leverage,'g')
out=P/'.runtime/lens-backtest'/name;out.mkdir(parents=True,exist_ok=True)
config=json.loads((source/'config.json').read_text())
config.update(strategy='XenonLens',bot_name='LENS HISTORICAL ONLY',xenon_lens_risk_USDC=a.risk,xenon_lens_audit=str(out/'audit.json'),xenon_runtime_dir=str(out),user_data_dir=str(out/'user_data'))
config['user_data_dir']=str(out/'user_data');(out/'user_data').mkdir(exist_ok=True)
config['xenon_lens_leverage']=a.leverage
if a.margin is not None:config.update(xenon_lens_margin_USDC=a.margin,max_open_trades=1)
config['entry_pricing']['price_side']='other'
config['order_types']={'entry':'market','exit':'market','stoploss':'market','stoploss_on_exchange':False}
for key in ['xenon_backtest_audit','xenon_fixed_risk_USDC']:
    config.pop(key,None)
(out/'config.json').write_text(json.dumps(config,indent=2))
args=[sys.executable,'-m','freqtrade','backtesting','--config',str(out/'config.json'),'--datadir',str(source/'data'),'--strategy-path',str(P/'strategies'),'--timerange','20260812-20260901' if a.dataset=='august_m1' else '20261002-20261112','--cache','none','--export','trades','--backtest-directory',str(out)]
if a.dataset=='august_m1' and not a.coarse:args+=['--timeframe-detail','1m']
if a.stress:args+=['--fee','0.0009']
(out/'command.json').write_text(json.dumps(args,indent=2))
with (out/'run.log').open('w') as log:
    result=subprocess.run(args,cwd=P.parent,stdout=log,stderr=subprocess.STDOUT)
if result.returncode:raise SystemExit('Lens backtest failed; inspect '+str(out/'run.log'))
print(out)
