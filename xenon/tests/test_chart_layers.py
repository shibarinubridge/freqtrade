import unittest,sys,pathlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from chart_layers import build,STEP
class LayerTests(unittest.TestCase):
 def bars(self):return [{'t':i*STEP,'o':o,'h':h,'l':l,'c':c,'v':1} for i,(o,h,l,c) in enumerate([(9,10,8,9),(10,13,9,12),(12,14,11,13),(10,10.5,8,9)])]
 def test_fvg_only_exists_after_third_candle_and_invalidation_after_close(self):
  rows=self.bars();a=build('TEST',rows,3*STEP-1);self.assertFalse(a['zones']);b=build('TEST',rows,3*STEP);self.assertEqual(b['zones'][0]['known_ms'],3*STEP);self.assertEqual(b['zones'][0]['status'],'active');c=build('TEST',rows,4*STEP);self.assertEqual(c['zones'][0]['status'],'invalidated');self.assertEqual(c['zones'][0]['end_ms'],4*STEP)
 def test_forming_bar_cannot_change_structure(self):
  rows=self.bars();a=build('TEST',rows,3*STEP+20);rows[-1]['c']=100000;rows[-1]['h']=100001;b=build('TEST',rows,3*STEP+20);self.assertEqual(a,b)
 def test_missing_annual_data_is_not_zero_poc(self):
  q=build('TEST',self.bars(),4*STEP);self.assertEqual(q['poc']['status'],'unavailable');self.assertNotIn('price',q['poc'])
