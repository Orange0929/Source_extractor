"""Live loopback smoke test, with STT model loading stubbed out."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[1]


class DesktopServerTest(unittest.TestCase):
    def test_original_data_directory_and_close_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);port_file=root/'port'
            env=dict(os.environ,SOURCE_EXTRACTOR_DATA_DIR=str(root),SOURCE_EXTRACTOR_PORT_FILE=str(port_file),
                     SOURCE_EXTRACTOR_PORT='0',SOURCE_EXTRACTOR_SERVER_TOKEN='test-token')
            script="import sys,types,runpy; m=types.ModuleType('faster_whisper');m.WhisperModel=object;sys.modules['faster_whisper']=m;runpy.run_path('desktop_server.py',run_name='__main__')"
            with (root/'server.log').open('w') as log:
                proc=subprocess.Popen([sys.executable,'-c',script],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
                try:
                    deadline=time.monotonic()+20
                    while not port_file.exists() and proc.poll() is None and time.monotonic()<deadline:time.sleep(.05)
                    self.assertTrue(port_file.exists(),(root/'server.log').read_text())
                    url='http://127.0.0.1:'+port_file.read_text()
                    def request(path, data=None, token=True):
                        headers={'X-Desktop-Token':'test-token'} if token else {}
                        if data is not None:headers['Content-Type']='application/x-www-form-urlencoded'
                        return urllib.request.urlopen(urllib.request.Request(url+path,data=data,headers=headers),timeout=5)
                    while True:
                        try:
                            with request('/api/desktop/health') as response:health=json.load(response)
                            break
                        except (OSError,ValueError):
                            if time.monotonic()>deadline:raise
                            time.sleep(.05)
                    self.assertFalse(health['busy'])
                    with self.assertRaises(urllib.error.HTTPError) as error:request('/api/desktop/health',token=False)
                    self.assertEqual(error.exception.code,403)
                    with request('/') as response:
                        html=response.read().decode();self.assertIn('desktop_ui.js',html);self.assertIn('btnCheckUpdate',html)
                    with request('/api/profiles',b'name=desktop-test') as response:
                        self.assertTrue(json.load(response)['ok'])
                    self.assertTrue(any(p['name']=='desktop-test' for p in json.loads((root/'data.json').read_text())['profiles']))
                    with request('/api/desktop/prepare-close',b'') as response:self.assertTrue(json.load(response)['ok'])
                    with self.assertRaises(urllib.error.HTTPError) as error:request('/api/profiles',b'name=must-not-save')
                    self.assertEqual(error.exception.code,503)
                    self.assertFalse(any(p['name']=='must-not-save' for p in json.loads((root/'data.json').read_text())['profiles']))
                finally:
                    proc.terminate()
                    try:proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:proc.kill();proc.wait()

if __name__=='__main__':unittest.main()
