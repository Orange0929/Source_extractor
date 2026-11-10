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

if __name__=='__main__':unittest.main()
