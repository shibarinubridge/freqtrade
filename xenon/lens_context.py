"""Read-only Lens observation, closed-bar packet journal and dashboard payload."""
import hashlib
import json
import pathlib
import sys
import time

import pandas as pd

P = pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(P/'strategies'))
from lens_rules import calculate, packet, STEP, VERSION, number

CACHE = {}


def atomic(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,allow_nan=False))
    tmp.replace(path)


def save_packet(root, coin, value):
    """Only observed closes are journaled. Restart/same-close is idempotent."""
    root=pathlib.Path(root)
    path=root/'latest'/f'{coin}_15.json'
    try:old=json.loads(path.read_text())
    except (OSError,ValueError):old=None
    stamp=value['xenon']['closed_ms']
    if old and old['xenon']['closed_ms']>stamp:return False
    if old and old['xenon']['closed_ms']==stamp:
        if old['xenon'].get('version')==value['xenon'].get('version'):return False
        # A code upgrade can reanalyse the latest already-closed bar. Keep
        # both versions in history and label this as reanalysis, not a new bar.
        value=json.loads(json.dumps(value))
        value['xenon']['reanalysis_of_version']=old['xenon'].get('version')
    atomic(path,value)
    # Separate stream per symbol/version: stable ordering and bounded tail, no 24/7
    # daemon or missed historical bars falsely represented as live packets.
    stream=root/'history'/f'{coin}_15.jsonl';stream.parent.mkdir(parents=True,exist_ok=True)
    lines=stream.read_text().splitlines()[-1999:] if stream.exists() else []
    lines.append(json.dumps(value,allow_nan=False))
    tmp=stream.with_suffix('.tmp');tmp.write_text('\n'.join(lines)+'\n');tmp.replace(stream)
    return True


def collect(coin, rows, now, root=None):
    closed=[r for r in rows if r['t']+STEP<=now]
    if not closed:return {'status':'unavailable','reason':'Lipsesc lumânări M15 închise.'}
    # Fingerprint all actual input values, not only the last timestamp: a feed
    # correction must not leave silently stale calculations in memory.
    closed=closed[-1600:]
    key=hashlib.sha256(json.dumps(closed,sort_keys=True).encode()).hexdigest()
    cached=CACHE.get(coin)
    if cached and cached[0]==key:
        return runtime_context(coin,cached[1])
    f=pd.DataFrame([{'date':pd.to_datetime(r['t'],unit='ms',utc=True),**{name:float(r[k]) if r.get(k) is not None else float('nan') for name,k in [('open','o'),('high','h'),('low','l'),('close','c'),('volume','v')]}} for r in closed])
    analyzed=calculate(f)
    value=packet(analyzed,symbol='HYPERLIQUID:'+coin)
    value['xenon'].update(observed_ms=int(time.time()*1000),observation_source='dashboard_public_collector',input_sha256=key)
    chart=chart_rows(analyzed)
    destination=pathlib.Path(root) if root else P/'.runtime/lens/observation'
    save_packet(destination,coin,value)
    out={'status':'ready' if value['xenon']['ready'] else 'warming_up','packet':value,'chart':chart,'source':'OBSERVATION_ONLY','version':VERSION}
    CACHE[coin]=(key,out)
    return runtime_context(coin,out)


def chart_rows(analyzed):
    chart=[]
    for b in analyzed.iloc[-600:].itertuples():
        chart.append({'t':int(b.date.timestamp()*1000),'ema20':number(b.ema20),'ema50':number(b.ema50),'ema200':number(b.ema200),'vwap':number(b.vwap),'signal':int(b.signal),'ready':bool(b.ready),'swing_high':number(b.swing_high),'swing_low':number(b.swing_low),'swing_high_known_ms':number(b.swing_high_known_ms),'swing_low_known_ms':number(b.swing_low_known_ms),'structure_event':b.structure_event})
    return chart


def runtime_context(coin, cached):
    out=dict(cached)
    try:out['validation']=json.loads((P/'lens-validation.json').read_text())
    except (OSError,ValueError):out['validation']={'status':'UNVERIFIED'}
    native=P/'.runtime/accounts/lens/lens-packets/latest'/f'{coin}_15.json'
    try:
        runtime=json.loads(native.read_text())
        out['runtime_packet']=runtime
        if cached['packet']['xenon']['closed_ms']<=runtime['xenon']['closed_ms']<=int(time.time()*1000):
            out['runtime_chart']=json.loads((native.parent.parent/'chart'/f'{coin}.json').read_text())
            # Do not double the 600-bar trace in the bounded Site snapshot.
            out['chart']=[]
    except (OSError,ValueError):pass
    decisions=P/'.runtime/accounts/lens/lens-decisions'/f'{coin}.json'
    try:out['decisions']=json.loads(decisions.read_text())[-30:]
    except (OSError,ValueError):out['decisions']=[]
    return out
