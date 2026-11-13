"""Explicitly armed, bounded DRY-RUN integration test. Never a trading strategy."""
import datetime as dt,json,pathlib
from freqtrade.strategy import IStrategy
from freqtrade.persistence import Trade
class XenonDiagnostic(IStrategy):
 INTERFACE_VERSION=3;timeframe='1m';startup_candle_count=30;process_only_new_candles=False;can_short=True
 minimal_roi={};stoploss=-.02;use_exit_signal=True
 order_types={'entry':'market','exit':'market','stoploss':'market','stoploss_on_exchange':False}
 def bot_start(self,**kwargs):
  if self.config.get('dry_run') is not True or self.config.get('force_entry_enable') is not False or self.config.get('xenon_account_id')!='diagnostic':raise RuntimeError('Diagnostic dry-run account required')
  self.root=pathlib.Path(self.config['xenon_runtime_dir'])
 def arm(self):
  try:
   a=json.loads((self.root/'arm.json').read_text())
   if not 1<=a['count']<=2 or dt.datetime.now(dt.timezone.utc).timestamp()*1000>=a['deadline_ms']:return None
   if len(Trade.get_trades_proxy(is_open=False))>=a['baseline_closed']+a['count']:return None
   return a
  except (OSError,ValueError,KeyError):return None
 def populate_indicators(self,dataframe,metadata):return dataframe
 def populate_entry_trend(self,dataframe,metadata):
  dataframe['enter_long']=0;dataframe['enter_short']=0;dataframe['enter_tag']='DIAGNOSTIC_ONLY'
  a=self.arm()
  if a and metadata['pair']=='BTC/USDC:USDC':
   n=len(Trade.get_trades_proxy(is_open=False))-a['baseline_closed'];dataframe.loc[dataframe.index[-1],'enter_short' if n%2 else 'enter_long']=1
  return dataframe
 def populate_exit_trend(self,dataframe,metadata):dataframe['exit_long']=0;dataframe['exit_short']=0;return dataframe
 def confirm_trade_entry(self,pair,order_type,amount,rate,**kwargs):return bool(self.arm()) and pair=='BTC/USDC:USDC' and order_type=='market' and 0<amount*rate<=25
 def leverage(self,**kwargs):return 1.
 def custom_stake_amount(self,max_stake,**kwargs):return min(20.,max_stake)
 def custom_exit(self,trade,current_time,**kwargs):
  if (current_time-trade.open_date_utc).total_seconds()>=45:return 'diagnostic_timed_exit'
