import pathlib,sys,tempfile,unittest,json
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from video_intake import register,POLICY
class IntakeTests(unittest.TestCase):
 def test_identical_upload_is_deduplicated_without_claiming_analysis(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d);a=p/'a.mp4';b=p/'b.mp4';a.write_bytes(b'test media');b.write_bytes(a.read_bytes())
   first=register(a,p/'db.sqlite');second=register(b,p/'db.sqlite')
   self.assertFalse(first['duplicate']);self.assertTrue(second['duplicate']);self.assertEqual(first['sha256'],second['sha256']);self.assertEqual(second['status'],'registered');self.assertFalse(second['execution_enabled'])
 def test_user_supplied_only_policy_never_implies_background_worker(self):
  policy=json.loads(POLICY.read_text());self.assertFalse(policy['autonomous_discovery']);self.assertTrue(policy['runtime_worker_implemented']);self.assertEqual(policy['executor'],'scheduled_agent');self.assertEqual(policy['execution_mode'],'dry_run')
