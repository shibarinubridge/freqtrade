"""Frozen FVG detector port. Geometry matches the audited research detector.
Numerical thresholds are research assumptions, not additional video claims.
"""
import datetime as dt,math,statistics,collections,copy
from zoneinfo import ZoneInfo
STEP=900000
NY=ZoneInfo('America/New_York')
META={c:{'szDecimals':n} for c,n in {'BTC':5,'ETH':4,'SOL':2,'HYPE':2}.items()}

def tick(coin,price):return 10.**max(-(6-META[coin]['szDecimals']),math.floor(math.log10(price))-4)

def rounding(coin,price,up):
 q=tick(coin,price);return (math.ceil(price/q-1e-8) if up else math.floor(price/q+1e-8))*q

def detect(coin,rows=None,trace=False):
 rows=[] if rows is None else rows;timeline=[];swept={};atr=None
 def decorate(obj):
  if obj is None:return None
  v=copy.deepcopy(obj);v['setup_id']=f"{coin}:{v.get('sweep_time')}:{v.get('direction')}";v['sweep_open_ms']=v.get('sweep_time',0)-STEP;v['liquidity_levels']=swept.get(v['setup_id'],[])
  for key in ['old_gap','new_gap']:
   g=v.get(key)
   if g and 0<=g['bar']<len(rows):g.update(from_ms=rows[max(0,g['bar']-2)]['t'],formed_ms=rows[g['bar']]['t'],known_ms=rows[g['bar']]['end']);g.pop('bar',None)
  v.pop('sweep_bar',None);return v
 def emit(kind,bar,obj=None,extra=None):
  if not trace:return
  v=decorate(obj);identity=v['setup_id'] if v else coin;timeline.append({'id':f"{identity}:{bar['end']}:{kind}",'kind':kind,'candle_ms':bar['t'],'available_ms':bar['end'],'setup':v,**(extra or {})})
 highs=[];lows=[];gaps=[];candidate=None;events=collections.defaultdict(list);trs=[];counts=collections.Counter();day=None;prevday=None;dh=dl=None
 for i,b in enumerate(rows):
  t,o,h,l,c=b['t'],b['o'],b['h'],b['l'],b['c'];end=b['end'];local=dt.datetime.fromtimestamp(t/1000,NY).date()
  if local!=day:
   if day is not None:prevday=(dh,dl)
   day=local;dh=h;dl=l
  dh=max(dh,h);dl=min(dl,l);pc=rows[i-1]['c'] if i else c
  trs.append(max(h-l,abs(h-pc),abs(l-pc)));atr=statistics.mean(trs[-14:]);contig=i>=2 and t-rows[i-2]['t']==2*STEP
  if i<30 or atr<=0:continue
  k=i-3
  if k>=3 and rows[i]['t']-rows[k-3]['t']==6*STEP:
   win=rows[k-3:k+4]
   if rows[k]['h']>max(r['h'] for j,r in enumerate(win) if j!=3):highs.append((k,rows[k]['h']))
   if rows[k]['l']<min(r['l'] for j,r in enumerate(win) if j!=3):lows.append((k,rows[k]['l']))
  highs=[x for x in highs if i-x[0]<=96];lows=[x for x in lows if i-x[0]<=96]
  gaps=[g for g in gaps if i-g['bar']<=480 and not (c<g['lo'] if g['direction']==1 else c>g['hi'])]
  ng=None
  if contig:
   if l>rows[i-2]['h']:ng={'bar':i,'lo':rows[i-2]['h'],'hi':l,'direction':1}
   elif h<rows[i-2]['l']:ng={'bar':i,'lo':h,'hi':rows[i-2]['l'],'direction':-1}
  if candidate:
   d=candidate['direction'];og=candidate['old_gap']
   if (c<og['lo'] or l<candidate['extreme']) if d==1 else (c>og['hi'] or h>candidate['extreme']):emit('candidate_invalidated',b,candidate);candidate=None;counts['candidate_invalidated']+=1
   elif i-candidate['sweep_bar']>6 or t-rows[i-1]['t']!=STEP:emit('candidate_expired',b,candidate);candidate=None;counts['candidate_expired']+=1
   else:
    if d*(pc-candidate['bos'])<=0 and d*(c-candidate['bos'])>0:
     fresh=not candidate['broken'];candidate['broken']=True
     if fresh:emit('bos_confirmed',b,candidate)
    if d*(c-o)>0 and h-l>=atr and abs(c-o)>=.6*(h-l):
     fresh=not candidate['displaced'];candidate['displaced']=True
     if fresh:emit('displacement',b,candidate)
    remembered=candidate.get('new_gap')
    if remembered and ((l<=remembered['lo']) if d==1 else (h>=remembered['hi'])):emit('gap_consumed',b,candidate);candidate.pop('new_gap',None)
    if ng and ng['direction']==d:candidate['new_gap']=dict(ng);emit('new_fvg',b,candidate)
    if candidate['broken'] and candidate['displaced'] and candidate.get('new_gap'):
     g=candidate['new_gap'];entry=rounding(coin,(g['lo']+g['hi'])/2,d==-1);stop=rounding(coin,candidate['extreme']-d*tick(coin,candidate['extreme']),d==-1);target=candidate['target'];risk=d*(entry-stop)
     if risk>0 and d*(target-entry)>0 and d*(c-entry)>0:
      order={**candidate,'entry_limit':entry,'stop':stop,'target':target,'signal_time':end,'expires':end+12*STEP,'old_gap':og,'new_gap':g,'coin':coin,'ATR':atr}
      events[end].append({'kind':'place','order':order});counts['orders']+=1;emit('setup_ready',b,order)
     else:emit('geometry_rejected',b,candidate);counts['invalid_geometry']+=1
     candidate=None
  if not candidate and contig:
   for d,sw,opp in [(1,lows,highs),(-1,highs,lows)]:
    levels=[q for j,q in sw if any(j!=k and abs(q-price)<=.1*atr for k,price in sw)]
    if prevday:levels.append(prevday[1] if d==1 else prevday[0])
    hit=[q for q in levels if (l<q<c and pc>=q if d==1 else h>q>c and pc<=q)]
    old=[g for g in gaps if g['direction']==d and g['bar']<i and (g['lo']<=l<=g['hi'] if d==1 else g['lo']<=h<=g['hi'])]
    if not(hit and old and opp):continue
    counts['sweep_old_FVG']+=1;bos=opp[-1][1];untouched=[q for j,q in opp if (max(r['h'] for r in rows[j+1:i+1])<=q if d==1 else min(r['l'] for r in rows[j+1:i+1])>=q)]
    if not untouched:counts['no_untouched_target']+=1;continue
    target=max(untouched) if d==1 else min(untouched)
    if not (target>bos>c if d==1 else target<bos<c):counts['no_internal_BOS_external_target']+=1;continue
    candidate={'direction':d,'old_gap':dict(old[-1]),'sweep_bar':i,'sweep_time':end,'extreme':l if d==1 else h,'bos':bos,'target':target,'displaced':False,'broken':False};counts['candidates']+=1
    if trace:swept[f'{coin}:{end}:{d}']=[float(q) for q in hit]
    emit('sweep_confirmed',b,candidate);break
  if ng:gaps.append(ng)
 if trace:
  levels=[{'price':q,'kind':kind,'origin_ms':rows[k]['t'],'known_ms':rows[k+3]['end']} for kind,items in [('swing_high',highs[-8:]),('swing_low',lows[-8:])] for k,q in items]
  if prevday:levels.extend([{'price':prevday[0],'kind':'prior_day_high','known_ms':rows[-1]['end']},{'price':prevday[1],'kind':'prior_day_low','known_ms':rows[-1]['end']}])
  plans=[e for e in timeline if e['kind']=='setup_ready']
  return dict(events),dict(counts),{'coin':coin,'timeframe':'15m','confirmed_ms':rows[-1]['end'] if rows else None,'candidate':decorate(candidate),'latest_plan':plans[-1]['setup'] if plans else None,'levels':levels,'events':timeline[-80:],'atr':atr}
 return dict(events),dict(counts)
