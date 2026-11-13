"""Reproducible official Freqtrade backtests; no live account configuration."""
import argparse,json,pathlib,subprocess,sys
P=pathlib.Path(__file__).resolve().parent;ROOT=P.parent
p=argparse.ArgumentParser();p.add_argument('--dataset',choices=['native_m15','august_m1'],required=True);p.add_argument('--stress',action='store_true');a=p.parse_args();source=P/'.runtime/backtest'/a.dataset;out=P/'.runtime/backtest'/(a.dataset+('_stress' if a.stress else ''));out.mkdir(exist_ok=True)
cfg=json.loads((source/'config.json').read_text());cfg['xenon_backtest_audit']=str(out/'audit.json');cfg['user_data_dir']=str(out/'user_data');(out/'user_data').mkdir(exist_ok=True);path=out/'run-config.json';path.write_text(json.dumps(cfg,indent=2))
args=[sys.executable,'-m','freqtrade','backtesting','--config',str(path),'--datadir',str(source/'data'),'--strategy-path',str(P/'strategies'),'--timerange','20261002-20261112' if a.dataset=='native_m15' else '20260812-20260901','--cache','none','--export','trades','--backtest-directory',str(out)]
if a.dataset=='august_m1':args+=['--timeframe-detail','1m']
if a.stress:args+=['--fee','0.0009']
(out/'command.json').write_text(json.dumps(args,indent=2))
with (out/'run.log').open('w') as log:result=subprocess.run(args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
if result.returncode or not list(out.glob('*.zip')):raise SystemExit('Backtest failed; inspect '+str(out/'run.log'))
print(str(out))
