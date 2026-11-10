import os
from pathlib import Path
import tempfile
import threading
import types
import unittest
from unittest.mock import patch
from stt_gpu_runtime import Installer,activate

class RuntimeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)
  self.manager=types.SimpleNamespace(cv=threading.RLock(),current=None,pause=lambda:None)
  self.inventory=types.SimpleNamespace(lock=threading.Lock(),cached={'old':1},expires=100)
  self.installer=Installer(self.root,self.manager,self.inventory);self.addCleanup(self.installer.close)
  download=patch.object(self.installer,'_download_wheels',return_value=['runtime.whl']);download.start();self.addCleanup(download.stop)
 def fake_process(self,command,**kwargs):
  self.command=command
  stage=Path(command[command.index('--target')+1]);folder=stage/'nvidia'/'test'/'bin';folder.mkdir(parents=True)
  for name in ('cublas64_12.dll','cudnn64_9.dll','cudart64_12.dll'):(folder/name).write_bytes(b'dll')
  return types.SimpleNamespace(wait=lambda **_:0,poll=lambda:0)
 def test_isolated_install_does_not_modify_existing_python_packages(self):
  self.installer.target.mkdir(parents=True);(self.installer.target/'old').write_text('old')
  with patch('stt_gpu_runtime.subprocess.Popen',side_effect=self.fake_process):self.installer._install()
  self.assertEqual(self.installer.status()['phase'],'done')
  self.assertIn('--no-deps',self.command);self.assertIn('--isolated',self.command)
  self.assertNotIn('torch',' '.join(self.command));self.assertTrue((self.installer.target/'manifest.json').is_file())
  self.assertIsNone(self.inventory.cached)
 def test_failure_preserves_existing_runtime(self):
  self.installer.target.mkdir(parents=True);(self.installer.target/'old').write_text('old')
  with patch('stt_gpu_runtime.subprocess.Popen',side_effect=OSError('offline')):self.installer._install()
  self.assertEqual(self.installer.status()['phase'],'error');self.assertEqual((self.installer.target/'old').read_text(),'old')
 def test_busy_file_rejects_install(self):
  self.manager.current=object()
  with patch('stt_gpu_runtime.SUPPORTED',True):
   with self.assertRaisesRegex(ValueError,'현재 파일'):self.installer.start()
 def test_dll_directories_are_child_environment_only(self):
  folder=self.root/'nvidia'/'cublas'/'bin';folder.mkdir(parents=True);(folder/'cublas64_12.dll').write_bytes(b'dll')
  with patch.dict(os.environ,{'SOURCE_EXTRACTOR_GPU_RUNTIME':str(self.root),'PATH':'original'}):
   self.assertIn(str(folder),activate());self.assertTrue(os.environ['PATH'].startswith(str(folder)))

 def test_install_releases_only_its_own_pause(self):
  from stt_manager import Manager
  manager=Manager(self.root);self.addCleanup(manager.close)
  self.installer.manager=manager
  manager.pause();self.installer.pause_hold=(False,manager.pause_revision)
  with patch('stt_gpu_runtime.subprocess.Popen',side_effect=self.fake_process):self.installer._install()
  self.assertFalse(manager.paused)
 def test_explicit_pause_during_install_is_preserved(self):
  from stt_manager import Manager
  manager=Manager(self.root);self.addCleanup(manager.close)
  self.installer.manager=manager
  manager.pause();self.installer.pause_hold=(False,manager.pause_revision)
  manager.pause()  # A separate user action after the install hold.
  with patch('stt_gpu_runtime.subprocess.Popen',side_effect=self.fake_process):self.installer._install()
  self.assertTrue(manager.paused)
 def test_install_failure_also_releases_temporary_pause(self):
  from stt_manager import Manager
  manager=Manager(self.root);self.addCleanup(manager.close)
  self.installer.manager=manager
  manager.pause();self.installer.pause_hold=(False,manager.pause_revision)
  with patch('stt_gpu_runtime.subprocess.Popen',side_effect=OSError('offline')):self.installer._install()
  self.assertEqual(self.installer.status()['phase'],'error');self.assertFalse(manager.paused)

class DownloadTests(unittest.TestCase):
 def test_combined_bytes_and_hash_verification(self):
  import io,json,hashlib
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);installer=Installer(root,None,None)
   self.addCleanup(installer.close)
   content=b'x'*(600*1024)
   def response(url,**kw):
    if url.endswith('/json'):
     name=url.split('/')[-3].replace('-','_')
     value={'urls':[{'filename':name+'-1-py3-none-win_amd64.whl','url':'https://files.pythonhosted.org/'+name,'size':len(content),'digests':{'sha256':hashlib.sha256(content).hexdigest()}}]}
     return io.BytesIO(json.dumps(value).encode())
    return io.BytesIO(content)
   snapshots=[]
   update=installer._update
   def track(**fields):update(**fields);snapshots.append(installer.status())
   with patch('stt_gpu_runtime.urllib.request.urlopen',side_effect=response),patch.object(installer,'_update',side_effect=track):
    paths=installer._download_wheels(root)
   self.assertEqual(len(paths),3)
   self.assertEqual(installer.status()['downloaded_bytes'],3*len(content))
   self.assertEqual(installer.status()['total_bytes'],3*len(content))
   progress=[s['downloaded_bytes'] for s in snapshots]
   self.assertEqual(progress,sorted(progress));self.assertGreater(len(progress),3)
 def test_hash_failure_never_promotes_download(self):
  import io,json
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);installer=Installer(root,None,None);self.addCleanup(installer.close)
   metadata={'urls':[{'filename':'test-1-py3-none-win_amd64.whl','url':'https://files.pythonhosted.org/test','size':3,'digests':{'sha256':'bad'}}]}
   def response(url,**kw):return io.BytesIO(json.dumps(metadata).encode() if url.endswith('/json') else b'bad')
   with patch('stt_gpu_runtime.urllib.request.urlopen',side_effect=response):
    with self.assertRaisesRegex(RuntimeError,'검증 실패'):installer._download_wheels(root)
   self.assertFalse(list(root.glob('*.whl')))

if __name__=='__main__':unittest.main()
