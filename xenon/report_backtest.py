"""Extract official results and verify exported trades against immutable setup tags."""
import json,pathlib,zipfile,sys,csv,datetime as dt,hashlib
from zoneinfo import ZoneInfo
P=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(P/'strategies'))
from XenonFVG import decode,risk_unit
from fvg_rules import tick
ROOT=P/'.runtime/backtest';rows=[];checks=[];archives=[]
for name in ['native_m15','native_m15_stress','august_m1','august_m1_stress']:
 out=ROOT/name;archive=sorted(out.glob('*.zip'))[-1];archives.append(archive)
 with zipfile.ZipFile(archive) as z:
  result=json.loads(z.read(next(n for n in z.namelist() if n.endswith('.json') and not n.endswith('_config.json'))))['strategy']['XenonFVGBacktest']
 source=ROOT/('august_m1' if name.startswith('august') else 'native_m15');data=json.loads((source/'opens.json').read_text());observed={p:set(x[0] for x in b) for p,b in data['prices'].items()}
 audit=json.loads((out/'audit.json').read_text());order_map={o['tag']:o for o in audit['orders']}
 for t in result['trades']:
  setup=decode(t['enter_tag']);coin=setup['coin'];tolerance=tick(coin,setup['entry_limit'])+1e-7
  entry=next(o['order_filled_timestamp'] for o in t['orders'] if o['ft_is_entry']);exit=t['close_timestamp']
  assert abs(t['open_rate']-setup['entry_limit'])<=tolerance
  assert abs(t['stop_loss_abs']-setup['stop'])<=tick(coin,setup['stop'])+1e-7
  assert setup['signal_time']<=entry<setup['expires']
  if t['exit_reason']=='roi':assert entry//60000<exit//60000 and setup['direction']*(t['close_rate']-setup['target'])>=-tolerance
  if t['exit_reason']=='fvg_time_exit':assert exit-entry>=86400000
  order=order_map[t['enter_tag']];assert order['planned_risk_USDC']<=order['equity_USDC']*.005+1e-7
  missing=None
  if name.startswith('august'):missing=sum(x not in observed[t['pair']] for x in range(entry,exit,60000));assert missing==0
  checks.append({'dataset':name,'pair':t['pair'],'tag':t['enter_tag'],'actual_fill_ms':entry,'placement_ms':t['open_timestamp'],'close_ms':exit,'entry_geometry':'PASS','final_stop_within_one_native_tick':'PASS','placement_risk_budget':'PASS','entry_minute_target_suppressed':'PASS','missing_M1_during_position':missing})
  # Native export open_date is placement time, not necessarily actual fill.
 row={k:result.get(k) for k in ['total_trades','profit_total_abs','winrate','max_drawdown_account','starting_balance','final_balance','backtest_start','backtest_end','profit_factor']};row.update(dataset=name,best_trade=max(t['profit_abs'] for t in result['trades']),profit_without_best_trade=result['profit_total_abs']-max(t['profit_abs'] for t in result['trades']),accepted_placements=len(audit['orders']),audit_counts=audit['counts'],archive=str(archive));rows.append(row)
