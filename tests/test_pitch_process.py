import sys,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pitch_process import PitchProcess

class PitchIsolationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  root=Path(self.tmp.name)
  self.env=patch.dict('os.environ',{'SOURCE_EXTRACTOR_DATA_DIR':str(root)});self.env.start();self.addCleanup(self.env.stop)
  script=root/'worker.py'
  script.write_text('''import sys,json,os
for line in sys.stdin:
 r=json.loads(line)
 if r['path']=='crash':os._exit(9)
 print(json.dumps({'points':[[r['start'],220]],'method':'FCPE'}),flush=True)
''')
  self.worker=PitchProcess([sys.executable,'-u',str(script)]);self.addCleanup(self.worker.close)
 def test_native_exit_is_contained_and_next_request_restarts(self):
  self.assertEqual(self.worker.analyze('ok',1,2)['points'],[[1,220]])
  with self.assertRaisesRegex(RuntimeError,'ピッチ|피치'):self.worker.analyze('crash',1,2)
  self.assertIsNone(self.worker.process)
  self.assertEqual(self.worker.analyze('ok',3,4)['points'],[[3,220]])
 def test_sequential_requests_reuse_worker(self):
  self.worker.analyze('ok',1,2);pid=self.worker.process.pid
  self.worker.analyze('ok',2,3);self.assertEqual(self.worker.process.pid,pid)

if __name__=='__main__':unittest.main()
