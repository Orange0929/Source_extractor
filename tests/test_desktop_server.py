"""Live loopback smoke test, with STT model loading stubbed out."""
import asyncio
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from desktop_server import blocks_close, configure_server_event_loop, job_reason, operation_label
from concurrent.futures import Future
from unittest.mock import Mock, patch
from desktop_app import DesktopApi


class ServerEventLoopTest(unittest.TestCase):
    def test_windows_uses_selector_policy_before_starting_server(self):
        with patch('desktop_server.sys.platform', 'win32'), \
             patch.object(asyncio, 'WindowsSelectorEventLoopPolicy', create=True) as policy, \
             patch.object(asyncio, 'set_event_loop_policy') as install:
            configure_server_event_loop()
            policy.assert_called_once_with()
            install.assert_called_once_with(policy.return_value)

    def test_other_platforms_keep_their_event_loop_policy(self):
        with patch('desktop_server.sys.platform', 'linux'), \
             patch.object(asyncio, 'set_event_loop_policy') as install:
            configure_server_event_loop()
            install.assert_not_called()

    @unittest.skipUnless(sys.platform == 'win32', 'Windows event loop implementation')
    def test_windows_runner_really_uses_selector_loop(self):
        original = asyncio.get_event_loop_policy()
        try:
            configure_server_event_loop()
            async def check():
                self.assertIsInstance(asyncio.get_running_loop(), asyncio.SelectorEventLoop)
            asyncio.run(check())
        finally:
            asyncio.set_event_loop_policy(original)


class CloseTrackingTest(unittest.TestCase):
    def test_reason_labels_and_finishing_jobs(self):
        self.assertEqual(operation_label({'path':'/api/import'}), '프로필 가져오기')
        self.assertEqual(operation_label({'path':'/api/audio_analysis/a'}), '피치 분석')
        future = Future()
        job = {'filename':'대사.wav', 'status':'done', 'progress':100, '_future':future}
        self.assertIn('분석 종료 처리 중: 대사.wav', job_reason(job))
        future.set_result(None)
        self.assertIsNone(job_reason(job))

    def test_close_reason_distinguishes_server_update_and_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            api = DesktopApi(Path(temp), 'http://127.0.0.1:1', 'test')
            api._process = Mock()
            api._process.poll.return_value = None
            with patch.object(api, '_server', return_value={'ok':False,'reasons':['피치 분석: 1건']}):
                self.assertFalse(api._can_close())
                self.assertEqual(api._close_reason, '피치 분석: 1건')
            with patch.object(api, '_server', side_effect=TimeoutError('timed out')):
                self.assertFalse(api._can_close())
                self.assertIn('서버 응답 확인 실패', api._close_reason)
            api._set('downloading', '실행 구성 요소 설치 중')
            api._lock.acquire()
            try:
                self.assertFalse(api._can_close())
                self.assertIn('실행 구성 요소 설치 중', api._close_reason)
            finally:
                api._lock.release()
            with patch.object(api, '_server', return_value={'ok':True}):
                self.assertTrue(api._can_close())
                self.assertEqual(api._close_reason, '')

    def test_playback_search_and_polling_do_not_block_exit(self):
        for path in ('/api/audio_source/a', '/api/clip_audio/c', '/api/audio_range/a',
                     '/api/search', '/api/search/ids', '/api/jobs/j', '/api/profiles',
                     '/api/audios', '/api/desktop/health'):
            with self.subTest(path=path):
                self.assertFalse(blocks_close({'type':'http', 'method':'GET', 'path':path}))

    def test_mutations_exports_and_analysis_remain_protected(self):
        for method, path in (('POST','/api/import'), ('POST','/api/upload'),
                             ('DELETE','/api/clips/c'), ('GET','/api/export/profile/p'),
                             ('GET','/api/clips/bulk_download/d'),
                             ('GET','/api/audio_analysis/a'), ('GET','/api/audio_waveform/a')):
            with self.subTest(path=path):
                self.assertTrue(blocks_close({'type':'http','method':method,'path':path}))
        self.assertFalse(blocks_close({'type':'http','method':'POST','path':'/api/desktop/prepare-close'}))


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
                    # Source switches cancel in-flight media/range responses.
                    # Exercise abrupt TCP resets, including clients abandoning
                    # an incomplete request, then verify the listener survives.
                    address = ('127.0.0.1', int(port_file.read_text()))
                    linger = struct.pack('hh' if os.name == 'nt' else 'ii', 1, 0)
                    for index in range(80):
                        with socket.create_connection(address, timeout=5) as client:
                            client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, linger)
                            if index % 2:
                                client.sendall(b'GET /static/app.js HTTP/1.1\r\nHost: localhost\r\nRange: bytes=0-65535\r\n\r\n')
                                client.recv(128)
                            else:
                                client.sendall(b'GET /static/app.js HTTP/1.1\r\n')
                        if index % 10 == 9:
                            with request('/api/desktop/health') as response:
                                self.assertFalse(json.load(response)['busy'])
                    with request('/static/app.js') as response:
                        self.assertGreater(len(response.read()), 1000)
                    self.assertIsNone(proc.poll())
                    if sys.platform == 'win32':
                        self.assertIn('Local server event loop: _WindowsSelectorEventLoop',
                                      (root/'server.log').read_text())
                    with request('/api/stt/gpu-install') as response:
                        self.assertFalse(json.load(response)['busy'])
                    with request('/api/stt/hardware') as response:
                        hardware=json.load(response)
                        self.assertGreater(hardware['cpu']['logical_threads'],0)
                        self.assertTrue(hardware['cpu']['name'])
                        self.assertIsInstance(hardware['gpus'],list)
                    with request('/api/stt/control') as response:
                        self.assertEqual(json.load(response)['settings']['performance'],'balanced')
                    def stt_post(path, data):
                        req=urllib.request.Request(url+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
                        with urllib.request.urlopen(req,timeout=5) as response:return json.load(response)
                    self.assertTrue(stt_post('/api/stt/control/pause',{})['paused'])
                    self.assertEqual(stt_post('/api/stt/settings',{'device':'cpu','threads':1})['settings']['device'],'cpu')
                    self.assertFalse(stt_post('/api/stt/control/resume',{})['paused'])
                    self.assertFalse(stt_post('/api/stt/control/stop',{})['paused'])
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
