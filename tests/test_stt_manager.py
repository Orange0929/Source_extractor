import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from stt_manager import Manager

FAKE = '''import sys,json,time
for line in sys.stdin:
 r=json.loads(line)
 print(json.dumps({'type':'device','actual':{'device':'cpu','message':'test'}}),flush=True)
 if r.get('hang'): time.sleep(100)
 print(json.dumps({'type':'progress','job':{'status':'running','progress':50}}),flush=True)
 print(json.dumps({'type':'result','result':{'status':'done','message':'ok','clips':[{'text':'hello'}]}}),flush=True)
'''

class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)
  self.worker=self.root/'worker.py';self.worker.write_text(FAKE)
  self.manager=Manager(self.root,[sys.executable,'-u',str(self.worker)])
  self.addCleanup(self.manager.close)
 def wait(self,predicate):
  deadline=time.monotonic()+5
  while not predicate():
   if time.monotonic()>deadline:self.fail('timeout')
   time.sleep(.01)
 def test_pause_preserves_queue_and_resume(self):
  m=self.manager;m.pause();result=[]
  future=m.submit(lambda:result.append(1))
  time.sleep(.05);self.assertEqual(result,[]);self.assertEqual(m.status()['waiting'],1)
  m.resume();future.result(3);self.assertEqual(result,[1])
 def test_pause_waits_for_current_file(self):
  m=self.manager;started=threading.Event();finish=threading.Event()
  f=m.submit(lambda:(started.set(),finish.wait(3)));self.assertTrue(started.wait(3))
  m.pause();next_file=m.submit(lambda:123);finish.set();f.result(3)
  self.assertFalse(next_file.done());m.resume();self.assertEqual(next_file.result(3),123)
 def test_settings_persist_and_validate(self):
  m=self.manager;m.configure({'device':'cpu','performance':'eco','threads':1});m.pause()
  other=Manager(self.root);self.addCleanup(other.close)
  self.assertTrue(other.paused);self.assertEqual(other.settings['threads'],1)
  with self.assertRaises(ValueError):m.configure({'device':'invalid'})
  with self.assertRaises(ValueError):m.configure({'threads':-1})
 def test_process_reused_and_progress_delivered(self):
  m=self.manager;events=[]
  r=m.run({},threading.Event(),events.append);pid=m.process.pid
  self.assertEqual(r['status'],'done');self.assertEqual(events[0]['progress'],50)
  m.run({},threading.Event(),events.append);self.assertEqual(m.process.pid,pid)
 def test_immediate_cancel_kills_worker_without_results(self):
  m=self.manager;cancel=threading.Event()
  future=m.submit(lambda:m.run({'hang':True},cancel,lambda _:None))
  self.wait(lambda:m.status()['actual'].get('device')=='cpu');process=m.process
  cancel.set();r=future.result(5)
  self.assertEqual(r['status'],'cancelled');self.assertEqual(r['clips'],[])
  self.assertIsNotNone(process.poll());self.assertIsNone(m.process)
 def test_cancelled_future_never_runs(self):
  m=self.manager;m.pause();called=[];f=m.submit(lambda:called.append(1))
  self.assertTrue(f.cancel());m.resume();time.sleep(.05);self.assertEqual(called,[])
 def test_worker_crash_surfaces_error(self):
  self.worker.write_text('raise RuntimeError("boom")')
  with self.assertRaisesRegex(RuntimeError,'stt_worker.log'):
   self.manager.run({},threading.Event(),lambda _:None)


class WorkerTests(unittest.TestCase):
 def exercise(self, device, fail_gpu=False):
  import io
  import types
  from unittest.mock import patch
  import stt_worker
  calls=[];models=[]
  core=types.SimpleNamespace(WHISPER_MODEL_NAME='small')
  def model(*args,**kw):models.append(kw);return object()
  def run(job,profile,audio,path):
   calls.append(models[-1]['device'])
   core.set_job(job,status='running',progress=10)
   if fail_gpu and models[-1]['device']=='cuda':
    core.set_job(job,status='error',message='missing CUDA library');return
   core.save_data({'clips':[{'transcript':'hello'}]})
   core.set_job(job,status='done',message='ok')
  request=dict(settings=dict(device=device,performance='eco',threads=1),job_id='j',profile_id='p',audio_id='a',path='a.wav')
  output=io.StringIO()
  with patch.dict(sys.modules,{'app':core,'app_fixed':types.SimpleNamespace(run_stt_job_fixed=run),'ctranslate2':types.SimpleNamespace(get_cuda_device_count=lambda:1),'faster_whisper':types.SimpleNamespace(WhisperModel=model)}),patch('sys.stdin',io.StringIO(json.dumps(request)+'\n')),patch('sys.stdout',output):
   stt_worker.main()
  return calls,[json.loads(line) for line in output.getvalue().splitlines()]
 def test_auto_gpu_failure_retries_cpu_without_terminal_progress(self):
  calls,messages=self.exercise('auto',True)
  self.assertEqual(calls,['cuda','cpu'])
  self.assertEqual(messages[-1]['result']['status'],'done')
  self.assertFalse(any(m['type']=='progress' and m['job'].get('status')=='error' for m in messages))
 def test_explicit_gpu_failure_is_reported_without_silent_fallback(self):
  calls,messages=self.exercise('cuda',True)
  self.assertEqual(calls,['cuda']);self.assertEqual(messages[-1]['result']['status'],'error')
 def test_cpu_complete_result(self):
  calls,messages=self.exercise('cpu')
  self.assertEqual(calls,['cpu']);self.assertEqual(len(messages[-1]['result']['clips']),1)

