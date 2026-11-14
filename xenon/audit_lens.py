"""Official lookahead analysis, isolated from any runtime account."""
import json
import pathlib
import subprocess
import sys
import time

P=pathlib.Path(__file__).resolve().parent
source=P/'.runtime/backtest/native_m15'
out=P/'.runtime/lens-backtest/lookahead';out.mkdir(parents=True,exist_ok=True)
config=json.loads((source/'config.json').read_text())
config.update(strategy='XenonLens',xenon_lens_lookahead_audit=True,xenon_lens_risk_USDC=5,xenon_lens_audit=str(out/'audit.json'),user_data_dir=str(out/'user_data'),xenon_runtime_dir=str(out))
(out/'user_data').mkdir(exist_ok=True)
config['entry_pricing']['price_side']='other'
config['order_types']={'entry':'market','exit':'market','stoploss':'market','stoploss_on_exchange':False}
config.pop('xenon_backtest_audit',None)
(out/'config.json').write_text(json.dumps(config,indent=2))
csv_path=out/f'lookahead-{time.time_ns()}.csv'
args=[sys.executable,'-m','freqtrade','lookahead-analysis','--config',str(out/'config.json'),'--datadir',str(source/'data'),'--strategy-path',str(P/'strategies'),'--timerange','20261002-20261112','--minimum-trade-amount','5','--targeted-trade-amount','10','--lookahead-analysis-exportfilename',str(csv_path)]
(out/'command.json').write_text(json.dumps(args,indent=2))
with (out/'run.log').open('w') as log:r=subprocess.run(args,cwd=P.parent,stdout=log,stderr=subprocess.STDOUT)
if r.returncode:raise SystemExit('Lookahead failed; inspect '+str(out/'run.log'))
(out/'lookahead.csv').write_bytes(csv_path.read_bytes())
print(out)
