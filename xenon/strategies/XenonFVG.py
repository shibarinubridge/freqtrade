"""Prospective Hyperliquid dry-run FVG. Never approved for real orders.

Frozen signal geometry; execution differences are documented in FVG-PORT.md.
Every entry callback fails closed. Entry tags make pending setup data immutable
and recoverable across analysis updates/restarts without a private dataset path.
"""
import datetime as dt,json,logging,math,pathlib
from zoneinfo import ZoneInfo
from pandas import DataFrame
from freqtrade.strategy import IStrategy,stoploss_from_absolute
from freqtrade.persistence import Trade
from fvg_rules import detect,tick,META,STEP
log=logging.getLogger(__name__)
FEE=.00045
SLIP=.0001

def ms(value):return int((value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)).timestamp()*1000)
def encode(o):
    return '|'.join(['XF1',o['coin'],str(o['direction']),str(o['signal_time'])]+[format(float(o[k]),'.12g') for k in ('entry_limit','stop','target')]+[format(float(o['old_gap'][k]),'.12g') for k in ('lo','hi')])
def decode(tag):
    a=(tag or '').split('|')
    if len(a)!=9 or a[0]!='XF1' or a[1] not in META:raise ValueError('Missing FVG setup')
    coin=a[1];d=int(a[2]);t=int(a[3]);e,s,z,lo,hi=map(float,a[4:])
    if d not in (-1,1) or t<=0 or any(not math.isfinite(x) or x<=0 for x in [e,s,z,lo,hi]) or lo>hi or d*(e-s)<=0 or d*(z-e)<=0:raise ValueError('Invalid FVG geometry')
    return {'coin':coin,'direction':d,'signal_time':t,'entry_limit':e,'stop':s,'target':z,'old_gap':{'lo':lo,'hi':hi},'expires':t+12*STEP}
def risk_unit(o,entry=None):
    e=o['entry_limit'] if entry is None else entry;d=o['direction'];stop=o['stop']*(1-d*SLIP)
    return d*(e-stop)+FEE*(e+stop)
def planned_rr(o):
    d=o['direction'];e=o['entry_limit'];target=o['target']*(1-d*SLIP)
    return (d*(target-e)-FEE*(e+target))/risk_unit(o)

