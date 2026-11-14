"""Native-engine same-portfolio prefix regression for the precision defect."""
import concurrent.futures
import json
import pathlib
import subprocess
import sys
import zipfile

P=pathlib.Path(__file__).resolve().parent
ROOT=P/'.runtime/lens-backtest'


def run(case):
    name,end=case
    out=ROOT/'precision-prefix'/name;out.mkdir(parents=True,exist_ok=True)
    cfg=json.loads((ROOT/'lookahead/config.json').read_text())
    # Match the official audit's huge wallet and fixed stake; this is NOT an
    # execution/account proposal. The strategy still retains its 2-position cap.
    cfg.update(dry_run_wallet=1000000000,stake_amount=10000,max_open_trades=-1,user_data_dir=str(out/'user_data'),xenon_lens_audit=str(out/'audit.json'))
    (out/'user_data').mkdir(exist_ok=True);(out/'config.json').write_text(json.dumps(cfg,indent=2))
    args=[sys.executable,'-m','freqtrade','backtesting','--config',str(out/'config.json'),'--datadir',str(P/'.runtime/backtest/native_m15/data'),'--strategy-path',str(P/'strategies'),'--timerange','20261002-'+end,'--cache','none','--export','trades','--backtest-directory',str(out)]
    (out/'command.json').write_text(json.dumps(args,indent=2))
    with (out/'run.log').open('w') as log:r=subprocess.run(args,cwd=P.parent,stdout=log,stderr=subprocess.STDOUT)
    assert r.returncode==0,str(out/'run.log')
    archive=sorted(out.glob('*.zip'))[-1]
    with zipfile.ZipFile(archive) as z:
        key=next(n for n in z.namelist() if n.endswith('.json') and not n.endswith('_config.json'))
        return json.loads(z.read(key))['strategy']['XenonLens']['trades']


with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    full,cut=pool.map(run,[('full','20261112'),('prefix','20261005')])
checks=[]
keys=['open_timestamp','close_timestamp','open_rate','close_rate','amount','exit_reason','stop_loss_abs','price_precision','precision_mode_price']
for t in cut:
    if 'force_exit' in t['exit_reason']:continue
    other=[x for x in full if x['enter_tag']==t['enter_tag']]
    assert len(other)==1,t['enter_tag']
    assert all(t.get(k)==other[0].get(k) for k in keys),(t['enter_tag'],{k:[t.get(k),other[0].get(k)] for k in keys if t.get(k)!=other[0].get(k)})
    checks.append({'tag':t['enter_tag'],'pair':t['pair'],**{k:t.get(k) for k in keys},'status':'PASS'})
regression=[x for x in checks if '|SOL|1|1791024300000|' in x['tag']]
assert len(regression)==1 and regression[0]['exit_reason']=='stop_loss'
report={'status':'PASS','scope':'All normally closed trades in the same native portfolio through Oct 5 match the longer run exactly. Billion-USDC wallet matches audit only, not the requested account.','checked_closed_trades':len(checks),'regression_trade':regression[0],'checks':checks}
(ROOT/'precision-prefix-regression.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
