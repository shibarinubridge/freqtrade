"""Audit actual native Lens exports and retain negative/blocked outcomes."""
import collections
import csv
import datetime as dt
import hashlib
import json
import pathlib
import sys
import zipfile

import pandas as pd

P=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(P/'strategies'))
from XenonLens import decode,unit_risk
from fvg_rules import tick
from lens_rules import VERSION

ROOT=P/'.runtime/lens-backtest'
NAMES=['august_m1_risk200','native_m15_risk200','august_m1_risk5','august_m1_m15only_risk5','august_m1_risk5_stress','native_m15_risk5']
rows=[];checks=[];archives=[]
for name in NAMES:
    folder=ROOT/name;archive=sorted(folder.glob('*.zip'))[-1];archives.append(archive)
    with zipfile.ZipFile(archive) as z:
        key=next(n for n in z.namelist() if n.endswith('.json') and not n.endswith('_config.json'))
        result=json.loads(z.read(key))['strategy']['XenonLens']
    config=json.loads((folder/'config.json').read_text());audit=json.loads((folder/'audit.json').read_text())
    orders={x['tag']:x for x in audit['decisions'] if x['reason']=='placement_authorized'}
    for t in result['trades']:
        o=decode(t['enter_tag']);fill=next(x['order_filled_timestamp'] for x in t['orders'] if x['ft_is_entry'])
        assert o['signal_time']<=fill and fill-o['signal_time']<=120000
        assert abs(t['stop_loss_abs']-o['stop'])<=tick(o['coin'],o['stop'])+1e-7
        planned=orders[t['enter_tag']]['risk_USDC'];actual=t['amount']*unit_risk(o,t['open_rate'])
        assert planned<=config['xenon_lens_risk_USDC']+1e-7
        assert actual<=config['xenon_lens_risk_USDC']+1e-6
        if t['exit_reason']=='roi':
            assert fill//60000<t['close_timestamp']//60000
            assert o['direction']*(t['close_rate']-o['target'])>=-tick(o['coin'],o['target'])-1e-7
        missing=None
        if name.startswith('august') and 'm15only' not in name:
            f=pd.read_feather(P/'.runtime/backtest/august_m1/data/futures'/f'{o["coin"]}_USDC_USDC-1m-futures.feather')
            observed=set(int(x.timestamp()*1000) for x in f.date)
            missing=sum(x not in observed for x in range(fill,t['close_timestamp'],60000))
            assert missing==0
        checks.append({'dataset':name,'tag':t['enter_tag'],'fill_ms':fill,'exit_ms':t['close_timestamp'],'planned_risk_USDC':planned,'actual_entry_risk_at_base_costs_USDC':actual,'missing_M1_during_position':missing,'status':'PASS'})
    decisions=collections.Counter(x['reason'] for x in audit['decisions'])
    unique_margin={x['tag']:x for x in audit['decisions'] if x['reason']=='margin_or_2x_exposure'}
    leverage=[x['minimum_gross_leverage'] for x in unique_margin.values()]
    row={k:result.get(k) for k in ['total_trades','profit_total_abs','winrate','max_drawdown_account','final_balance','backtest_start','backtest_end']}
    row.update(dataset=name,risk_USDC=config['xenon_lens_risk_USDC'],decision_counts=dict(decisions),unique_margin_rejected_tags=len(unique_margin),required_exposure_multiple_range=[min(leverage),max(leverage)] if leverage else None,guard_suspended=audit['state'].get('suspended',False),observed_peak_equity_USDC=audit['state'].get('peak'))
    rows.append(row)
