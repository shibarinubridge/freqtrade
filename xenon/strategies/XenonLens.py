"""Independent Lens paper/backtest strategy. No real-money execution accepted.

Reference tracker remains in packets; broker fills occur AFTER confirmation.
T1 is informational, all remaining quantity exits at T2 or the fixed stop.
"""
import datetime as dt
import json
import math
import pathlib
import sys
from zoneinfo import ZoneInfo
from ccxt import TICK_SIZE

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, stoploss_from_absolute

from lens_rules import calculate, packet, STEP, VERSION
from fvg_rules import META, tick, rounding

FEE=.00045
SLIP=.0001


def ms(value):
    aware=value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
    return int(aware.timestamp()*1000)


def encode(coin, direction, timestamp, entry, stop, target):
    # Native levels must be valid for Hyperliquid at their own prices. Stop
    # rounds toward entry and T2 toward entry, conservatively. The raw source
    # tracker in packets remains separate and unchanged.
    stop=rounding(coin,stop,direction==1)
    target=rounding(coin,target,direction==-1)
    return '|'.join(['XL1',coin,str(int(direction)),str(timestamp),*[format(float(v),'.12g') for v in [entry,stop,target]]])


def decode(tag):
    a=(tag or '').split('|')
    if len(a)!=7 or a[0]!='XL1' or a[1] not in META:raise ValueError('Missing Lens tag')
    d,t=int(a[2]),int(a[3]);e,s,z=map(float,a[4:])
    if d not in (-1,1) or t<=0 or any(not math.isfinite(v) or v<=0 for v in [e,s,z]) or d*(e-s)<=0 or d*(z-e)<=0:raise ValueError('Invalid Lens geometry')
    return {'coin':a[1],'direction':d,'signal_time':t,'entry':e,'stop':s,'target':z}


def unit_risk(o, entry):
    adverse=o['stop']*(1-o['direction']*SLIP)
    return o['direction']*(entry-adverse)+FEE*(entry+adverse)


