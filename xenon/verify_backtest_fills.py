"""Native-engine prefix replay beyond actual Limit fill, retaining full portfolio."""
import pathlib,sys,json,zipfile,subprocess,datetime as dt
P=pathlib.Path(__file__).resolve().parent;ROOT=P/'.runtime/backtest';source=ROOT/'native_m15'
def result(out):
 archive=sorted(out.glob('*.zip'))[-1]
 with zipfile.ZipFile(archive) as z:return json.loads(z.read(next(n for n in z.namelist() if n.endswith('.json') and not n.endswith('_config.json'))))['strategy']['XenonFVGBacktest']
base=result(source);checks=[]
for i,t in enumerate(base['trades']):
 fill=next(o['order_filled_timestamp'] for o in t['orders'] if o['ft_is_entry']);delay=fill-t['open_timestamp']
 if delay<=900000:continue
 out=ROOT/'causal-fill-replay'/str(i);out.mkdir(parents=True,exist_ok=True);cfg=json.loads((source/'config.json').read_text());cfg.update(user_data_dir=str(out/'user_data'),xenon_backtest_audit=str(out/'audit.json'));(out/'user_data').mkdir(exist_ok=True);(out/'config.json').write_text(json.dumps(cfg));stop=fill+1800000
 args=[sys.executable,'-m','freqtrade','backtesting','--config',str(out/'config.json'),'--datadir',str(source/'data'),'--strategy-path',str(P/'strategies'),'--timerange',f'1790899200-{stop//1000}','--cache','none','--export','trades','--backtest-directory',str(out)]
 with (out/'run.log').open('w') as log:r=subprocess.run(args,cwd=P.parent,stdout=log,stderr=subprocess.STDOUT)
 assert r.returncode==0, str(out/'run.log');truncated=result(out);matches=[x for x in truncated['trades'] if x['enter_tag']==t['enter_tag']];assert len(matches)==1
 replay=matches[0];replayfill=next(o['order_filled_timestamp'] for o in replay['orders'] if o['ft_is_entry']);assert replayfill==fill and replay['open_rate']==t['open_rate'] and replay['amount']==t['amount']
 check={'pair':t['pair'],'tag':t['enter_tag'],'placement_ms':t['open_timestamp'],'fill_ms':fill,'delay_minutes':delay/60000,'truncated_end_ms':stop,'entry_fill_amount_and_price_unchanged':True};checks.append(check);print(json.dumps(check),flush=True)
report={'status':'PASS','checked_delayed_entries':len(checks),'checks':checks,'explanation':'Official lookahead slices at placement+one main candle; all five flags correspond to fills delayed beyond that horizon. Native portfolio replay ending after actual fill preserves the entry, fill time, amount and price. This diagnoses these five flags only, not a universal absence-of-bias certificate.'};(ROOT/'limit-fill-prefix-audit.json').write_text(json.dumps(report,indent=2))