lookahead=list(csv.DictReader((ROOT/'lookahead/lookahead.csv').open()))
diagnosis_path=ROOT/'lookahead/portfolio-prefix-diagnosis.json'
diagnosis=json.loads(diagnosis_path.read_text()) if diagnosis_path.exists() else {'status':'PENDING'}
regression_path=ROOT/'precision-prefix-regression.json'
regression=json.loads(regression_path.read_text())
if lookahead[0]['has_bias']=='False':diagnosis={'status':'OFFICIAL_NO_FLAGS_AFTER_CAUSAL_PRECISION_FIX','native_prefix_regression':regression['status'],'checked_closed_trades':regression['checked_closed_trades']}
sources=['strategies/lens_rules.py','strategies/XenonLens.py','lens_context.py','run_lens_backtest.py','audit_lens.py','verify_lens_lookahead.py','verify_lens_precision.py','verify_lens_prefix.py']
summary={'created_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'strategy':'XenonLens','version':VERSION,'mode':'HISTORICAL_EXPLORATORY','runs':rows,'native_trade_rule_checks':checks,'official_lookahead':lookahead,'lookahead_diagnosis':diagnosis,'native_precision_prefix_regression':regression,'source_sha256':{f:hashlib.sha256((P/f).read_bytes()).hexdigest() for f in sources},'pine_numeric_parity':'UNVERIFIED_NO_PINE_ORACLE','fresh_holdout_evaluated':False,'optimization_performed':False,'live_trading_performed':False}
(ROOT/'summary.json').write_text(json.dumps(summary,indent=2))
md='# AI Agent Lens fără TradingView — implementare și verificare\n\nContul Lens are proces, API, bază de date și sold virtual separate. Botul FVG nu a fost modificat sau repornit. Lens este experimental, inițial PAUSED, cu risc cerut de 200 USDC și levier/expunere maximum 2×.\n\n## Motor oficial Freqtrade\n\nCapital virtual: 1.000 USDC. «risk5» este exclusiv comparație tehnică la 5 USDC risc fix; nu înlocuiește cererea de 200 USDC și nu modifică contul Lens.\n\n| Rulare | Trades | Net USDC | Win rate | DD maxim |\n|---|---:|---:|---:|---:|\n'
for r in rows:
    md+=f'| {r["dataset"]} | {r["total_trades"]} | {r["profit_total_abs"]:+.4f} | {100*r["winrate"]:.1f}% | {100*r["max_drawdown_account"]:.2f}% |\n'
md+='\nAugust: 12–31 august 2026, semnale M15 și execuție cu detaliu M1, cu excepția rularii «m15only». Native: 2 octombrie–12 noiembrie 2026, numai M15. Comisioane 0,045% pe sens; «stress» dublează numai comisionul efectiv. Funding istoric, mark/oracle aproximat prin prețuri futures H1.\n\nZero tranzacții la risc 200 înseamnă refuz de marjă/expunere, nu profitabilitate. Protecțiile de pierdere zilnică și drawdown sunt păstrate: în testele la risc 5 au suspendat intrările înainte de sfârșitul perioadei. Drawdown-ul raportat de motor și pragul intrabar de protecție nu sunt aceeași măsură. Nu au fost relaxate protecțiile pentru a produce mai multe tranzacții.\n\n## Reguli și verificări\n\n'
md+=f'- {len(checks)} execuții native auditate: timestamp după confirmare, geometrie înghețată, stop în limita unui tick, risc și ținte.\n'
md+='- 16 verificări pe prefixuri de date reale, două perioade și patru piețe: indicatorii și semnalele anterioare nu se schimbă la adăugarea viitorului.\n- Teste unitare de cauzalitate HTF, pivoti confirmați, RMA, scoruri, refuz de marjă, risc fix, restart și stop înainte de target.\n- Test separat cu SQL/Order/Trade reale din Freqtrade: persistența metadatelor, stopului și țintei la restart; fără ordine trimise unui exchange.\n\n## Lookahead\n\n'
md+='Rezultat oficial păstrat brut: '+json.dumps(lookahead,ensure_ascii=False)+'.\n\nDiagnosticul suplimentar: **'+diagnosis.get('status','PENDING')+'**. Regresia nativă verifică '+str(regression['checked_closed_trades'])+' tranzacții închise normal: aceleași intrări, cantități, stopuri și ieșiri într-un portofoliu trunchiat la 5 octombrie și în rularea până la 12 noiembrie.\n\nPrima implementare a avut o alertă de ieșire. Cauza demonstrată: `get_tick_size_over_time` deduce precizia din maximul lunar de zecimale, inclusiv lumânări viitoare. Pentru cazul SOL, tick-ul dedus era 0,001 în istoricul lung și 0,01 în cel scurt; stopurile 119,096 și 119,10 produceau ieșiri diferite. Versiunea 2 rotunjește conservator geometria nativă la tick-ul cunoscut al instrumentului și fixează precizia tranzacției istorice înainte de evaluarea stopului/ROI. Codul motorului Freqtrade nu a fost modificat. Auditul oficial a fost repetat și acum nu are alerte în cele 10 tranzacții verificate.\n\nRezultatele, sursele și alerta inițială sunt păstrate în `pre-causal-precision/`. Aceasta este o corecție de cauzalitate/execuție, nu o optimizare după profit. Nici auditul curat nu certifică universal absența oricărui bias sau profitabilitatea. Instrumentul oficial folosește un portofoliu virtual de un miliard USDC pentru audit; nu este contul cerut de utilizator și nu reprezintă rezultatele sale.\n\n## Diferențe față de Pine\n\n- Calcule Python din OHLCV Hyperliquid; nu s-a executat codul într-un cont TradingView. Paritatea numerică Pine, inclusiv inițializarea indicatorilor și egalitățile pivotilor, rămâne necertificată.\n- Sesiuni UTC, HTF anterior disponibil la deschiderea M15; nu folosim închiderea H4 curentă. Agregatele incomplete sunt excluse. VWAP din sesiune parțială este etichetat.\n- Codul Pine acordă 6 puncte unei lumânări direcționale chiar când volumul relativ lipsește; portul urmează codul, deși documentația spune zero.\n- Trackerul de referință deschide la close și înlocuiește instantaneu o direcție opusă. Freqtrade intră după confirmare, aplică marjă, costuri și protecții, iar înlocuirea necesită ieșirea efectivă. Trackerul nu dovedește o poziție nativă.\n- Harta brută ATR rămâne în pachetul de referință. Pentru execuție, stopul și T2 sunt rotunjite către intrare la tick-ul nativ, conservator. Gapurile care invalidează geometria sau reduc recompensa netă planificată sub 1R sunt refuzate. T1 este doar informativ, fără ieșire parțială.\n- Slippage-ul de 1 bp este o rezervă în dimensionarea riscului, nu o reconstrucție a spreadului, cozii sau execuției adverse. M15 nu reconstituie ordinea tickurilor.\n- Istoricul este deja examinat; nu există holdout nou și nu s-a făcut optimizare pe rezultatele acestuia. Rezultatele negative sunt păstrate. Nu există validare de profitabilitate.\n'
(ROOT/'report.md').write_text(md)
with zipfile.ZipFile(ROOT/'xenon-lens-review.zip','w',zipfile.ZIP_DEFLATED) as z:
    for f in [ROOT/'report.md',ROOT/'summary.json',ROOT/'prefix-parity.json',ROOT/'lookahead/lookahead.csv']:
        z.write(f,str(f.relative_to(ROOT)))
    if diagnosis_path.exists():z.write(diagnosis_path,str(diagnosis_path.relative_to(ROOT)))
    z.write(regression_path,regression_path.name)
    for extra in ['hosted-integration.json','deployment.json']:
        if (ROOT/extra).exists():z.write(ROOT/extra,extra)
    for f in ['precision-root-cause.json','summary.json','lookahead/lookahead.csv']:
        file=ROOT/'pre-causal-precision'/f
        if file.exists():z.write(file,'before-fix/'+f)
    for archive in archives:z.write(archive,'native/'+archive.parent.name+'/'+archive.name)
    for f in sources+['report_lens.py','LENS.md','lens-validation.json','tests/test_lens.py','tests/verify_lens_persistence.py','vendor/ai-agent-lens/ai-agent-lens.pine','vendor/ai-agent-lens/LICENSE','vendor/ai-agent-lens/provenance.json']:
        z.write(P/f,'source/'+f)
    for dataset in ['native_m15','august_m1']:
        z.write(P/'.runtime/backtest'/dataset/'data-manifest.json','data/'+dataset+'/data-manifest.json')
print(md)
