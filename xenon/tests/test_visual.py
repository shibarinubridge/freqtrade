import importlib.util,json,pathlib,sys,tempfile,unittest
from unittest.mock import patch
P=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(P/'strategies'))
from fvg_rules import detect,STEP
import fvg_visual
from XenonFVG import XenonFVG
class VisualTests(unittest.TestCase):
 def test_visual_export_is_disabled_for_fixtures_and_research(self):
  s=XenonFVG({'dry_run':True});self.assertFalse(s._visual_enabled)
  with patch('XenonFVG.visual_decision') as note:s._note('BTC/USDC:USDC','placement_authorized','await_broker_order_id');note.assert_not_called()
 def test_publish_observed_time_survives_and_preboot_is_reconstruction(self):
  view={'coin':'BTC','confirmed_ms':200,'events':[{'id':'a','available_ms':100},{'id':'b','available_ms':300}]}
  with tempfile.TemporaryDirectory() as d,patch.object(fvg_visual,'ROOT',pathlib.Path(d)),patch('fvg_visual.time.time',return_value=1):
   fvg_visual.publish('BTC',view,[],200,'v');first=json.loads((pathlib.Path(d)/'BTC.json').read_text());self.assertEqual(first['events'][0]['origin'],'historical_reconstruction');self.assertEqual(first['events'][1]['origin'],'strategy_observation')
   with patch('fvg_visual.time.time',return_value=2):fvg_visual.publish('BTC',view,[],200,'v')
   second=json.loads((pathlib.Path(d)/'BTC.json').read_text());self.assertEqual(first['events'][0]['observed_ms'],second['events'][0]['observed_ms']);self.assertEqual(view['events'][0],{'id':'a','available_ms':100})
 def test_approval_is_observation_not_order_sent(self):
  with tempfile.TemporaryDirectory() as d,patch.object(fvg_visual,'ROOT',pathlib.Path(d)):
   fvg_visual.decision('BTC/USDC:USDC','placement_authorized','await_broker_order_id')
   fvg_visual.decision('BTC/USDC:USDC','placement_authorized','await_broker_order_id')
   out=json.loads((pathlib.Path(d)/'BTC-decisions.json').read_text());self.assertEqual(len(out),1);self.assertNotIn('order_id',out[0]);self.assertEqual(out[0]['kind'],'placement_authorized')
 def test_trace_is_optional_and_does_not_change_detector_output(self):
  rows=[{'t':i*STEP,'end':(i+1)*STEP,'o':100+(i%7),'h':103+(i%7),'l':97+(i%7),'c':101+(i%7),'v':1} for i in range(120)]
  plain=detect('BTC',rows);traced=detect('BTC',rows,trace=True);self.assertEqual(plain,traced[:2]);self.assertEqual(traced[2]['confirmed_ms'],120*STEP)
if __name__=='__main__':unittest.main()
