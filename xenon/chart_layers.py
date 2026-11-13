"""Causal chart context; independent from executable strategy confirmation."""
import datetime as dt,json,pathlib,statistics,time
from zoneinfo import ZoneInfo
NY=ZoneInfo('America/New_York');STEP=900000;_cache={}
def annual_profile(coin,now):
 key=(coin,now//3600000)
 if key in _cache:return _cache[key]
 path=pathlib.Path(__file__).resolve().parent/'.runtime/chart-history'/(coin+'.json');method='D1/H1'
 try:raw=json.loads(path.read_text())['rows']
 except (OSError,ValueError):return {'status':'unavailable','reason':'Istoric anual de profil indisponibil'}
 year=dt.datetime.fromtimestamp(now/1000,dt.timezone.utc).year;start=int(dt.datetime(year,1,1,tzinfo=dt.timezone.utc).timestamp()*1000)
 rows=sorted({x['t']:x for x in raw if start<=x['t'] and x['t']+x['step']<=now}.values(),key=lambda x:x['t'])
 if not rows:return {'status':'unavailable','reason':'Fără date în anul curent'}
 lo=min(x['low'] for x in rows);hi=max(x['high'] for x in rows);width=(hi-lo)/96 or 1.;bins=[0.]*96
 for r in rows:
  a=max(0,min(95,int((r['low']-lo)/width)));b=max(a,min(95,int((r['high']-lo)/width)))
  for i in range(a,b+1):bins[i]+=float(r['volume'])/(b-a+1)
 last=rows[-1]['t']+rows[-1]['step'];expected=(last-start)//3600000;covered=sum(x['step']//3600000 for x in rows);missing=expected-covered;price=lo+(max(range(96),key=lambda i:bins[i])+.5)*width
 out={'status':'proxy','price':price,'label':'POC YTD · proxy D1/H1','year':year,'start_ms':start,'data_end_ms':last,'missing_hours':missing,'coverage':covered/expected if expected else 0,'stale_hours':max(0,(now-last)//3600000),'method':'96 bins, distribuție uniformă a volumului D1 + H1 curent între low/high; nu volum tranzacționat exact pe preț','timezone':'UTC'}
 _cache[key]=out;return out

def build(coin,rows,now):
 bars=[r for r in rows if r['t']+STEP<=now];levels=[];zones=[];events=[];highs=[];lows=[];prev=None;trend=0
 today=dt.datetime.fromtimestamp(now/1000,NY).date();yesterday=today-dt.timedelta(days=1);monday=today-dt.timedelta(days=today.weekday());prior=monday-dt.timedelta(days=7)
 for label,a,b in [('PD',yesterday,today),('PW',prior,monday),('W',monday,today+dt.timedelta(days=1))]:
  group=[r for r in bars if a<=dt.datetime.fromtimestamp(r['t']/1000,NY).date()<b]
  expected_start=int(dt.datetime.combine(a,dt.time(),NY).timestamp()*1000);expected_end=min(now,int(dt.datetime.combine(b,dt.time(),NY).timestamp()*1000));expected=int((expected_end-expected_start)//STEP)
  complete=len(group)>=expected and expected>0
  if group:
   for suffix,key,fn in [('H','h',max),('L','l',min)]:levels.append({'label':label+suffix+('' if complete else ' · parțial'),'price':fn(x[key] for x in group),'complete':complete,'timezone':'America/New_York','kind':'weekly' if label!='PD' else 'daily'})
 for i,r in enumerate(bars):
  t=r['t'];end=t+STEP
  for z in zones:
   if z['status']!='active':continue
   failed=(r['c']<z['invalidation'] if z['direction']==1 else r['c']>z['invalidation'])
   if failed:z.update(status='invalidated',end_ms=end);events.append({'kind':'invalidation','t':t,'known_ms':end,'price':z['invalidation'],'zone_id':z['id']})
  if i>=6:
   k=i-3;win=bars[k-3:k+4]
   if win[-1]['t']-win[0]['t']==6*STEP:
    if bars[k]['h']>max(x['h'] for j,x in enumerate(win) if j!=3):highs.append({'price':bars[k]['h'],'origin_ms':bars[k]['t'],'known_ms':end,'broken':False})
    if bars[k]['l']<min(x['l'] for j,x in enumerate(win) if j!=3):lows.append({'price':bars[k]['l'],'origin_ms':bars[k]['t'],'known_ms':end,'broken':False})
  gap=None
  if i>=2 and t-bars[i-2]['t']==2*STEP:
   if r['l']>bars[i-2]['h']:gap=(1,bars[i-2]['h'],r['l'])
   elif r['h']<bars[i-2]['l']:gap=(-1,r['h'],bars[i-2]['l'])
   if gap:
    d,lo,hi=gap;zones.append({'id':f'fvg:{end}:{d}','kind':'fvg','direction':d,'lo':lo,'hi':hi,'from_ms':bars[i-2]['t'],'known_ms':end,'invalidation':lo if d==1 else hi,'status':'active'})
  for d,items in [(1,highs),(-1,lows)]:
   candidates=[x for x in items if x['known_ms']<=t and not x['broken']]
   if not candidates or prev is None:continue
   level=candidates[-1];price=level['price']
   if (r['h']>price>r['c'] and prev<=price if d==1 else r['l']<price<r['c'] and prev>=price):events.append({'kind':'sweep','direction':-d,'t':t,'known_ms':end,'price':price})
   if d*(prev-price)<=0 and d*(r['c']-price)>0:
    level['broken']=True
    atr=statistics.mean(max(b['h']-b['l'],abs(b['h']-bars[max(0,j-1)]['c']),abs(b['l']-bars[max(0,j-1)]['c'])) for j,b in enumerate(bars[max(0,i-13):i+1],start=max(0,i-13)))
    strong=r['h']-r['l']>=atr and d*(r['c']-r['o'])>=.6*(r['h']-r['l'])
    kind='mss' if trend==-d and strong else 'bos'
    events.append({'kind':kind,'direction':d,'t':t,'known_ms':end,'price':price});trend=d
    opposite=[b for b in bars[max(0,i-6):i] if d*(b['c']-b['o'])<0]
    if opposite and gap and gap[0]==d and r['h']-r['l']>=atr and d*(r['c']-r['o'])>=.6*(r['h']-r['l']):
     ob=opposite[-1];lo=min(ob['o'],ob['c']);hi=max(ob['o'],ob['c']);zones.append({'id':f'ob:{end}:{d}','kind':'ob','direction':d,'lo':lo,'hi':hi,'from_ms':ob['t'],'known_ms':end,'invalidation':(lo+hi)/2,'status':'active','label':'OB candidat · BOS+FVG'})
  prev=r['c']
 return {'source':'context_detector_not_trade_signal','confirmed_ms':bars[-1]['t']+STEP if bars else None,'levels':levels,'zones':zones[-60:],'events':events[-60:],'poc':annual_profile(coin,now),'rules':'M15 închis; swing 3+3; MSS=break opus direcției precedente cu displacement ATR14/corp60%; BOS=alte breakuri;  OB contextual BOS+FVG+impuls ATR14/corp60%; invalidare OB la close prin MT. Nu califică o intrare.'}
