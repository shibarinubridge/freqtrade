import json,pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import research_loop as r
class ResearchTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.p=pathlib.Path(self.tmp.name);self.db=self.p/'db';self.video=self.p/'video.mp4';self.video.write_bytes(b'fixture');self.item=r.enqueue(self.video,self.db)
 def tearDown(self):self.tmp.cleanup()
 def test_claim_is_exclusive_and_stale_lease_can_be_recovered(self):
  a=r.claim(self.db,now=100);self.assertIsNone(r.claim(self.db,now=101));b=r.claim(self.db,now=3600101);self.assertNotEqual(a['token'],b['token'])
 def test_source_rules_and_unknowns_are_preserved_without_execution(self):
  a=r.claim(self.db);f=self.p/'analysis.json';f.write_text(json.dumps({'source_sha256':self.item['sha256'],'source_rules':[{'text':'retest','start_s':1,'end_s':2}],'assumptions':[],'unresolved':['stop unspecified'],'evidence':[]}));self.assertEqual(r.finish(a['sha'],a['token'],f,self.db)['state'],'blocked_rules')
  with self.assertRaises(ValueError):r.finish(a['sha'],a['token'],f,self.db)
 def test_evaluation_cannot_reuse_validation_or_call_it_development(self):
  result={'development_id':'train','validation_id':'holdout','data_sha256':'abc','variant_id':'baseline','net_after_costs':-1,'stress_net':-2,'trade_count':5,'lookahead_pass':True,'native_lifecycle_pass':False};f=self.p/'evaluation.json';f.write_text(json.dumps(result));r.record_experiment(self.item['sha256'],'baseline',f,db_path=self.db)
  with self.assertRaises(ValueError):r.record_experiment(self.item['sha256'],'retry',f,db_path=self.db)
  result['validation_id']='train';f.write_text(json.dumps(result))
  with self.assertRaises(ValueError):r.record_experiment(self.item['sha256'],'leak',f,db_path=self.db)