lookahead=list(csv.DictReader((ROOT/'lookahead.csv').open()))
fill_replays=json.loads((ROOT/'limit-fill-prefix-audit.json').read_text())
assert fill_replays['status']=='PASS'
summary={'created_bucharest':dt.datetime.now(ZoneInfo('Europe/Bucharest')).isoformat(),'engine':'Freqtrade 2026.10 official backtesting','strategy':'XenonFVGBacktest','scope':'Historical exploratory evaluation; no deployment or out-of-sample qualification','runs':rows,'trade_rule_checks':len(checks),'trade_rule_audit_status':'PASS','official_lookahead':lookahead,'delayed_limit_prefix_replays':fill_replays,'limitations':['OHLCV-open proxy replaces order book; queue/partial fills and adverse slippage not reproduced.','M15-only run cannot resolve entry-minute chronology. M1 run is a different historical sample, not a resolution-only comparison.','Fees .045% each side; stress doubles fees only. Risk/target geometry remains frozen at baseline estimated costs.','Funding uses historical rates and futures H1 mark-price proxy.','Data are previously examined. Small sample, not independent profitability validation.','The official lookahead tool flags five delayed Limit entries; see the retained raw result and native prefix-replay diagnosis.']}
(ROOT/'summary.json').write_text(json.dumps(summary,indent=2));(ROOT/'trade-rule-audit.json').write_text(json.dumps(checks,indent=2))
md='# FVG în backtesterul Freqtrade\n\nStrategie: `XenonFVGBacktest`, derivată din regulile înghețate ale `XenonFVG`. Instrumente: BTC, ETH, SOL și HYPE, perpetual USDC pe Hyperliquid.\n\nCapital inițial virtual: 1.000 USDC; risc planificat: 0,5% din equity pe tranzacție (aproximativ 5 USDC inițial); maximum două poziții; levier maximum 2×. Botul și contul forward nu au fost modificate.\n\nComision de bază: 0,045% pe fiecare sens. Testele «stress» dublează numai comisionul efectiv la 0,09% pe sens; regulile inițiale de calcul al riscului și țintei rămân înghețate.\n\n| Date / execuție | Tranzacții | Net USDC | Win rate | Drawdown maxim | Sold final |\n|---|---:|---:|---:|---:|---:|\n'
for r in rows:md+=f"| {r['dataset']} | {r['total_trades']} | {r['profit_total_abs']:+.4f} | {100*r['winrate']:.1f}% | {100*r['max_drawdown_account']:.2f}% | {r['final_balance']:.4f} |\n"
md+='\nPerioade UTC: `native_m15`: 2 octombrie 2026, 00:00 – 12 noiembrie 2026, 00:00; `august_m1`: 12 august – 31 august 2026, până la 23:45. Primul test folosește M15; cel din august folosește semnale M15 cu detaliu M1. Perioadele diferă, deci diferența de PnL nu măsoară exclusiv efectul rezoluției.\n\n## Verificarea regulilor\n\nSemnalele, tagurile, direcția, intrarea CE, stopul și ținta coincid exact cu `XenonFVG` pe ambele seturi de date, inclusiv pe prefixuri de istoric. Auditul celor '+str(len(checks))+' tranzacții din cele patru rulări confirmă geometria intrărilor, stopul efectiv în limita unui tick nativ, bugetul de risc la plasare, expirarea și ieșirile. Nicio poziție din august nu traversează minute lipsă.\n\n`initial_stop_loss_abs` poate reflecta stopul generic anterior executării ordinului; stopul fix efectiv este verificat prin `stop_loss_abs`. `open_date` poate indica plasarea ordinului: auditul folosește timestampul executării efective.\n\n## Auditul de lookahead\n\nInstrumentul oficial raportează **5 intrări suspecte din 8**, zero ieșiri și zero indicatori semnalați. Nu este raportat ca PASS. Toate cele cinci alerte corespund ordinelor Limit executate la 30–150 de minute după plasare; auditul standard taie istoricul la plasare plus o singură lumânare M15.\n\nAm reluat separat întregul portofoliu până după fiecare executare întârziată: **'+str(fill_replays['checked_delayed_entries'])+'/'+str(fill_replays['checked_delayed_entries'])+'** păstrează identic tagul, momentul executării, cantitatea și prețul. Aceasta explică aceste cinci alerte; nu este o garanție universală privind orice posibil bias. Rezultatul brut este în `lookahead.csv`, iar reluările în `limit-fill-prefix-audit.json`.\n\n## Limitele simulării\n\n- Intrarea folosește deschiderea istorică drept aproximare pentru cotație. Nu avem registrul de ordine, poziția în coadă sau execuțiile parțiale. Slippage-ul advers efectiv nu este simulat.\n- M15 nu poate reconstitui ordinea evenimentelor din interiorul unei lumânări. M1 oferă detaliu suplimentar, fără a reproduce piața tick cu tick.\n- Funding-ul folosește ratele istorice, cu prețurile futures H1 drept aproximare pentru mark price.\n- În testul M1 cu comisioane duble, protecțiile de risc reduc numărul de tranzacții. Pierderea mai mică nu înseamnă că taxele mai mari îmbunătățesc strategia.\n- Ambele perioade au fost examinate anterior; nu reprezintă un holdout nou. Eșantionul este mic.\n\nRezultatul pozitiv M15 depinde puternic de cea mai bună tranzacție. Fără ea, netul acelui test devine '+f"{rows[0]['profit_without_best_trade']:+.4f} USDC"+'. Testul M1 de bază este negativ. Profitabilitatea strategiei nu este validată.\n'
(ROOT/'report.md').write_text(md)
with zipfile.ZipFile(ROOT/'xenon-fvg-backtest-review.zip','w',zipfile.ZIP_DEFLATED) as z:
 for f in [ROOT/'report.md',ROOT/'summary.json',ROOT/'parity.json',ROOT/'trade-rule-audit.json',*archives]:z.write(f,('native/'+f.parent.name+'/'+f.name) if f.suffix=='.zip' else f.name)
 for extra in ['lookahead.csv','limit-fill-prefix-audit.json']:
  if (ROOT/extra).exists():z.write(ROOT/extra,extra)
 for folder in ['native_m15','august_m1']:
  z.write(ROOT/folder/'data-manifest.json',folder+'/data-manifest.json')
 for f in ['strategies/XenonFVG.py','strategies/XenonFVGBacktest.py','strategies/fvg_rules.py','run_backtest.py','prepare_backtest.py','verify_backtest_parity.py','verify_backtest_fills.py','report_backtest.py','tests/test_backtest.py','FVG-BACKTEST.md']:z.write(P/f,'source/'+f)
print(json.dumps({'status':'PASS','trade_checks':len(checks),'runs':rows},indent=2))
