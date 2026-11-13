"""Reproducible official Freqtrade backtests; no live account configuration."""
import argparse,json,pathlib,subprocess,sys,math
P=pathlib.Path(__file__).resolve().parent;ROOT=P.parent
p=argparse.ArgumentParser();p.add_argument('--dataset',choices=['native_m15','august_m1'],required=True);p.add_argument('--stress',action='store_true');p.add_argument('--coarse',action='store_true',help='M15 execution on the same August M15 signal data');p.add_argument('--fixed-risk',type=float,help='Historical fixed USDC risk, retaining margin/exposure and loss guards');a=p.parse_args()
if a.fixed_risk is not None and (not math.isfinite(a.fixed_risk) or a.fixed_risk<=0):p.error('fixed risk must be positive and finite')
if a.coarse and a.dataset!='august_m1':p.error('--coarse is for the August paired comparison')
source=P/'.runtime/backtest'/a.dataset;out=P/'.runtime/backtest'/(a.dataset+('_m15only' if a.coarse else '')+('_risk'+format(a.fixed_risk,'g') if a.fixed_risk is not None else '')+('_stress' if a.stress else ''));out.mkdir(exist_ok=True)
cfg=json.loads((source/'config.json').read_text());cfg['xenon_backtest_audit']=str(out/'audit.json');cfg['user_data_dir']=str(out/'user_data');(out/'user_data').mkdir(exist_ok=True)
if a.fixed_risk is not None:cfg['xenon_fixed_risk_USDC']=a.fixed_risk
path=out/'run-config.json';path.write_text(json.dumps(cfg,indent=2))
args=[sys.executable,'-m','freqtrade','backtesting','--config',str(path),'--datadir',str(source/'data'),'--strategy-path',str(P/'strategies'),'--timerange','20261002-20261112' if a.dataset=='native_m15' else '20260812-20260901','--cache','none','--export','trades','--backtest-directory',str(out)]
if a.dataset=='august_m1' and not a.coarse:args+=['--timeframe-detail','1m']
if a.stress:args+=['--fee','0.0009']
(out/'command.json').write_text(json.dumps(args,indent=2))
with (out/'run.log').open('w') as log:result=subprocess.run(args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
if result.returncode or not list(out.glob('*.zip')):raise SystemExit('Backtest failed; inspect '+str(out/'run.log'))
print(str(out))
