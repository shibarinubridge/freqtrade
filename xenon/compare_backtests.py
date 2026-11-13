"""Same-period execution audit and fixed-risk feasibility, without optimization."""
import hashlib
import html
import json
import pathlib
import sys
import zipfile
from datetime import datetime, timezone

import pandas as pd

P = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(P / 'strategies'))
from XenonFVG import decode
from fvg_rules import tick

ROOT = P / '.runtime/backtest'
OUT = ROOT / 'same-period-review'
OUT.mkdir(exist_ok=True)


def read_run(name):
    folder = ROOT / name
    archive = sorted(folder.glob('*.zip'))[-1]
    with zipfile.ZipFile(archive) as z:
        key = next(n for n in z.namelist() if n.endswith('.json') and not n.endswith('_config.json'))
        result = json.loads(z.read(key))['strategy']['XenonFVGBacktest']
    return result, json.loads((folder / 'audit.json').read_text()), archive


def stamp(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime('%m-%d %H:%M UTC')


def chart(name, i, trade):
    """Export actual OHLCV and native trade events as a standalone SVG."""
    setup = decode(trade['enter_tag'])
    coin = setup['coin']
    fill = next(o['order_filled_timestamp'] for o in trade['orders'] if o['ft_is_entry'])
    close = trade['close_timestamp']
    df = pd.read_feather(ROOT / 'august_m1/data/futures' / f'{coin}_USDC_USDC-15m-futures.feather')
    # Feather/Pandas may preserve microsecond rather than nanosecond units.
    df['ms'] = df.date.map(lambda value: int(value.timestamp() * 1000))
    bars = df.loc[(df.ms >= setup['signal_time'] - 32 * 900000) & (df.ms <= close + 8 * 900000)]
    assert not bars.empty, (name, trade['enter_tag'], str(df.date.dtype))
    lo = min(bars.low.min(), setup['stop'], setup['target'])
    hi = max(bars.high.max(), setup['stop'], setup['target'])
    pad = (hi - lo) * .1
    lo -= pad
    hi += pad
    start, end = bars.ms.min(), bars.ms.max() + 900000
    x = lambda t: 65 + (t - start) / (end - start) * 1000
    y = lambda p: 70 + (hi - p) / (hi - lo) * 430
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="590" viewBox="0 0 1200 590">',
           '<rect width="1200" height="590" fill="#101820"/>',
           '<g font-family="sans-serif" font-size="13" fill="#d8e1e8">',
           f'<text x="25" y="28">{html.escape(name)} · {coin} · {"SHORT" if trade["is_short"] else "LONG"} · net {trade["profit_abs"]:+.4f} USDC</text>',
           '<text x="25" y="50">Lumânări M15 reale; reperele sunt timestampurile native. Nu reprezintă mișcarea tick cu tick.</text>']
    for n in range(6):
        price = lo + n / 5 * (hi - lo)
        svg.append(f'<path d="M65 {y(price):.2f} H1065" stroke="#293540"/><text x="1075" y="{y(price):.2f}">{price:.5g}</text>')
    for b in bars.itertuples():
        color = '#52b99b' if b.close >= b.open else '#db7777'
        xx = x(b.ms + 450000)
        width = max(1, 1000 / len(bars) * .6)
        svg.append(f'<path d="M{xx:.2f} {y(b.high):.2f} V{y(b.low):.2f}" stroke="{color}"/><rect x="{xx-width/2:.2f}" y="{min(y(b.open), y(b.close)):.2f}" width="{width:.2f}" height="{max(1, abs(y(b.open)-y(b.close))):.2f}" fill="{color}"/>')
    for label, level, color in [('CE / Limit', setup['entry_limit'], '#d8b46a'), ('Stop', setup['stop'], '#db7777'), ('Target', setup['target'], '#52b99b')]:
        svg.append(f'<path d="M{x(setup["signal_time"]):.2f} {y(level):.2f} H1065" stroke="{color}" stroke-dasharray="6 4"/><text x="70" y="{y(level)-5:.2f}" fill="{color}">{label}: {level:g}</text>')
    for j, (label, time, price) in enumerate([('Semnal/plasare', trade['open_timestamp'], setup['entry_limit']), ('Fill', fill, trade['open_rate']), ('Ieșire: '+trade['exit_reason'], close, trade['close_rate'])]):
        svg.append(f'<path d="M{x(time):.2f} 70 V500" stroke="#7ca9d8" stroke-dasharray="2 5"/><circle cx="{x(time):.2f}" cy="{y(price):.2f}" r="5" fill="#a8cdf1"/><text x="65" y="{530+j*20}">{html.escape(label)}: {stamp(time)} · {price:g}</text>')
    svg.append('</g></svg>')
    file = f'{name}-{i+1}-{coin}.svg'
    (OUT / file).write_text('\n'.join(svg))
    return file


