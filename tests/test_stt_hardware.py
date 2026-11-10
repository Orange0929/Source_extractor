import json
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import stt_hardware as hw

class HardwareTests(unittest.TestCase):
 def probe(self,loader):
  module=types.SimpleNamespace(get_cuda_device_count=lambda:2,get_supported_compute_types=lambda *a,**kw:{'float16','float32'})
  with patch.dict(sys.modules,{'ctranslate2':module}),patch.object(hw.shutil,'which',return_value='nvidia-smi'),patch.object(hw.subprocess,'check_output',return_value='0, NVIDIA Test 0\n1, NVIDIA Test 1\n'),patch.object(hw.ctypes,'CDLL',side_effect=loader):
   return hw.gpu_probe()
 def test_named_gpus_with_ready_runtime(self):
  result=self.probe(lambda _:object())
  self.assertEqual([g['name'] for g in result['gpus']],['NVIDIA Test 0','NVIDIA Test 1'])
  self.assertTrue(all(g['ready'] for g in result['gpus']))
 def test_detected_gpu_without_runtime_is_not_advertised_ready(self):
  def fail(_):raise OSError('missing cudnn')
  result=self.probe(fail)
  self.assertEqual(len(result['gpus']),2)
  self.assertFalse(result['gpus'][0]['ready']);self.assertIn('missing cudnn',result['gpus'][0]['reason'])
 def test_timeout_preserves_cpu_and_is_cached(self):
  inventory=hw.Inventory()
  with patch.object(hw.subprocess,'run',side_effect=subprocess.TimeoutExpired('probe',12)) as run:
   result=inventory.get();self.assertGreater(result['cpu']['logical_threads'],0)
   self.assertEqual(result['gpus'],[]);self.assertIn('CPU',result['message'])
   self.assertEqual(inventory.get(),result);self.assertEqual(run.call_count,1)
 def test_inventory_parses_json_after_native_diagnostics(self):
  result={'gpus':[],'message':'no NVIDIA'}
  with patch.object(hw.subprocess,'run',return_value=types.SimpleNamespace(stdout='native log\n'+json.dumps(result))):
   self.assertEqual(hw.Inventory().get()['message'],'no NVIDIA')

if __name__=='__main__':unittest.main()
