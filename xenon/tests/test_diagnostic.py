import datetime as dt,json,pathlib,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'strategies'))
from XenonDiagnostic import XenonDiagnostic
from pandas import DataFrame
class DiagnosticTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);self.s=XenonDiagnostic({'dry_run':True,'force_entry_enable':False,'xenon_account_id':'diagnostic','xenon_runtime_dir':str(self.root)});self.s.bot_start()
 def tearDown(self):self.tmp.cleanup()
 def test_wrong_mode_or_account_refuses_start(self):
  for cfg in [{'dry_run':False},{'force_entry_enable':True},{'xenon_account_id':'fvg'}]:
   s=XenonDiagnostic(self.s.config|cfg)
   with self.assertRaises(RuntimeError):s.bot_start()
 def test_missing_or_expired_arm_cannot_signal(self):
  with patch('XenonDiagnostic.Trade.get_trades_proxy',return_value=[]):
   self.assertIsNone(self.s.arm());(self.root/'arm.json').write_text(json.dumps({'count':2,'baseline_closed':0,'deadline_ms':1}));self.assertIsNone(self.s.arm())
 def test_two_trade_bound_and_long_short_sequence(self):
  (self.root/'arm.json').write_text(json.dumps({'count':2,'baseline_closed':0,'deadline_ms':9999999999999}))
  for n in [0,1,2]:
   with patch('XenonDiagnostic.Trade.get_trades_proxy',return_value=[None]*n):
    d=self.s.populate_entry_trend(DataFrame({'close':[1.]}),{'pair':'BTC/USDC:USDC'})
    self.assertEqual(int(d.enter_long.iloc[-1]),int(n==0));self.assertEqual(int(d.enter_short.iloc[-1]),int(n==1))
 def test_exit_clock_and_stake_cap(self):
  from types import SimpleNamespace
  now=dt.datetime.now(dt.timezone.utc);t=SimpleNamespace(open_date_utc=now)
  self.assertIsNone(self.s.custom_exit(t,now+dt.timedelta(seconds=44)));self.assertEqual(self.s.custom_exit(t,now+dt.timedelta(seconds=45)),'diagnostic_timed_exit');self.assertEqual(self.s.custom_stake_amount(1000),20)
