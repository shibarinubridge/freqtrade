"""AI Agent Lens Python port; closed-bar context, not broker execution.

Adapted from roan-maverick/AI Agent Lens, MIT (see ../vendor/ai-agent-lens).
Pine initialization/pivot parity remains unverified without a Pine oracle.
All higher-timeframe features become available at the main candle OPEN.
"""
from dataclasses import dataclass, asdict
import datetime as dt
import math

import numpy as np
import pandas as pd

STEP = 900000
VERSION = 'xenon-lens-2'


@dataclass(frozen=True)
class Settings:
    threshold: int = 70
    block_high_vol: bool = True
    htf_minutes: int = 240
    htf_ema_length: int = 50
    swing: int = 5
    stop_atr: float = 1.5
    target_1_r: float = 1.5
    target_2_r: float = 3.0


def rma(series, length):
    """Wilder RMA seeded by the first length nonmissing observations."""
    result = []
    seed = []
    last = None
    for raw in series:
        if not math.isfinite(raw):
            result.append(np.nan if last is None else last)
            continue
        if last is None:
            seed.append(float(raw))
            if len(seed) == length:
                last = sum(seed) / length
        else:
            last = (last * (length - 1) + raw) / length
        result.append(np.nan if last is None else last)
    return pd.Series(result, index=series.index, dtype=float)


