import sys,pathlib,tempfile,json,unittest,datetime as dt,types
from unittest.mock import patch
from freqtrade.enums import RunMode
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'strategies'))
from XenonFVGBacktest import XenonFVGBacktest
from XenonFVG import FEE,encode
from test_fvg import NOW,T,PAIR,setup,bars
class BacktestTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(self.tmp.name);self.opens=p/'opens.json';self.opens.write_text(json.dumps({'prices':{PAIR:[[T,101],[T+60000,99999]]},'main_times':{PAIR:[T-900000]},'price_step':60000}));self.s=XenonFVGBacktest({'runmode':RunMode.BACKTEST,'dry_run':True,'force_entry_enable':False,'fee':FEE,'stake_currency':'USDC','xenon_backtest_opens':str(self.opens)});self.s.bot_start();self.s.dp=types.SimpleNamespace(get_analyzed_dataframe=lambda *a:(bars(),None),orderbook=lambda *a:(_ for _ in ()).throw(AssertionError('Live book accessed')));self.s.wallets=types.SimpleNamespace(get_total=lambda c:1000);self.s._trades=lambda:[]
 def tearDown(self):self.tmp.cleanup()
 def test_forward_mode_is_refused(self):
  self.s.config['runmode']=RunMode.DRY_RUN
  with self.assertRaises(RuntimeError):self.s.bot_start()
 def test_current_open_proxy_never_reads_future_candle(self):
  self.assertEqual(self.s._price(PAIR,NOW),101);self.assertEqual(self.s._price(PAIR,dt.datetime.fromtimestamp((T+60000)/1000,dt.timezone.utc)),99999)
 def test_native_geometry_and_risk_accept_valid_limit_without_book(self):
  tag=encode(setup());stake=self.s.custom_stake_amount(PAIR,NOW,100,100,5,990,2,tag,'long');q=stake*2/100;self.assertGreater(q,0);self.assertTrue(self.s.confirm_trade_entry(PAIR,'limit',q,100,'GTC',NOW,tag,'long'));self.assertFalse(self.s.confirm_trade_entry(PAIR,'limit',q,100,'GTC',NOW,tag,'long'))
 def test_clamped_entry_and_marketable_proxy_are_refused(self):
  tag=encode(setup());self.assertFalse(self.s.confirm_trade_entry(PAIR,'limit',1,100.01,'GTC',NOW,tag,'long'));self.s._prices[PAIR][0][1]=99;self.assertFalse(self.s.confirm_trade_entry(PAIR,'limit',1,100,'GTC',NOW,tag,'long'))
 def test_no_forward_runtime_writes(self):
  with patch('pathlib.Path.write_text') as write:self.s._save();self.s._journal(types.SimpleNamespace());write.assert_not_called()
 def test_fixed_200_risk_is_not_silently_reduced_to_fit_margin(self):
  self.s._fixed_risk=200
  stake=self.s.custom_stake_amount(PAIR,NOW,100,100,5,990,2,encode(setup()),'long')
  self.assertEqual(stake,0);self.assertEqual(self.s._sizing[-1]['decision'],'margin_or_2x_exposure');self.assertGreater(self.s._sizing[-1]['required_margin_USDC'],990)
 def test_fixed_risk_sizes_at_200_when_account_can_support_it(self):
  self.s._fixed_risk=200;self.s.wallets.get_total=lambda c:100000
  tag=encode(setup());stake=self.s.custom_stake_amount(PAIR,NOW,100,100,5,99000,2,tag,'long')
  self.assertGreater(stake,0);self.assertLessEqual(self.s._sizing[-1]['rounded_risk_USDC'],200)
  self.assertTrue(self.s.confirm_trade_entry(PAIR,'limit',stake*2/100,100,'GTC',NOW,tag,'long'))
 def test_fixed_risk_keeps_original_loss_guard(self):
  self.s._fixed_risk=200;self.assertTrue(self.s._gate(1000,NOW));self.assertFalse(self.s._gate(800,NOW))
