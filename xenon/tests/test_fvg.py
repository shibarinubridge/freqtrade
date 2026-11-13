import datetime as dt,math,pathlib,sys,tempfile,types,unittest
from unittest.mock import patch
from pandas import DataFrame,to_datetime
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'strategies'))
from XenonFVG import XenonFVG,encode,decode,risk_unit,planned_rr,STEP,FEE
from freqtrade.persistence import Trade

NOW=dt.datetime(2026,11,13,12,0,30,tzinfo=dt.timezone.utc)
T=int(NOW.timestamp()*1000)-30000
PAIR='BTC/USDC:USDC'
def setup(d=1):return {'coin':'BTC','direction':d,'signal_time':T,'entry_limit':100.,'stop':99. if d==1 else 101.,'target':103. if d==1 else 97.,'old_gap':{'lo':98.,'hi':98.5} if d==1 else {'lo':101.5,'hi':102.}}
def bars(extra=None):
 a=[{'date':to_datetime(T-STEP,unit='ms',utc=True),'open':101,'high':102,'low':100.5,'close':101.,'volume':10.}]
 return DataFrame(a+(extra or []))
class PortTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=XenonFVG({'dry_run':True,'force_entry_enable':False,'stake_currency':'USDC','fee':FEE});self.s._boot_ms=0;self.s._risk_path=pathlib.Path(self.tmp.name)/'risk.json';self.s._account=lambda now:(1000.,[])
  self.s.dp=types.SimpleNamespace(get_analyzed_dataframe=lambda *a:(bars(),None),orderbook=lambda *a:{'bids':[[101.,10]],'asks':[[101.1,10]]})
 def tearDown(self):self.tmp.cleanup()
 def confirm(self,o=None,amount=1.,rate=100.,side='long'):
  return self.s.confirm_trade_entry(PAIR,'limit',amount,rate,'GTC',NOW,encode(o or setup()),side)
 def test_tag_roundtrip_is_geometry_preserving_and_pair_bound(self):
  o=setup();r=decode(encode(o));self.assertEqual(r['entry_limit'],o['entry_limit']);self.assertEqual(r['coin'],'BTC');self.assertLess(len(encode(o)),255);self.assertFalse(self.s._valid_setup('ETH/USDC:USDC',r,NOW))
  for x in ['bad','XF1|BTC|1|0|nan|99|103|98|99']:
   with self.assertRaises(ValueError):decode(x)
 def test_confirm_refuses_clamp_marketable_stale_and_duplicate_setup(self):
  self.assertFalse(self.s.confirm_trade_entry(PAIR,'limit',1,100,'IOC',NOW,encode(setup()),'long'))
  self.assertFalse(self.confirm(rate=100.01));self.s.dp.orderbook=lambda *a:{'bids':[[99.,10]],'asks':[[99.1,10]]};self.assertFalse(self.confirm())
  self.s.dp.orderbook=lambda *a:{'bids':[[101.,10]],'asks':[[101.1,10]]};stale=setup();stale['signal_time']=T-180000;self.assertFalse(self.confirm(stale))
  self.assertTrue(self.confirm());self.assertFalse(self.confirm())
 def test_sizing_is_risk_budget_not_margin_and_final_quantity_cannot_exceed_budget(self):
  o=setup();tag=encode(o);stake=self.s.custom_stake_amount(PAIR,NOW,100,100,5,990,2,tag,'long');q=stake*2/100
  self.assertGreater(stake,0);self.assertLessEqual(q*risk_unit(o),5);self.assertFalse(self.confirm(amount=5/risk_unit(o)*1.05));self.assertTrue(self.confirm(amount=q))
 def test_pending_orders_reserve_risk_and_notional(self):
  t=types.SimpleNamespace(enter_tag=encode(setup()),amount=0.,amount_requested=4.,stake_amount=200.,leverage=2.,open_rate=100.)
  gross,risk=self.s._reserved([t]);self.assertEqual(gross,400);self.assertGreater(risk,4)
  self.s._account=lambda now:(1000.,[t,t]);self.assertEqual(self.s.custom_stake_amount(PAIR,NOW,100,100,5,990,2,encode(setup()),'long'),0)
 def test_existing_positions_reserve_current_marked_notional(self):
  t=types.SimpleNamespace(pair=PAIR,enter_tag=encode(setup()),amount=4.,amount_requested=4.,stake_amount=200.,leverage=2.,open_rate=100.)
  self.s.dp.orderbook=lambda *a:{'bids':[[129.,10]],'asks':[[130.,10]]}
  gross,risk=self.s._reserved([t]);self.assertEqual(gross,520);self.assertGreater(risk,4)
 def test_expiration_is_absolute_and_body_invalidation_uses_only_closed_candles(self):
  o=decode(encode(setup()));trade=types.SimpleNamespace(enter_tag=encode(setup()));expiry=dt.datetime.fromtimestamp(o['expires']/1000,dt.timezone.utc)
  self.assertFalse(self.s.check_entry_timeout(PAIR,trade,None,NOW));self.assertTrue(self.s.check_entry_timeout(PAIR,trade,None,expiry))
  x={'date':to_datetime(T,unit='ms',utc=True),'open':100,'high':101,'low':97,'close':97.9,'volume':10};self.s.dp.get_analyzed_dataframe=lambda *a:(bars([x]),None)
  self.assertTrue(self.s._valid_setup(PAIR,o,NOW,pending=True),'future/unclosed candle must not invalidate')
  self.assertFalse(self.s._valid_setup(PAIR,o,NOW+dt.timedelta(minutes=15),pending=True))
  self.assertEqual(self.s.adjust_entry_price(trade,None,PAIR,NOW,105,100,trade.enter_tag,'long'),100)
 def test_absolute_stop_and_roi_use_trade_leverage_fees_and_native_target(self):
  for direction in [1,-1]:
   o=setup(direction);trade=types.SimpleNamespace(enter_tag=encode(o),is_short=direction<0,leverage=2.,get_custom_data=lambda key: T-60000,calc_profit_ratio=lambda price:(price-100)*direction/50-.0018)
   self.assertAlmostEqual(self.s.custom_stoploss(PAIR,trade,NOW,100,0,True),.02)
   roi=self.s.custom_roi(PAIR,trade,NOW,10,trade.enter_tag,'short' if direction<0 else 'long');self.assertAlmostEqual(roi,trade.calc_profit_ratio(o['target']))
   trade.get_custom_data=lambda key:T;self.assertIsNone(self.s.custom_roi(PAIR,trade,NOW,0,trade.enter_tag,'long'))
 def test_stop_flag_precedes_target_roi_in_real_framework(self):
  o=setup();t=Trade(pair=PAIR,open_rate=100.,amount=1.,stake_amount=50.,leverage=2.,is_short=False,fee_open=FEE,fee_close=FEE,open_date=NOW-dt.timedelta(minutes=30),enter_tag=encode(o))
  t.get_custom_data=lambda key:T-60000;t.stop_loss=99.;t.initial_stop_loss=99.;self.s._ft_stop_uses_after_fill=True
  exits=self.s.should_exit(t,103.2,NOW,enter=False,exit_=False,low=98.,high=104.)
  reasons=[x.exit_type.value for x in exits];self.assertIn('roi',reasons);self.assertIn('stop_loss',reasons);self.assertLess(reasons.index('stop_loss'),reasons.index('roi'))
 def test_fill_clock_is_persisted_and_loss_journal_does_not_invent_causes(self):
  data={};o=setup();t=types.SimpleNamespace(id=7,enter_tag=encode(o),entry_side='buy',amount=2.,open_rate=100.,is_open=True,get_custom_data=lambda k:data.get(k),set_custom_data=lambda k,v:data.__setitem__(k,v))
  fill=NOW+dt.timedelta(minutes=20);order=types.SimpleNamespace(ft_order_side='buy',filled=2.,order_filled_date=fill)
  self.s.order_filled(PAIR,t,order,fill);self.s.order_filled(PAIR,t,order,fill+dt.timedelta(seconds=30));self.assertEqual(data['fvg_fill_ms'],int(fill.timestamp()*1000))
  t.stop_loss=99.;self.assertIsNone(self.s.custom_exit(PAIR,t,fill+dt.timedelta(hours=23),100,0));self.assertEqual(self.s.custom_exit(PAIR,t,fill+dt.timedelta(hours=24),100,0),'fvg_time_exit')
  t.is_open=False;t.close_profit_abs=-2.;t.exit_reason='stop_loss';t.close_date_utc=fill+dt.timedelta(hours=1);t.pair=PAIR;self.s._journal(t)
  import json
  record=json.loads((self.s._risk_path.parent/'fvg-reviews/7.json').read_text());self.assertEqual(record['outcome'],'LOSS');self.assertEqual(record['cause_status'],'NOT_ESTABLISHED');self.assertLess(record['net_R'],0)
 def test_missing_setup_and_runtime_failures_reject_entries(self):
  self.assertFalse(self.s.confirm_trade_entry(PAIR,'limit',1,100,'GTC',NOW,'malformed','long'))
  self.s._account=lambda t:(_ for _ in ()).throw(RuntimeError('offline'))
  self.assertEqual(self.s.custom_stake_amount(PAIR,NOW,100,100,5,990,2,encode(setup()),'long'),0);self.assertFalse(self.confirm())
 def test_guard_blocks_new_entries_after_daily_loss_or_drawdown(self):
  self.assertTrue(self.s._gate(1000,NOW));self.assertFalse(self.s._gate(984,NOW));self.assertFalse(self.s._gate(1000,NOW+dt.timedelta(minutes=1)))
  self.s._risk={};self.assertTrue(self.s._gate(1000,NOW));self.assertFalse(self.s._gate(974,NOW));self.assertTrue(self.s._risk['suspended'])

if __name__=='__main__':unittest.main()