class IntegrationTests(unittest.TestCase):
 def setUp(self):
  import types,copy
  from stt_manager import install
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  root=Path(self.tmp.name)
  class Routes:
   routes=[]
   def __init__(self):self.handlers={}
   def get(self,path):return self.register(path)
   def post(self,path):return self.register(path)
   def on_event(self,path):return self.register(path)
   def register(self,path):
    def decorate(fn):self.handlers[path]=fn;return fn
    return decorate
  self.data={'audios':[dict(id='a',profile_id='p',path='a.wav',stt_status='running')], 'clips':[]}
  (root/'a.wav').write_bytes(b'audio')
  self.core=types.SimpleNamespace(DATA_DIR=root,UPLOAD_DIR=root,DATA_LOCK=threading.Lock(),JOBS_LOCK=threading.Lock(),
   JOBS={},EXECUTOR=types.SimpleNamespace(shutdown=lambda **_:None),app=Routes(),audit=lambda *a,**kw:None,
   api_cancel_job=lambda _:None,HTTPException=ValueError)
  c=self.core
  c.load_data=lambda:copy.deepcopy(self.data)
  def save(data):self.data=copy.deepcopy(data)
  c.save_data=save
  c.set_job=lambda job_id,**kw:c.JOBS.setdefault(job_id,{}).update(kw)
  c.get_job=lambda job_id:c.JOBS.get(job_id)
  def event(job_id):return c.JOBS.setdefault(job_id,{}).setdefault('_cancel_event',threading.Event())
  c._get_cancel_event=event
  self.submitted=[];c.submit_audio_job=lambda audio:self.submitted.append(audio['id'])
  install(c);self.addCleanup(c.STT_MANAGER.close)
 def test_recovery_pauses_and_restores_only_unfinished(self):
  self.data['audios'].append(dict(id='b',path='b.wav',stt_status='done'))
  self.core.app.handlers['startup']()
  self.assertEqual(self.submitted,['a']);self.assertTrue(self.core.STT_MANAGER.paused)
 def test_stop_persists_queued_cancel_and_keeps_completed_clips(self):
  c=self.core;c.STT_MANAGER.pause()
  c.JOBS['q']=dict(status='queued',audio_id='a',_future=c.STT_MANAGER.submit(lambda:None))
  self.data['clips']=[{'id':'manual','audio_id':'other'}]
  c.app.handlers['/api/stt/control/{action}']('stop')
  self.assertEqual(self.data['audios'][0]['stt_status'],'cancelled')
  self.assertEqual(len(self.data['clips']),1)
 def test_commit_deduplicates_and_preserves_manual_edits(self):
  c=self.core
  c.STT_MANAGER.run=lambda *args:{'status':'done','message':'ok','clips':[dict(id='new',audio_id='a')]}
  c.run_stt_job('j','p','a',Path('a.wav'))
  self.assertEqual(self.data['clips'][0]['id'],'new')
  self.data['clips'][0]['transcript']='manual correction'
  c.run_stt_job('j2','p','a',Path('a.wav'))
  self.assertEqual(len(self.data['clips']),1);self.assertEqual(self.data['clips'][0]['transcript'],'manual correction')
 def test_cancelled_partial_results_are_never_saved(self):
  c=self.core
  c.STT_MANAGER.run=lambda *args:{'status':'cancelled','message':'cancel','clips':[dict(id='partial')]}
  c.run_stt_job('j','p','a',Path('a.wav'))
  self.assertEqual(self.data['clips'],[])
 def test_result_uses_current_profile_owner(self):
  c=self.core;self.data['audios'][0]['profile_id']='moved'
  c.STT_MANAGER.run=lambda *args:{'status':'done','message':'ok','clips':[dict(id='new',audio_id='a',profile_id='p')]}
  c.run_stt_job('j','p','a',Path('a.wav'))
  self.assertEqual(self.data['clips'][0]['profile_id'],'moved')

if __name__=='__main__':unittest.main()