names = ['august_m1_m15only', 'august_m1', 'august_m1_m15only_risk200', 'august_m1_risk200', 'native_m15_risk200']
runs = {}
archives = []
links = []
for name in names:
    r, audit, archive = read_run(name)
    archives.append(archive)
    checks = []
    for i, t in enumerate(r['trades']):
        o = decode(t['enter_tag'])
        fill = next(order['order_filled_timestamp'] for order in t['orders'] if order['ft_is_entry'])
        assert abs(t['open_rate']-o['entry_limit']) <= tick(o['coin'], o['entry_limit']) + 1e-7
        assert abs(t['stop_loss_abs']-o['stop']) <= tick(o['coin'], o['stop']) + 1e-7
        assert o['signal_time'] <= fill < o['expires']
        if t['exit_reason'] == 'roi':
            assert fill // 60000 < t['close_timestamp'] // 60000
            assert o['direction']*(t['close_rate']-o['target']) >= -tick(o['coin'], o['target']) - 1e-7
        if t['exit_reason'] == 'fvg_time_exit':
            assert t['close_timestamp']-fill >= 86400000
        checks.append({'tag':t['enter_tag'], 'fill_ms':fill, 'entry':t['open_rate'], 'close_ms':t['close_timestamp'], 'exit':t['close_rate'], 'reason':t['exit_reason'], 'quantity':t['amount'], 'net_USDC':t['profit_abs']})
        if name in names[:2]:
            links.append(chart(name, i, t))
    runs[name] = {k:r[k] for k in ['total_trades', 'profit_total_abs', 'winrate', 'max_drawdown_account', 'final_balance', 'backtest_start', 'backtest_end']}
    runs[name].update(audit_counts=audit['counts'], sizing=audit.get('sizing', []), trades=checks)
    # Conditional sensitivity on the executed trades; not an engine rerun.
    runs[name]['exit_slippage_sensitivity_USDC'] = {str(bp):r['profit_total_abs']-sum(t['amount']*t['close_rate']*bp/10000 for t in r['trades']) for bp in [0, 1, 5, 10]}

a, b = [runs[n] for n in names[:2]]
assert a['backtest_start'] == b['backtest_start'] and a['backtest_end'] == b['backtest_end']
assert {t['tag'] for t in a['trades']} == {t['tag'] for t in b['trades']}
differences = []
for t in a['trades']:
    other = next(x for x in b['trades'] if x['tag'] == t['tag'])
    differences.append({'tag':t['tag'], 'M15':t, 'M1':other})
summary = {'scope':'Exploratory execution and sizing verification; not new strategy variants or holdout validation', 'same_period_same_trade_tags':True, 'runs':runs, 'trade_comparisons':differences, 'frozen_source_sha256':{f:hashlib.sha256((P/f).read_bytes()).hexdigest() for f in ['strategies/fvg_rules.py', 'strategies/XenonFVG.py', 'strategies/XenonFVGBacktest.py']}, 'blocked':['No new untouched validation sample used.', 'Fixed 200 USDC risk cannot fit these setups in a 1000 USDC account at the retained 2x exposure/margin limits.'], 'slippage_interpretation':'Extra adverse exit cost on fixed executed trades; ignores changed sizing, risk guards, queue and fills. It is not a full slippage engine simulation.'}
(OUT/'comparison.json').write_text(json.dumps(summary, indent=2))
md = '# Verificare M15/M1 și risc fix 200 USDC\n\nCapital virtual: 1.000 USDC. Semnalele rămân M15, cu exact aceleași date și perioadă pentru comparația din august. Nu s-a schimbat botul activ.\n\n| Rulare | Tranzacții | Net USDC | Sold final |\n|---|---:|---:|---:|\n'
for name, r in runs.items():
    md += f'| {name} | {r["total_trades"]} | {r["profit_total_abs"]:+.4f} | {r["final_balance"]:.4f} |\n'
