"""Real worker IPC + FFmpeg timeline, using a tiny model stub (no weights/GPU)."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from stt_manager import Manager

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
class ProcessTest(unittest.TestCase):
 def test_worker_creates_timeline_and_returns_complete_clips_without_writing_data(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);audio=root/'voice.wav'
   subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=1',str(audio)],check=True)
   bootstrap=root/'bootstrap.py'
   bootstrap.write_text('''import sys,types
sys.path.insert(0,ROOT)
class Model:
 def __init__(self,*a,**kw): pass
 def transcribe(self,*a,**kw):
  return [types.SimpleNamespace(text='hello',start=.1,end=.7,words=[])],None
sys.modules['faster_whisper']=types.SimpleNamespace(WhisperModel=Model)
sys.modules['ctranslate2']=types.SimpleNamespace(get_cuda_device_count=lambda:0)
import app as core
core.norm_ko_sound=lambda s:s
core.jp_kana_norm=lambda s:s
import stt_worker
stt_worker.main()
'''.replace('ROOT',repr(str(Path(__file__).resolve().parents[1]))))
   with patch.dict(os.environ,{'SOURCE_EXTRACTOR_DATA_DIR':tmp}):
    manager=Manager(root,[sys.executable,'-u',str(bootstrap)])
    try:
     manager.configure({'device':'cpu','threads':1})
     result=manager.run(dict(job_id='j',profile_id='p',audio_id='a',path=str(audio)),threading.Event(),lambda _:None)
     self.assertEqual(result['status'],'done',result)
     self.assertEqual(result['clips'][0]['transcript'],'hello')
     self.assertTrue((root/'timeline_cache'/'voice.timeline.flac').is_file())
     if (root/'data.json').exists():
      import json
      self.assertEqual(json.loads((root/'data.json').read_text())['clips'],[])
    finally:manager.close()