class XenonFVG(IStrategy):
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
    exit_profit_only=False
    ignore_roi_if_entry_signal=False
    ignore_buying_expired_candle_after=120
    order_types={'entry':'limit','exit':'market','stoploss':'market','stoploss_on_exchange':False}
    order_time_in_force={'entry':'GTC','exit':'GTC'}
    plot_config={'main_plot':{'fvg_limit':{'color':'#d9a779'},'fvg_stop':{'color':'#d27d7d'},'fvg_target':{'color':'#83b79c'},'xenon_ema20':{'color':'#929da9'}}}
    def version(self):return 'xenon-fvg-dryrun-1'
    def __init__(self,config):
        super().__init__(config);self._boot_ms=ms(dt.datetime.now(dt.timezone.utc));self._risk={};self._risk_path=pathlib.Path(__file__).resolve().parents[1]/'.runtime/fvg-risk.json'
    def bot_start(self,**kwargs):
        if self.config.get('dry_run') is not True or self.config.get('force_entry_enable') is not False:raise RuntimeError('XenonFVG requires dry-run and no force entry')
        if getattr(self.config.get('runmode'),'value',self.config.get('runmode')) not in ('dry_run',None):raise RuntimeError('Historical backtesting is not the approved execution model for this port')
        if abs(float(self.config.get('fee',0))-FEE)>1e-12:raise RuntimeError('XenonFVG requires its frozen conservative fee override')
        if self._risk_path.exists():self._risk=json.loads(self._risk_path.read_text())
        self._risk.setdefault('consumed',[])
        log.warning('XenonFVG enabled for prospective DRY-RUN only. Risk .5%, min planned net1R, GTC nonmarketable Limit, all-taker fees .045%. Source replay PnL is not transferable.')
    def _save(self):
        self._risk_path.parent.mkdir(exist_ok=True,mode=0o700);tmp=self._risk_path.with_suffix('.tmp');tmp.write_text(json.dumps(self._risk,indent=2));tmp.replace(self._risk_path)
    def _closed(self,pair,now):
        df,_=self.dp.get_analyzed_dataframe(pair,self.timeframe)
        return df.loc[df['date'].map(ms)+STEP<=ms(now)]
    def _trades(self):return list(Trade.get_trades_proxy(is_open=True))
    def _account(self,now):
        trades=self._trades();equity=float(self.wallets.get_total(self.config['stake_currency']))
        for t in trades:
            if t.amount>0:
                book=self.dp.orderbook(t.pair,1);mark=float(book['asks' if t.is_short else 'bids'][0][0])
                equity+=float(t.calc_profit_ratio(mark))*float(t.stake_amount)
        if not math.isfinite(equity) or equity<=0:raise ValueError('Invalid equity')
        return equity,trades
    def _gate(self,eq,now):
        day=now.astimezone(ZoneInfo('Europe/Bucharest')).date().isoformat();self._risk.setdefault('peak',eq)
        self._risk['peak']=max(eq,self._risk['peak'])
        if self._risk.get('day')!=day:self._risk.update(day=day,day_start=eq,day_blocked=False)
        if eq<=self._risk['day_start']*.985:self._risk['day_blocked']=True
        if eq<=self._risk['peak']*.975:self._risk['suspended']=True
        return not self._risk.get('day_blocked') and not self._risk.get('suspended')
    def bot_loop_start(self,current_time,**kwargs):
        try:
            eq,_=self._account(current_time);self._gate(eq,current_time);self._save()
            for trade in Trade.get_trades_proxy(is_open=False):
                if (trade.enter_tag or '').startswith('XF1|'):self._journal(trade)
        except Exception as e:log.warning('FVG monitoring check: %s',type(e).__name__)
    def populate_indicators(self,dataframe:DataFrame,metadata:dict)->DataFrame:
        df=dataframe;coin=metadata['pair'].split('/')[0]
        df['xenon_ema20']=df['close'].ewm(span=20,adjust=False).mean()
        for col in ('fvg_limit','fvg_stop','fvg_target'):df[col]=float('nan')
        df['fvg_direction']=0;df['fvg_tag']=''
        if coin not in META or df.empty:return df
        rows=[{'t':ms(x.date),'end':ms(x.date)+STEP,'o':float(x.open),'h':float(x.high),'l':float(x.low),'c':float(x.close),'v':float(x.volume)} for x in df.itertuples()]
        events,_=detect(coin,rows);indexes={x['end']:idx for idx,x in zip(df.index,rows)}
        for time,items in events.items():
            for event in items:
                o=event['order']
                if planned_rr(o)<1:continue
                idx=indexes[time];df.at[idx,'fvg_direction']=o['direction'];df.at[idx,'fvg_tag']=encode(o)
                for col,key in [('fvg_limit','entry_limit'),('fvg_stop','stop'),('fvg_target','target')]:df.at[idx,col]=o[key]
        return df
    def populate_entry_trend(self,dataframe,metadata):
        dataframe['enter_long']=(dataframe['fvg_direction']==1).astype(int);dataframe['enter_short']=(dataframe['fvg_direction']==-1).astype(int);dataframe['enter_tag']=dataframe['fvg_tag'];return dataframe
    def populate_exit_trend(self,dataframe,metadata):
        dataframe['exit_long']=0;dataframe['exit_short']=0;return dataframe
    def leverage(self,pair,current_time,current_rate,proposed_leverage,max_leverage,entry_tag,side,**kwargs):return min(2.,max_leverage)
    def _valid_setup(self,pair,o,now,pending=False):
        time=ms(now)
        if o['coin']!=pair.split('/')[0]:return False
        if time<o['signal_time'] or time>=o['expires']:return False
        if not pending and (o['signal_time']<self._boot_ms or time-o['signal_time']>120000):return False
        bars=self._closed(pair,now)
        if bars.empty:return False
        for x in bars.itertuples():
            if ms(x.date)<o['signal_time']:continue
            if (x.close<o['old_gap']['lo'] if o['direction']==1 else x.close>o['old_gap']['hi']):return False
            if (x.high>=o['target'] if o['direction']==1 else x.low<=o['target']):return False
        return True
    def custom_entry_price(self,pair,trade,current_time,proposed_rate,entry_tag,side,**kwargs):
        try:return decode(entry_tag)['entry_limit']
        except Exception:return proposed_rate
    def _reserved(self,trades):
        gross=risk=0.
        for t in trades:
            o=decode(t.enter_tag);q=max(float(t.amount or 0),float(t.amount_requested or 0),float(t.stake_amount)*float(t.leverage)/float(t.open_rate))
            mark=max(float(t.open_rate),o['entry_limit'])
            if float(t.amount or 0)>0:
                book=self.dp.orderbook(t.pair,1);mark=max(mark,float(book['bids'][0][0]),float(book['asks'][0][0]))
            gross+=q*mark;risk+=q*risk_unit(o,float(t.open_rate))
        return gross,risk
    def custom_stake_amount(self,pair,current_time,current_rate,proposed_stake,min_stake,max_stake,leverage,entry_tag,side,**kwargs):
        try:
            if self.config.get('dry_run') is not True:return 0.
            o=decode(entry_tag);eq,trades=self._account(current_time)
            if not self._gate(eq,current_time) or not self._valid_setup(pair,o,current_time) or entry_tag in self._risk.get('consumed',[]):return 0.
            if len(trades)>=2 or planned_rr(o)<1:return 0.
            unit=risk_unit(o);q=math.floor((eq*.005/unit)*10**META[pair.split('/')[0]]['szDecimals'])/10**META[pair.split('/')[0]]['szDecimals']
            gross,openrisk=self._reserved(trades);notional=q*o['entry_limit'];stake=notional/leverage
            if q<=0 or notional<10 or stake>max_stake or stake<(min_stake or 0) or gross+notional>eq*2 or openrisk+q*unit>eq*.01+1e-9:return 0.
            return stake
        except Exception as e:log.warning('FVG sizing refused: %s',type(e).__name__);return 0.
    def confirm_trade_entry(self,pair,order_type,amount,rate,time_in_force,current_time,entry_tag,side,**kwargs):
        try:
            if self.config.get('dry_run') is not True or self.config.get('force_entry_enable') is not False or order_type!='limit' or time_in_force!='GTC':return False
            if not math.isfinite(amount) or not math.isfinite(rate) or amount<=0 or rate<=0 or amount*rate<10:return False
            o=decode(entry_tag);coin=pair.split('/')[0]
            if o['direction']!=(1 if side=='long' else -1) or abs(rate-o['entry_limit'])>tick(coin,rate)*.01:return False
            if not self._valid_setup(pair,o,current_time) or entry_tag in self._risk.get('consumed',[]) or planned_rr(o)<1:return False
            book=self.dp.orderbook(pair,1);bid=float(book['bids'][0][0]);ask=float(book['asks'][0][0])
            if not (math.isfinite(bid) and math.isfinite(ask) and 0<bid<=ask):return False
            if (rate>=ask if side=='long' else rate<=bid):return False
            eq,trades=self._account(current_time);gross,openrisk=self._reserved(trades);loss=amount*risk_unit(o,rate)
            if not self._gate(eq,current_time) or len(trades)>=2 or loss>eq*.005+1e-8 or gross+amount*rate>2*eq+1e-8 or openrisk+loss>eq*.01+1e-8:return False
            if o['direction']*(rate-o['stop'])/rate>=.2:return False
            self._risk.setdefault('consumed',[]).append(entry_tag);self._risk['consumed']=self._risk['consumed'][-2000:];self._save();return True
        except Exception as e:log.warning('FVG placement refused: %s',type(e).__name__);return False
    def check_entry_timeout(self,pair,trade,order,current_time,**kwargs):
        try:return not self._valid_setup(pair,decode(trade.enter_tag),current_time,pending=True)
        except Exception:return True
    def adjust_entry_price(self,trade,order,pair,current_time,proposed_rate,current_order_rate,entry_tag,side,**kwargs):return current_order_rate
    def custom_stoploss(self,pair,trade,current_time,current_rate,current_profit,after_fill=False,**kwargs):
        try:return stoploss_from_absolute(decode(trade.enter_tag)['stop'],current_rate,is_short=trade.is_short,leverage=trade.leverage)
        except Exception:return None
    def order_filled(self,pair,trade,order,current_time,**kwargs):
        o=decode(trade.enter_tag)
        if order.ft_order_side==trade.entry_side and float(order.filled or 0)>0:
            if trade.get_custom_data('fvg_fill_ms') is None:trade.set_custom_data('fvg_fill_ms',ms(order.order_filled_date or current_time))
            trade.set_custom_data('fvg_setup',o);trade.set_custom_data('fvg_initial_risk_USDC',float(trade.amount)*risk_unit(o,float(trade.open_rate)))
        elif not trade.is_open:self._journal(trade)
    def custom_roi(self,pair,trade,current_time,trade_duration,entry_tag,side,**kwargs):
        try:
            filled=trade.get_custom_data('fvg_fill_ms')
            if filled is None or ms(current_time)//60000<=filled//60000:return None
            return float(trade.calc_profit_ratio(decode(trade.enter_tag)['target']))
        except Exception:return None
    def custom_exit(self,pair,trade,current_time,current_rate,current_profit,**kwargs):
        try:
            o=decode(trade.enter_tag);filled=trade.get_custom_data('fvg_fill_ms')
            if filled is None:return 'fvg_missing_fill_metadata'
            if o['direction']*(current_rate-o['stop'])<=0 and (not trade.stop_loss or abs(trade.stop_loss-o['stop'])>tick(pair.split('/')[0],o['stop'])):return 'fvg_invalid_fill_stop'
            if ms(current_time)-filled>=96*STEP:return 'fvg_time_exit'
            return None
        except Exception:return 'fvg_missing_setup'
    def _journal(self,trade):
        if trade.is_open:return
        risk=trade.get_custom_data('fvg_initial_risk_USDC');net=trade.close_profit_abs
        record={'trade_id':trade.id,'scope':'FVG_FREQTRADE_DRY_RUN','strategy_version':self.version(),'pair':trade.pair,'net_USDC':net,'risk_USDC':risk,'net_R':net/risk if net is not None and risk else None,'exit_reason':trade.exit_reason,'outcome':'UNRESOLVED' if net is None else 'LOSS' if net<0 else 'WIN_OR_FLAT','cause_status':'NOT_ESTABLISHED','interpretation':'Observed exit and costs are facts; a loss alone does not establish a market cause or a strategy defect.','setup':decode(trade.enter_tag),'fill_ms':trade.get_custom_data('fvg_fill_ms'),'closed_ms':ms(trade.close_date_utc) if trade.close_date_utc else None}
        folder=self._risk_path.parent/'fvg-reviews';folder.mkdir(exist_ok=True);(folder/f'{trade.id}.json').write_text(json.dumps(record,indent=2))