md += '\nM15 și M1 au aceleași șapte taguri de intrare. Diferențele pe fiecare tranzacție sunt păstrate în comparison.json. Acest rezultat negativ este păstrat; regulile nu au fost optimizate pe el.\n\n## Risc fix\n\nRiscul de 200 USDC este pierderea planificată la stop, inclusiv costurile estimate, nu valoarea poziției sau marja. Cantitatea este rotunjită în jos la precizia instrumentului. Bugetul agregat al scenariului istoric este două ori 200 USDC, pentru maximum două poziții; limitele de expunere și levier rămân 2×. Protecțiile originale zilnice și de drawdown rămân active și ar putea opri sistemul după o singură pierdere mare.\n\n'
for name in names[2:]:
    sizing = runs[name]['sizing']
    if sizing:
        vals = [s['minimum_gross_leverage'] for s in sizing]
        md += f'- {name}: {len(sizing)} încercări de dimensionare, inclusiv reîncercări ale aceluiași setup; expunere cerută între {min(vals):.2f}× și {max(vals):.2f}× capitalul. Vezi marja cerută și disponibilă pentru fiecare ordin în comparison.json.\n'
md += '\nNu am mărit levierul sau deplasat stopurile pentru a forța ordinele. Zero tranzacții în aceste scenarii înseamnă imposibilitate de dimensionare în limitele păstrate, nu rezultat de profitabilitate.\n\n## Sensibilitate la slippage\n\nCost suplimentar advers numai la ieșire, aplicat acelorași tranzacții executate; fără redimensionare sau reevaluarea protecțiilor. Este un calcul de sensibilitate, nu un nou backtest Freqtrade. Intrările Limit nu sunt mutate dincolo de prețul lor.\n\n| Rulare | 0 bp | 1 bp | 5 bp | 10 bp |\n|---|---:|---:|---:|---:|\n'
for name in names[:2]:
    vals = runs[name]['exit_slippage_sensitivity_USDC']
    md += '| '+name+' | '+' | '.join(f'{vals[str(bp)]:+.4f}' for bp in [0,1,5,10])+' |\n'
md += '\n## Verificare vizuală\n\n[Deschide graficele celor 14 execuții comparate](charts.html). Fiecare grafic arată lumânările reale, CE, stopul, ținta, plasarea, fill-ul și ieșirea. Graficele nu reconstruiesc ordinea tickurilor intrabar.\n\nAuditul oficial anterior de lookahead păstrează cele cinci alerte de fill întârziat și diagnosticul prin reluări native; nu este convertit în PASS prin această comparație. Datele au fost examinate anterior, deci nu avem o validare nouă, independentă.\n'
(OUT/'report.md').write_text(md)
(OUT/'charts.html').write_text('<!doctype html><meta charset="utf-8"><title>Audit execuții FVG</title><style>body{background:#101820;color:#d8e1e8;font:16px sans-serif;margin:24px}img{width:100%;max-width:1200px;display:block;margin:24px 0}</style><h1>Execuții FVG: M15 versus M1</h1><p>12–31 august 2026 UTC. Capital 1.000 USDC; risc de bază 0,5%. Rezultate istorice exploratorii.</p>'+''.join(f'<img src="{f}" alt="{f}">' for f in links))
with zipfile.ZipFile(OUT/'same-period-review.zip', 'w', zipfile.ZIP_DEFLATED) as z:
    for f in OUT.iterdir():
        if f.suffix in ['.json', '.md', '.html', '.svg']:
            z.write(f, f.name)
    for archive in archives:
        z.write(archive, 'native/'+archive.parent.name+'/'+archive.name)
    for f in ['compare_backtests.py', 'run_backtest.py', 'strategies/XenonFVGBacktest.py']:
        z.write(P/f, 'source/'+f)
print(md)