def complete_groups(frame, minutes):
    """UTC buckets: never synthesize absent candles or accept partial HTF bars."""
    group = frame.set_index('date').resample(f'{minutes}min', origin='epoch')
    aggregate = group.agg({'open':'first', 'high':'max', 'low':'min', 'close':'last', 'volume':'sum'})
    count = group.close.count()
    return aggregate.loc[count == minutes // 15].reset_index()


def known_higher(frame, minutes, ema_length=None):
    higher = complete_groups(frame, minutes)
    if higher.empty:
        return pd.DataFrame(index=frame.index, columns=['known_close', 'known_ema', 'known_high', 'known_low'], dtype=float)
    higher['available'] = higher.date + pd.Timedelta(minutes=minutes)
    higher['known_close'] = higher.close
    higher['known_ema'] = higher.close.ewm(span=ema_length or 50, adjust=False).mean()
    higher['known_high'], higher['known_low'] = higher.high, higher.low
    higher['known_count'] = np.arange(1, len(higher)+1)
    columns = ['known_close', 'known_ema', 'known_high', 'known_low', 'known_count']
    # Pine expr[1] + lookahead_on uses the previous HTF at main-bar OPEN,
    # including the last main bar which closes exactly at the HTF boundary.
    joined = pd.merge_asof(frame[['date']], higher[['available', *columns]], left_on='date', right_on='available', direction='backward')
    # Do not carry an old HTF/day over a missing bucket.
    joined.loc[(joined.date-joined.available) >= pd.Timedelta(minutes=minutes), columns] = np.nan
    joined.index = frame.index
    return joined


def pattern(o, h, l, c, prev, atr):
    rng, body = h-l, abs(c-o)
    if rng <= 0:
        return 'FLAT'
    if prev is not None:
        po, ph, pl, pc = prev
        if c > o and pc < po and c >= po and o <= pc:
            return 'BULLISH_ENGULFING'
        if c < o and pc > po and c <= po and o >= pc:
            return 'BEARISH_ENGULFING'
    if body/rng <= .1:
        return 'DOJI'
    if min(o,c)-l >= 2*body and h-max(o,c) <= .15*rng:
        return 'HAMMER'
    if h-max(o,c) >= 2*body and min(o,c)-l <= .15*rng:
        return 'SHOOTING_STAR'
    if body/rng >= .9:
        return 'BULLISH_MARUBOZU' if c > o else 'BEARISH_MARUBOZU'
    if prev is not None:
        if h < ph and l > pl:
            return 'INSIDE_BAR'
        if h > ph and l < pl:
            return 'OUTSIDE_BAR'
    if atr > 0 and rng >= 1.8*atr:
        return 'WIDE_RANGE_BULL' if c > o else 'WIDE_RANGE_BEAR'
    return 'NONE'


def calculate(frame, settings=Settings()):
    """One output per observed M15 bar. Future prefixes never alter past rows."""
    f = frame[['date','open','high','low','close','volume']].copy().reset_index(drop=True)
    # Freqtrade/Feather can supply ms/us/ns. merge_asof requires identical units.
    f['date'] = pd.to_datetime(f.date, utc=True).astype('datetime64[ns, UTC]')
    if not f.date.is_monotonic_increasing or f.date.duplicated().any():
        raise ValueError('Candles must be sorted and unique')
    if not (f.date.dt.minute.mod(15).eq(0) & f.date.dt.second.eq(0) & f.date.dt.microsecond.eq(0)).all():
        raise ValueError('Expected UTC-aligned M15 candles')
    prices = f[['open','high','low','close']].to_numpy(dtype=float)
    if not np.isfinite(prices).all() or (prices <= 0).any():
        raise ValueError('Invalid OHLC')
    if ((f.low > f[['open','close']].min(axis=1)) | (f.high < f[['open','close']].max(axis=1)) | (f.high < f.low)).any():
        raise ValueError('Inconsistent OHLC')
    if ((f.volume < 0) | np.isinf(f.volume)).any():
        raise ValueError('Invalid volume')
    if f.empty:
        return f
    c, h, l, o = f.close, f.high, f.low, f.open
    for n in [20,50,200]:
        f[f'ema{n}'] = c.ewm(span=n, adjust=False).mean()
    change = c.diff()
    gain, loss = rma(change.clip(lower=0),14), rma((-change).clip(lower=0),14)
    f['rsi'] = 100-100/(1+gain/loss)
    f.loc[(gain == 0) & (loss == 0), 'rsi'] = np.nan
    macd = c.ewm(span=12,adjust=False).mean()-c.ewm(span=26,adjust=False).mean()
    f['macd_hist'] = macd-macd.ewm(span=9,adjust=False).mean()
    tr = pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    f['atr'] = rma(tr,14)
    up, down = h.diff(), -l.diff()
    plus = up.where((up > down) & (up > 0),0.0)
    minus = down.where((down > up) & (down > 0),0.0)
    plus.iloc[0] = minus.iloc[0] = np.nan
    dmi_tr = tr.copy();dmi_tr.iloc[0] = np.nan
    base = rma(dmi_tr,14)
    f['di_plus'], f['di_minus'] = 100*rma(plus,14)/base, 100*rma(minus,14)/base
    total = f.di_plus+f.di_minus
    f['adx'] = 100*rma((f.di_plus-f.di_minus).abs()/total.where(total != 0,1),14)
    f['atr_percentile'] = f.atr.rolling(100,min_periods=100).apply(lambda a:100*np.count_nonzero(a <= a[-1])/len(a),raw=True)
    avg = f.volume.rolling(20,min_periods=20).mean()
    f['relative_volume'] = f.volume/avg.where(avg > 0)
    days = f.date.dt.floor('D')
    vol = f.volume.fillna(0)
    f['vwap'] = (((h+l+c)/3*vol).groupby(days).cumsum()/vol.groupby(days).cumsum().replace(0,np.nan)).where(f.volume.notna())
    session_count=f.groupby(days).cumcount()+1
    f['vwap_complete_session'] = f.groupby(days).date.transform('min').eq(days) & ((f.date-days).dt.total_seconds()/900+1).eq(session_count)
    higher, daily = known_higher(f,settings.htf_minutes,settings.htf_ema_length), known_higher(f,1440)
    f['htf_close'], f['htf_ema'] = higher.known_close, higher.known_ema
    f['htf_ready'] = higher.get('known_count',pd.Series(0,index=f.index)).ge(settings.htf_ema_length)
    f['pdh'], f['pdl'] = daily.known_high,daily.known_low
    f['htf_bias'] = np.where(f.htf_close > f.htf_ema,'UP',np.where(f.htf_close < f.htf_ema,'DOWN','FLAT'))
    f.loc[f.htf_close.isna(),'htf_bias'] = 'UNAVAILABLE'
    rising = f.ema200 > f.ema200.shift(5)
    falling = f.ema200 < f.ema200.shift(5)
    f['regime'] = np.select([f.atr_percentile >= 90,(c > f.ema200)&rising&(f.adx >= 20),(c < f.ema200)&falling&(f.adx >= 20)],['HIGH_VOLATILITY','TREND_UP','TREND_DOWN'],default='RANGE')
    f['ready'] = (f.index >= 200) & f.htf_ready & f[['atr','rsi','adx','atr_percentile']].notna().all(axis=1)
    for d, side in [(1,'long'),(-1,'short')]:
        f[side+'_trend'] = 7*(d*(f.ema20-f.ema50)>0).astype(int)+7*(d*(f.ema50-f.ema200)>0).astype(int)+6*(d*(c-f.ema20)>0).astype(int)
        rsi_points = np.where(d*(f.rsi-50)>0,np.where(f.rsi >= 75 if d==1 else f.rsi <= 25,4,10),0)
        f[side+'_momentum'] = rsi_points+5*(d*f.macd_hist > 0).astype(int)+5*(d*f.macd_hist.diff()>0).astype(int)
        stronger = (f.di_plus > f.di_minus) if d==1 else (f.di_minus > f.di_plus)
        f[side+'_strength'] = 10*stronger.astype(int)+10*(stronger&(f.adx>=20)).astype(int)
        # Follow code: bullish/bearish candles still receive 6 points when
        # relative volume is missing (README/spec claim zero in that case).
        f[side+'_volume'] = np.where(d*(c-o)>0,np.select([f.relative_volume>=1.5,f.relative_volume>=1],[20,12],default=6),0)
        f[side+'_htf'] = np.select([f.htf_bias==('UP' if d==1 else 'DOWN'),f.htf_bias.isin(['FLAT','UNAVAILABLE'])],[20,10],default=0)
        f[side+'_score'] = f[[side+'_'+k for k in ['trend','momentum','strength','volume','htf']]].sum(axis=1)
        f[side+'_condition'] = (f[side+'_score']>=settings.threshold)&(f[side+'_score'].shift()<settings.threshold)&(f.regime!=('TREND_DOWN' if d==1 else 'TREND_UP'))
        if settings.block_high_vol:
            f[side+'_condition'] &= f.regime!='HIGH_VOLATILITY'
    f['signal'] = 0
    f['structure_bias'], f['structure_event'], f['pattern'] = 'MIXED','NONE','NONE'
    for col in ['swing_high','swing_low','swing_high_origin_ms','swing_low_origin_ms','swing_high_known_ms','swing_low_known_ms','trade_entry','trade_stop','trade_t1','trade_t2','trade_bar','last_setup_bar']:
        f[col] = np.nan
    f['trade_side'], f['trade_status'], f['last_setup_side'],f['event'] = 'NONE','NONE','NONE','BAR_CLOSE'
    sh, sl = [], []
    tside, last_side, status, tradebar, lastbar = 0,'NONE','NONE',None,None
    entry = stop = t1 = t2 = np.nan
    strength = settings.swing
    timestamps = [int(t.timestamp()*1000) for t in f.date]
    for i, b in enumerate(f.itertuples()):
        now = timestamps[i]+STEP
        if i >= 2*strength:
            k = i-strength
            # Confirm at i; never draw the pivot at k as if known then.
            if timestamps[i]-timestamps[i-2*strength] == 2*strength*STEP:
                if h.iloc[k] >= h.iloc[k-strength:k].max() and h.iloc[k] > h.iloc[k+1:i+1].max():
                    sh.append((float(h.iloc[k]),timestamps[k],now))
                if l.iloc[k] <= l.iloc[k-strength:k].min() and l.iloc[k] < l.iloc[k+1:i+1].min():
                    sl.append((float(l.iloc[k]),timestamps[k],now))
        for name, values in [('high',sh),('low',sl)]:
            if values:
                f.at[i,'swing_'+name],f.at[i,'swing_'+name+'_origin_ms'],f.at[i,'swing_'+name+'_known_ms'] = values[-1]
        if len(sh)>1 and len(sl)>1:
            f.at[i,'structure_bias'] = 'BULLISH' if sh[-1][0]>sh[-2][0] and sl[-1][0]>sl[-2][0] else 'BEARISH' if sh[-1][0]<sh[-2][0] and sl[-1][0]<sl[-2][0] else 'MIXED'
        previous = None if i==0 else (o.iloc[i-1],h.iloc[i-1],l.iloc[i-1],c.iloc[i-1])
        if previous:
            if sh and b.close>sh[-1][0] and previous[3]<=sh[-1][0]:f.at[i,'structure_event']='BREAK_UP'
            elif sl and b.close<sl[-1][0] and previous[3]>=sl[-1][0]:f.at[i,'structure_event']='BREAK_DOWN'
        f.at[i,'pattern'] = pattern(b.open,b.high,b.low,b.close,previous,b.atr)
        before = status
        if tside and i > tradebar:
            if b.low <= stop if tside==1 else b.high >= stop:
                status = 'STOPPED_AFTER_T1' if status=='TARGET_1_HIT' else 'STOPPED';tside=0
            elif b.high >= t2 if tside==1 else b.low <= t2:
                status='TARGET_2_HIT';tside=0
            elif (b.high >= t1 if tside==1 else b.low <= t1) and status=='ACTIVE':status='TARGET_1_HIT'
        long = b.long_condition and not b.short_condition
        short = b.short_condition and not b.long_condition
        direction = 1 if long and tside!=1 else -1 if short and tside!=-1 else 0
        if direction and math.isfinite(b.atr):
            tside=direction;last_side='LONG' if direction==1 else 'SHORT';status='ACTIVE';tradebar=lastbar=i
            entry=b.close;distance=settings.stop_atr*b.atr;stop=entry-direction*distance;t1=entry+direction*distance*settings.target_1_r;t2=entry+direction*distance*settings.target_2_r
            f.at[i,'signal']=direction
            f.at[i,'event']='LONG_SETUP' if direction==1 else 'SHORT_SETUP'
        elif before!=status:f.at[i,'event']='TRADE_UPDATE'
        f.at[i,'trade_side']=last_side;f.at[i,'trade_status']=status;f.at[i,'last_setup_side']=last_side
        for col, value in [('trade_entry',entry),('trade_stop',stop),('trade_t1',t1),('trade_t2',t2),('trade_bar',tradebar),('last_setup_bar',lastbar)]:
            if value is not None:f.at[i,col]=value
    return f


def number(value, places=None):
    if value is None or not math.isfinite(float(value)):
        return None
    return float(value) if places is None else round(float(value),places)


def packet(frame, index=-1, symbol='HYPERLIQUID:BTC', settings=Settings()):
    """Schema-compatible packet plus explicit XENON provenance/quality fields."""
    if frame.empty:
        return None
    i = len(frame)-1 if index==-1 else index
    b = frame.iloc[i]
    prev = frame.iloc[i-1] if i else None
    rng = b.high-b.low
    num = number
    candle = {'open':b.open,'high':b.high,'low':b.low,'close':b.close,'volume':num(b.volume,4),'direction':'bull' if b.close>b.open else 'bear' if b.close<b.open else 'flat','body_pct':num(abs(b.close-b.open)/rng*100 if rng else 0,1),'upper_wick_pct':num((b.high-max(b.open,b.close))/rng*100 if rng else 0,1),'lower_wick_pct':num((min(b.open,b.close)-b.low)/rng*100 if rng else 0,1),'range_atr':num(rng/b.atr if b.atr>0 else None,2),'close_position_pct':num((b.close-b.low)/rng*100 if rng else 50,1),'gap_pct':num((b.open-prev.close)/prev.close*100 if prev is not None else None,3),'closed_above_prev_high':bool(prev is not None and b.close>prev.high),'closed_below_prev_low':bool(prev is not None and b.close<prev.low),'pattern':b.pattern}
    recent = []
    for j in range(max(0,i-4),i+1):
        r=frame.iloc[j];rr=r.high-r.low
        recent.append({'bars_ago':i-j,'o':r.open,'h':r.high,'l':r.low,'c':r.close,'v':num(r.volume,4),'dir':'bull' if r.close>r.open else 'bear' if r.close<r.open else 'flat','body_pct':num(abs(r.close-r.open)/rr*100 if rr else 0,1),'range_atr':num(rr/r.atr if r.atr>0 else None,2),'pattern':r.pattern})
    factors = {side:{k:int(b[side+'_'+k]) for k in ['trend','momentum','strength','volume','htf']} for side in ['long','short']}
    time = b.date+pd.Timedelta(minutes=15)
    state = f'LENS|{symbol.split(":")[-1]}|15|{b.regime}|L{b.long_score}|S{b.short_score}|{b.trade_side}:{b.trade_status}'
    return {'schema':'ai-agent-lens/v1','event':b.event,'symbol':symbol,'timeframe':'15','time':time.strftime('%Y-%m-%dT%H:%M:%SZ'),'state_code':state,'candle':candle,'recent_candles':recent,'regime':b.regime,
            'trend':{'ema_fast':num(b.ema20),'ema_mid':num(b.ema50),'ema_slow':num(b.ema200),'stack':'BULLISH' if b.ema20>b.ema50>b.ema200 else 'BEARISH' if b.ema20<b.ema50<b.ema200 else 'MIXED','slow_slope':'RISING' if i>=5 and b.ema200>frame.iloc[i-5].ema200 else 'FALLING' if i>=5 and b.ema200<frame.iloc[i-5].ema200 else 'FLAT','htf':str(settings.htf_minutes),'htf_bias':b.htf_bias if b.htf_bias!='UNAVAILABLE' else 'N/A'},
            'momentum':{'rsi':num(b.rsi,2),'macd_hist':num(b.macd_hist,6),'macd_hist_rising':bool(prev is not None and b.macd_hist>prev.macd_hist)},'strength':{'adx':num(b.adx,2),'di_plus':num(b.di_plus,2),'di_minus':num(b.di_minus,2)},'volatility':{'atr':num(b.atr),'atr_percentile':num(b.atr_percentile,1)},'volume':{'relative':num(b.relative_volume,2)},
            'structure':{'bias':b.structure_bias,'event':b.structure_event,'last_swing_high':num(b.swing_high),'last_swing_low':num(b.swing_low)},'levels':{'prev_day_high':num(b.pdh),'prev_day_low':num(b.pdl),'vwap':num(b.vwap)},'scores':{'long':int(b.long_score),'short':int(b.short_score),'threshold':settings.threshold,'long_factors':factors['long'],'short_factors':factors['short']},
            'trade':{'side':b.trade_side,'status':b.trade_status,'entry':num(b.trade_entry),'stop':num(b.trade_stop),'target_1':num(b.trade_t1),'target_2':num(b.trade_t2),'bars_since_entry':int(i-b.trade_bar) if pd.notna(b.trade_bar) else None},'last_setup':{'side':b.last_setup_side,'bars_ago':int(i-b.last_setup_bar) if pd.notna(b.last_setup_bar) else None},
            'xenon':{'version':VERSION,'source':'hyperliquid_ohlcv_python','closed_ms':int(time.timestamp()*1000),'ready':bool(b.ready),'execution':'REFERENCE_ONLY_NOT_BROKER','pine_numeric_parity':'UNVERIFIED','timezone':'UTC','vwap_complete_session':bool(b.vwap_complete_session),'htf_available_at':'main_bar_open','settings':asdict(settings),'swing_high_origin_ms':num(b.swing_high_origin_ms),'swing_high_known_ms':num(b.swing_high_known_ms),'swing_low_origin_ms':num(b.swing_low_origin_ms),'swing_low_known_ms':num(b.swing_low_known_ms)}}
