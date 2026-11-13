"""Historical-only port. Uses same detector and risk; OHLCV is not a book/queue."""
import bisect,json,math,pathlib,datetime as dt,collections
from XenonFVG import XenonFVG,decode,risk_unit,planned_rr,ms,FEE
from fvg_rules import tick,STEP,META
class XenonFVGBacktest(XenonFVG):
 def version(self):return 'xenon-fvg-backtest-1'
 def bot_start(self,**kwargs):
  mode=getattr(self.config.get('runmode'),'value',self.config.get('runmode'))
  historical=mode=='backtest' or (mode=='util_no_exchange' and self.config.get('xenon_lookahead_audit') is True)
  if not historical or self.config.get('dry_run') is not True or self.config.get('force_entry_enable') is not False:raise RuntimeError('Historical backtest only')
  if abs(float(self.config.get('fee',0))-FEE)>1e-12 and self.config.get('fee')!=2*FEE:raise RuntimeError('Frozen fee or explicit2x stress required')
  fixed=self.config.get('xenon_fixed_risk_USDC')
  if fixed is not None and (not math.isfinite(float(fixed)) or float(fixed)<=0):raise RuntimeError('Fixed historical risk must be positive and finite')
  self._fixed_risk=None if fixed is None else float(fixed);self._sizing=[]
  self._boot_ms=0;self._visual_enabled=False;self._risk={'consumed':[]};self._audit=collections.Counter();self._orders=[]
  data=json.loads(pathlib.Path(self.config['xenon_backtest_opens']).read_text());self._prices=data['prices'];self._price_times={p:[x[0] for x in r] for p,r in self._prices.items()};self._main={p:set(v) for p,v in data['main_times'].items()};self._price_step=data['price_step']
 def _save(self):
  destination=self.config.get('xenon_backtest_audit')
  if destination and hasattr(self,'_audit'):pathlib.Path(destination).write_text(json.dumps({'counts':dict(self._audit),'orders':self._orders,'risk_state':self._risk,'sizing':self._sizing},indent=2))
 def _budget(self,equity):return self._fixed_risk if self._fixed_risk is not None else equity*.005
 def _risk_cap(self,equity):return 2*self._fixed_risk if self._fixed_risk is not None else equity*.01
 def custom_stake_amount(self,pair,current_time,current_rate,proposed_stake,min_stake,max_stake,leverage,entry_tag,side,**kwargs):
  if self._fixed_risk is None:return super().custom_stake_amount(pair,current_time,current_rate,proposed_stake,min_stake,max_stake,leverage,entry_tag,side,**kwargs)
  try:
   o=decode(entry_tag);eq,trades=self._account(current_time);why=self._setup_block(pair,o,current_time)
   if why:self._note(pair,'entry_blocked',why,entry_tag);return 0.
   if not self._gate(eq,current_time):self._note(pair,'entry_blocked','risk_guard',entry_tag);return 0.
   if entry_tag in self._risk['consumed'] or len(trades)>=2 or planned_rr(o)<1:return 0.
   unit=risk_unit(o);scale=10**META[pair.split('/')[0]]['szDecimals'];q=math.floor(self._budget(eq)/unit*scale)/scale
   gross,openrisk=self._reserved(trades);notional=q*o['entry_limit'];stake=notional/leverage
   why='PASS'
   if q<=0 or notional<10 or stake<(min_stake or 0):why='minimum_order'
   elif stake>max_stake or gross+notional>2*eq:why='margin_or_2x_exposure'
   elif openrisk+q*unit>self._risk_cap(eq)+1e-8:why='open_risk_cap'
   self._sizing.append({'tag':entry_tag,'pair':pair,'time_ms':ms(current_time),'requested_risk_USDC':self._fixed_risk,'rounded_risk_USDC':q*unit,'equity_USDC':eq,'required_notional_USDC':notional,'required_margin_USDC':stake,'available_margin_USDC':max_stake,'minimum_gross_leverage':notional/eq,'decision':why})
   self._audit['fixed_sizing:'+why]+=1;self._save()
   return stake if why=='PASS' else 0.
  except Exception as e:self._audit['fixed_sizing_error:'+type(e).__name__]+=1;self._save();return 0.
 def _journal(self,trade):pass
 def _price(self,pair,now):
  t=ms(now);rows=self._prices[pair];i=bisect.bisect_right(self._price_times[pair],t)-1
  if i<0 or t-rows[i][0]>=self._price_step:raise ValueError('No observed price at simulation time')
  return float(rows[i][1])
 def populate_indicators(self,dataframe,metadata):
  pair=metadata['pair'];observed=dataframe.date.map(ms).isin(self._main[pair]);valid=super().populate_indicators(dataframe.loc[observed].copy(),metadata)
  result=dataframe.copy()
  for col in ('xenon_ema20','fvg_limit','fvg_stop','fvg_target','fvg_direction','fvg_tag'):result[col]=valid[col].reindex(result.index)
  result['fvg_direction']=result.fvg_direction.fillna(0);result['fvg_tag']=result.fvg_tag.fillna('');return result
 def _account(self,now):
  self._mark_time=now;trades=self._trades();equity=float(self.wallets.get_total(self.config['stake_currency']))
  for trade in trades:
   if trade.amount>0:equity+=float(trade.calc_profit_ratio(self._price(trade.pair,now)))*float(trade.stake_amount)
  if not math.isfinite(equity) or equity<=0:raise ValueError('Invalid equity')
  return equity,trades
 def _reserved(self,trades):
  gross=risk=0.
  for t in trades:
   o=decode(t.enter_tag);q=max(float(t.amount or 0),float(t.amount_requested or 0),float(t.stake_amount)*float(t.leverage)/float(t.open_rate));mark=max(float(t.open_rate),o['entry_limit'])

   if float(t.amount or 0)>0:mark=max(mark,self._price(t.pair,self._mark_time))
   gross+=q*mark;risk+=q*risk_unit(o,float(t.open_rate))
  return gross,risk
 def _note(self,pair,kind,reason,tag=None,extra=None):self._audit[kind+':'+reason]+=1
 def confirm_trade_entry(self,pair,order_type,amount,rate,time_in_force,current_time,entry_tag,side,**kwargs):
  try:
   if self.config.get('dry_run') is not True or order_type!='limit' or time_in_force!='GTC':self._audit['invalid_order_mode']+=1;return False
   o=decode(entry_tag);coin=pair.split('/')[0]
   if not math.isfinite(amount) or not math.isfinite(rate) or amount<=0 or amount*rate<10:self._audit['invalid_amount']+=1;return False
   if o['direction']!=(1 if side=='long' else -1) or abs(rate-o['entry_limit'])>tick(coin,rate)*.01:self._audit['clamped_or_wrong_side']+=1;return False
   if not self._valid_setup(pair,o,current_time) or entry_tag in self._risk['consumed'] or planned_rr(o)<1:self._audit['setup_or_duplicate_or_rr']+=1;return False
   opening=self._price(pair,current_time)
   if (rate>=opening if side=='long' else rate<=opening):self._audit['marketable_at_open_proxy']+=1;return False
   eq,trades=self._account(current_time);gross,openrisk=self._reserved(trades);loss=amount*risk_unit(o,rate)
   if not self._gate(eq,current_time) or len(trades)>=2 or loss>self._budget(eq)+1e-8 or gross+amount*rate>2*eq+1e-8 or openrisk+loss>self._risk_cap(eq)+1e-8:self._audit['final_risk_or_capacity']+=1;return False
   if o['direction']*(rate-o['stop'])/rate>=.2:self._audit['stop_distance']+=1;return False
   self._risk['consumed'].append(entry_tag);self._orders.append({'tag':entry_tag,'time_ms':ms(current_time),'amount':amount,'rate':rate,'planned_risk_USDC':loss,'equity_USDC':eq});self._save();return True
  except Exception as e:self._audit['placement_error:'+type(e).__name__]+=1;return False
 def order_filled(self,pair,trade,order,current_time,**kwargs):
  # LocalTrade is historical; suppress all forward-runtime journal writes.
  super().order_filled(pair,trade,order,current_time,**kwargs)
 def bot_cleanup(self,**kwargs):
  self._save()
