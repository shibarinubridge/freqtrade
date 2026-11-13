import json,pathlib,sys,tempfile,time,unittest
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from native_ui_relay import Relay,allowed
from adapter import ModeError

class NativeRelayTests(unittest.TestCase):
 def test_only_local_monitoring_and_limited_controls_are_allowed(self):
  for p in ['profit','pair_candles?pair=BTC%2FUSDC%3AUSDC&limit=100','strategy/XenonObserve']:self.assertTrue(allowed('GET',p))
  for p in ['http://evil.test','../config','//evil.test','show_config?url=http://evil.test']:self.assertFalse(allowed('GET',p))
  for p in ['forceentry','forceexit','reload_config','trades/1']:self.assertFalse(allowed('POST',p))
 def test_expired_and_unverified_jobs_never_reach_the_local_api(self):
  with tempfile.TemporaryDirectory() as d:
   r=Relay(ledger=pathlib.Path(d)/'test.db');job={'id':'a','method':'POST','path':'start','deadline_ms':0};self.assertEqual(r.execute(job)['status'],504)
   job['deadline_ms']=int(time.time()*1000)+10000
   with patch.object(r.client,'config',side_effect=ModeError()):self.assertEqual(r.execute(job)['status'],503)
 def test_post_receipt_prevents_repeating_mutation_and_authentication_is_redacted(self):
  with tempfile.TemporaryDirectory() as d:
   auth=pathlib.Path(d)/'auth.json';auth.write_text(json.dumps({'username':'xenon','password':'example-password-do-not-export'}));r=Relay(auth,ledger=pathlib.Path(d)/'test.db');job={'id':'native-command','method':'POST','path':'pause','body':{},'deadline_ms':int(time.time()*1000)+10000}
   response=MagicMock();response.status=200;response.read.return_value=b'{"status":"paused","debug":"example-password-do-not-export"}';opener=MagicMock();opener.open.return_value.__enter__.return_value=response
   with patch.object(r.client,'config',return_value={'dry_run':True}),patch('urllib.request.build_opener',return_value=opener):
    one=r.execute(job);two=r.execute(job)
   self.assertEqual(one,two);self.assertEqual(opener.open.call_count,1);self.assertNotIn('example-password-do-not-export',json.dumps(one))
if __name__=='__main__':unittest.main()