class XenonLens(IStrategy):
    INTERFACE_VERSION=3
    timeframe='15m'
    startup_candle_count=1000
    process_only_new_candles=True
    can_short=True
    position_adjustment_enable=False
    use_custom_stoploss=True
    use_custom_roi=True
    minimal_roi={}
    stoploss=-.5
    trailing_stop=False
    use_exit_signal=True
    order_types={'entry':'market','exit':'market','stoploss':'market','stoploss_on_exchange':False}
    order_time_in_force={'entry':'GTC','exit':'GTC'}
    plot_config={'main_plot':{k:{'color':color} for k,color in [('lens_entry','#d9ac77'),('lens_stop','#db7777'),('lens_target','#52b99b'),('lens_ema20','#66bba9'),('lens_ema50','#d9ac77'),('lens_ema200','#a698cd')]},'subplots':{'Lens confluence':{'lens_long_score':{'color':'#52b99b'},'lens_short_score':{'color':'#db7777'}}}}

    def version(self):return VERSION+'-fixed-margin' if self.config.get('xenon_lens_margin_USDC') is not None else VERSION

    def bot_start(self,**kwargs):
        mode=getattr(self.config.get('runmode'),'value',self.config.get('runmode'))
        audit=mode=='util_no_exchange' and self.config.get('xenon_lens_lookahead_audit') is True
        if (mode not in ('backtest','dry_run') and not audit) or self.config.get('dry_run') is not True or self.config.get('force_entry_enable') is not False:raise RuntimeError('Lens accepts isolated dry-run/backtest only')
        if self.config.get('exchange',{}).get('name')!='hyperliquid':raise RuntimeError('Hyperliquid only')
        if abs(float(self.config.get('fee',0))-FEE)>1e-12 and self.config.get('fee')!=2*FEE:raise RuntimeError('Frozen base or explicit 2x fee stress only')
        self._historical=mode=='backtest' or audit
        self._budget=float(self.config.get('xenon_lens_risk_USDC',200))
        if not math.isfinite(self._budget) or self._budget<=0:raise RuntimeError('Invalid fixed Lens risk')
        self._leverage=float(self.config.get('xenon_lens_leverage',2))
        self._margin=self.config.get('xenon_lens_margin_USDC')
        if self._margin is not None:self._margin=float(self._margin)
        if not math.isfinite(self._leverage) or not 1<=self._leverage<=5:raise RuntimeError('Lens leverage must be within 1–5x')
        if self._margin is not None and (not math.isfinite(self._margin) or self._margin<=0):raise RuntimeError('Invalid Lens margin')
        self._slots=1 if self._margin is not None else 2
        self._runtime=pathlib.Path(self.config.get('xenon_runtime_dir',''))
        if not self._historical and ('lens' not in self._runtime.parts or not self._runtime.is_absolute()):raise RuntimeError('Lens needs its own absolute runtime directory')
        self._state={'consumed':[]};self._audit=[];self._boot=0 if self._historical else ms(dt.datetime.now(dt.timezone.utc))
        self._now=None
        state=self._runtime/'lens-risk.json'
        if not self._historical and state.exists():self._state=json.loads(state.read_text())
        self._observed=None
        if self.config.get('xenon_backtest_opens'):
            data=json.loads(pathlib.Path(self.config['xenon_backtest_opens']).read_text());self._observed={p:set(rows) for p,rows in data['main_times'].items()}

    def _write(self):
        destination=self.config.get('xenon_lens_audit') if self._historical else self._runtime/'lens-risk.json'
        if destination:
            p=pathlib.Path(destination);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix('.tmp')
            tmp.write_text(json.dumps({'state':self._state,'decisions':self._audit},allow_nan=False) if self._historical else json.dumps(self._state,allow_nan=False));tmp.replace(p)

    def _note(self,pair,reason,now,**details):
        record={'pair':pair,'reason':reason,'observed_ms':ms(now),**details}
        if self._audit and self._audit[-1]==record:return
        self._audit.append(record)
        if not self._historical:
            self._audit=self._audit[-1000:]
            path=self._runtime/'lens-decisions'/f'{pair.split("/")[0]}.json';path.parent.mkdir(parents=True,exist_ok=True)
            rows=[x for x in self._audit if x['pair']==pair][-30:];tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(rows,allow_nan=False));tmp.replace(path)
        self._write()

    def populate_indicators(self,dataframe,metadata):
        observed=dataframe
        if self._observed is not None:observed=dataframe.loc[dataframe.date.map(ms).isin(self._observed[metadata['pair']])]
        result=calculate(observed)
        result.index=observed.index
        out=dataframe.copy()
        for column in ['ema20','ema50','ema200','long_score','short_score','signal','ready','trade_entry','trade_stop','trade_t2']:
            name={'trade_entry':'entry','trade_stop':'stop','trade_t2':'target'}.get(column,column)
            out['lens_'+name]=result[column].reindex(out.index)
        out['lens_signal']=out.lens_signal.fillna(0);out['lens_ready']=out.lens_ready.fillna(False).astype(bool)
        out['lens_tag']=''
        coin=metadata['pair'].split('/')[0]
        for idx,b in result.iterrows():
            if b.trade_side in ('LONG','SHORT') and math.isfinite(b.trade_stop) and math.isfinite(b.trade_t2) and min(b.trade_stop,b.trade_t2)>0:
                out.at[idx,'lens_stop']=rounding(coin,b.trade_stop,b.trade_side=='LONG')
                out.at[idx,'lens_target']=rounding(coin,b.trade_t2,b.trade_side=='SHORT')
        for b in out.loc[out.lens_ready & out.lens_signal.ne(0)].itertuples():
            index=b.Index
            # Original close/ATR map is frozen in the tag, not recomputed at fill.
            if min(b.lens_entry,b.lens_stop,b.lens_target)>0:
                out.at[index,'lens_tag']=encode(coin,b.lens_signal,ms(b.date)+STEP,b.lens_entry,b.lens_stop,b.lens_target)
        if not getattr(self,'_historical',True):
            closed=result.loc[result.date.map(ms)+STEP<=ms(dt.datetime.now(dt.timezone.utc))]
            if len(closed):
                sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
                from lens_context import save_packet, chart_rows, atomic
                value=packet(closed,symbol='HYPERLIQUID:'+coin);value['xenon'].update(version=self.version(),execution_profile={'margin_USDC':self._margin,'leverage':self._leverage,'risk_cap_USDC':self._budget,'max_positions':self._slots},observation_source='freqtrade_lens_runtime',boot_ms=self._boot,observed_ms=ms(dt.datetime.now(dt.timezone.utc)))
                save_packet(self._runtime/'lens-packets',coin,value)
                atomic(self._runtime/'lens-packets/chart'/f'{coin}.json',chart_rows(closed))
        return out

    def populate_entry_trend(self,dataframe,metadata):
        valid=dataframe.lens_ready & dataframe.lens_tag.ne('')
        dataframe['enter_long']=(valid & dataframe.lens_signal.eq(1)).astype(int)
        dataframe['enter_short']=(valid & dataframe.lens_signal.eq(-1)).astype(int)
        dataframe['enter_tag']=dataframe.lens_tag
        return dataframe

    def populate_exit_trend(self,dataframe,metadata):
        dataframe['exit_long']=0;dataframe['exit_short']=0
        return dataframe

    def leverage(self,pair,current_time,current_rate,proposed_leverage,max_leverage,entry_tag,side,**kwargs):return min(float(self.config.get('xenon_lens_leverage',2)),max_leverage)

    def _account(self):
        equity=float(self.wallets.get_total(self.config['stake_currency']))
        trades=list(Trade.get_trades_proxy(is_open=True))
        gross=reserved=0.
        for t in trades:
            o=decode(t.enter_tag)
            amount=max(float(t.amount or 0),float(t.amount_requested or 0),float(t.stake_amount)*float(t.leverage)/float(t.open_rate))
            mark=float(t.open_rate)
            if not self._historical and t.amount>0:
                book=self.dp.orderbook(t.pair,1);mark=float(book['asks' if t.is_short else 'bids'][0][0]);equity+=float(t.calc_profit_ratio(mark))*float(t.stake_amount)
            elif self._historical and t.amount>0:
                bars=self.dp.get_pair_dataframe(t.pair,self.timeframe)
                bars=bars.loc[bars.date.map(ms)+STEP<=ms(self._now)]
                if bars.empty:raise ValueError('No closed historical mark')
                mark=float(bars.iloc[-1].close);equity+=float(t.calc_profit_ratio(mark))*float(t.stake_amount)
            gross+=amount*max(mark,t.open_rate);reserved+=amount*unit_risk(o,t.open_rate)
        if not math.isfinite(equity) or equity<=0:raise ValueError('Invalid equity')
        return equity,trades,gross,reserved

    def _gate(self,equity,now):
        # Keep the existing pilot's loss gates; do not loosen them to force $200.
        day=now.astimezone(ZoneInfo('Europe/Bucharest')).date().isoformat();s=self._state;s['peak']=max(equity,s.get('peak',equity))
        if s.get('day')!=day:s.update(day=day,day_start=equity,day_blocked=False)
        if equity<=s['day_start']*.985:s['day_blocked']=True
        if equity<=s['peak']*.975:s['suspended']=True
        return not s.get('day_blocked') and not s.get('suspended')

    def bot_loop_start(self,current_time,**kwargs):
        try:
            self._now=current_time;before=json.dumps(self._state,sort_keys=True)
            eq,*_=self._account();self._gate(eq,current_time)
            if json.dumps(self._state,sort_keys=True)!=before:self._write()
        except Exception:pass

    def _valid(self,pair,o,now,rate,side):
        if o['coin']!=pair.split('/')[0] or o['direction']!=(1 if side=='long' else -1):return False
        if o['signal_time']<self._boot or not 0<=ms(now)-o['signal_time']<=120000:return False
        if o['direction']*(rate-o['stop'])<=0 or o['direction']*(o['target']-rate)<=0:return False
        risk=unit_risk(o,rate)
        reward=o['direction']*(o['target']*(1-o['direction']*SLIP)-rate)-FEE*(rate+o['target'])
        return risk>0 and reward/risk>=1

    def custom_stake_amount(self,pair,current_time,current_rate,proposed_stake,min_stake,max_stake,leverage,entry_tag,side,**kwargs):
        try:
            o=decode(entry_tag)
            if not self._valid(pair,o,current_time,current_rate,side):self._note(pair,'stale_or_invalid_geometry',current_time,tag=entry_tag);return 0.
            eq,trades,gross,reserved=self._account()
            if not self._gate(eq,current_time) or entry_tag in self._state['consumed'] or len(trades)>=self._slots:self._note(pair,'risk_guard_or_capacity',current_time,tag=entry_tag);return 0.
            scale=10**META[o['coin']]['szDecimals'];unit=unit_risk(o,current_rate)
            if self._margin is not None and leverage!=self._leverage:self._note(pair,'requested_leverage_unavailable',current_time,tag=entry_tag);return 0.
            desired_q=self._budget/unit if self._margin is None else self._margin*leverage/current_rate
            q=math.floor(desired_q*scale)/scale;notional=q*current_rate;stake=notional/leverage
            reason='sizing_approved'
            if q<=0 or notional<10 or stake<(min_stake or 0):reason='minimum_order'
            elif stake>max_stake or gross+notional>self._leverage*eq:reason='margin_or_2x_exposure' if self._leverage==2 else 'margin_or_exposure_limit'
            elif q*unit>self._budget+1e-8:reason='fixed_margin_exceeds_risk_cap'
            elif reserved+q*unit>self._slots*self._budget+1e-8:reason='open_risk_cap'
            self._note(pair,reason,current_time,tag=entry_tag,risk_USDC=q*unit,requested_risk_USDC=self._budget,required_margin_USDC=stake,available_margin_USDC=max_stake,minimum_gross_leverage=notional/eq)
            return stake if reason=='sizing_approved' else 0.
        except Exception as e:self._note(pair,'sizing_error',current_time,error_type=type(e).__name__);return 0.

    def confirm_trade_entry(self,pair,order_type,amount,rate,time_in_force,current_time,entry_tag,side,**kwargs):
        try:
            if self.config.get('dry_run') is not True or self.config.get('force_entry_enable') is not False or order_type!='market' or time_in_force!='GTC':return False
            o=decode(entry_tag)
            if not math.isfinite(amount) or not math.isfinite(rate) or amount<=0 or rate<=0 or amount*rate<10:return False
            if not self._valid(pair,o,current_time,rate,side):return False
            eq,trades,gross,reserved=self._account();loss=amount*unit_risk(o,rate)
            if entry_tag in self._state['consumed'] or not self._gate(eq,current_time) or len(trades)>=self._slots or loss>self._budget+1e-8 or reserved+loss>self._slots*self._budget+1e-8 or gross+amount*rate>self._leverage*eq+1e-8:return False
            if self._margin is not None and amount*rate>self._margin*self._leverage+1e-8:return False
            if o['direction']*(rate-o['stop'])/rate>=.2:return False
            self._state['consumed'].append(entry_tag);self._state['consumed']=self._state['consumed'][-4000:];self._note(pair,'placement_authorized',current_time,tag=entry_tag,risk_USDC=loss)
            return True
        except Exception:return False

    def custom_stoploss(self,pair,trade,current_time,current_rate,current_profit,after_fill=False,**kwargs):
        try:
            o=decode(trade.enter_tag)
            # Avoid a floating-point reconstruction crossing an exchange tick
            # when the framework rounds a long stop up / short stop down.
            stop=o['stop']*(1-o['direction']*1e-12)
            return stoploss_from_absolute(stop,current_rate,is_short=trade.is_short,leverage=trade.leverage)
        except Exception:return None

    def order_filled(self,pair,trade,order,current_time,**kwargs):
        if order.ft_order_side==trade.entry_side and float(order.filled or 0)>0:
            o=decode(trade.enter_tag)
            if self._historical:
                # Upstream monthly candle-derived precision can include future
                # prices. Freeze known instrument precision before stop/ROI.
                trade.price_precision=min(tick(o['coin'],v) for v in [trade.open_rate,o['stop'],o['target']])
                trade.precision_mode_price=TICK_SIZE
            if trade.get_custom_data('lens_fill_ms') is None:trade.set_custom_data('lens_fill_ms',ms(order.order_filled_date or current_time))
            trade.set_custom_data('lens_setup',o);trade.set_custom_data('lens_risk_USDC',trade.amount*unit_risk(o,trade.open_rate))
        elif not trade.is_open and not self._historical:
            p=self._runtime/'lens-reviews'/f'{trade.id}.json';p.parent.mkdir(exist_ok=True)
            p.write_text(json.dumps({'trade_id':trade.id,'pair':pair,'net_USDC':trade.close_profit_abs,'exit_reason':trade.exit_reason,'tag':trade.enter_tag,'source':'NATIVE_LENS_DRY_RUN'}))

    def custom_roi(self,pair,trade,current_time,trade_duration,entry_tag,side,**kwargs):
        try:
            fill=trade.get_custom_data('lens_fill_ms')
            if fill is None or ms(current_time)//60000<=fill//60000:return None
            return float(trade.calc_profit_ratio(decode(trade.enter_tag)['target']))
        except Exception:return None

    def custom_exit(self,pair,trade,current_time,current_rate,current_profit,**kwargs):
        try:
            o=decode(trade.enter_tag);fill=trade.get_custom_data('lens_fill_ms')
            if fill is None:return 'lens_missing_fill_metadata'
            if o['direction']*(current_rate-o['stop'])<=0 and abs((trade.stop_loss or 0)-o['stop'])>tick(o['coin'],o['stop']):return 'lens_invalid_fill_stop'
            df,_=self.dp.get_analyzed_dataframe(pair,self.timeframe)
            closed=df.loc[df.date.map(ms)+STEP<=ms(current_time)]
            if len(closed):
                last=closed.iloc[-1]
                if last.lens_ready and last.lens_signal==-o['direction'] and 0<=ms(current_time)-ms(last.date)-STEP<=120000:return 'lens_opposite_setup'
            return None
        except Exception:return 'lens_missing_setup'
