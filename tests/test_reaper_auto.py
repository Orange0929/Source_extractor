import ctypes as C
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import reaper_bridge as bridge
import reaper_windows as windows
from desktop_app import DesktopApi

class AutoTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.window=dict(key='100:20:9000',hwnd=100,pid=20,created=9000,title='A - REAPER')

    def heartbeat(self,**extra):
        data=dict(protocol=2,session='session-1',updated=time.time(),projects={},active_project='A',**extra)
        folder=bridge.ipc_root(self.root)/data['session'];folder.mkdir(parents=True,exist_ok=True)
        (folder/'heartbeat.json').write_text(json.dumps(data))

    def test_no_running_reaper_never_attempts_launch(self):
        with patch.object(windows,'enumerate_reaper_windows',return_value=[]),patch.object(windows,'deliver_script') as deliver,patch('subprocess.Popen',side_effect=AssertionError('No launch')):
            self.assertIn('error',bridge.connect_automatically(self.root))
            deliver.assert_not_called()

    def test_multiple_windows_require_selection(self):
        with patch.object(windows,'enumerate_reaper_windows',return_value=[self.window,{**self.window,'key':'other'}]),patch.object(windows,'deliver_script') as deliver:
            result=bridge.connect_automatically(self.root)
            self.assertEqual(len(result['windows']),2);deliver.assert_not_called()

    def test_existing_automatic_connection_is_reused(self):
        self.heartbeat(window_key=self.window['key'])
        with patch.object(windows,'enumerate_reaper_windows',return_value=[self.window]),patch.object(windows,'deliver_script') as deliver:
            self.assertEqual(bridge.connect_automatically(self.root)['instance'],'session-1')
            deliver.assert_not_called()

    def test_mismatching_receiver_ack_is_not_success(self):
        self.heartbeat(window_key=self.window['key'],connect_token='wrong')
        # Do not reuse this heartbeat as an auto session; emulate an unrelated window.
        with patch.object(windows,'enumerate_reaper_windows',return_value=[{**self.window,'key':'new-window'}]),patch.object(windows,'deliver_script'),patch('time.monotonic',side_effect=[0,9]):
            self.assertTrue(bridge.connect_automatically(self.root)['needs_manual'])

    def test_auto_capture_remembers_target_only_after_receiver_ack(self):
        api=DesktopApi(self.root,'http://localhost','token')
        target=dict(project_id='p',instance='s',track_guid='t',project_name='A',track_name='Voice')
        with patch.object(api,'_trusted',return_value=True),patch.object(bridge,'connect_automatically',return_value={'ok':True,'instance':'s'}),patch.object(bridge,'run_target_request',return_value={'ok':True,'target':target}):
            self.assertTrue(api.connect_reaper()['ok'])
        self.assertEqual(bridge.read_target(self.root),target)
        self.assertFalse(api._export_lock.locked())

    def test_auto_failure_preserves_manual_target(self):
        api=DesktopApi(self.root,'http://localhost','token')
        (self.root/'.desktop').mkdir();bridge.target_path(self.root).write_text('{"old":"unchanged"}')
        with patch.object(api,'_trusted',return_value=True),patch.object(bridge,'connect_automatically',return_value={'error':'blocked','needs_manual':True}),patch.object(bridge,'run_target_request') as capture:
            self.assertTrue(api.connect_reaper()['needs_manual']);capture.assert_not_called()
        self.assertEqual(bridge.target_path(self.root).read_text(),'{"old":"unchanged"}')

    def test_win32_payload_is_raw_utf8_and_script_only(self):
        script=self.root/'한글 script.lua';script.write_text('-- receiver')
        calls=[]
        class User:
            def SendMessageTimeoutW(_,hwnd,msg,sender,packet,flags,timeout,result):
                value=windows.COPYDATASTRUCT.from_address(packet)
                calls.append((hwnd,msg,value.dwData,C.string_at(value.lpData,value.cbData),timeout))
                result._obj.value=1
                return 1
        with patch.object(windows,'enumerate_reaper_windows',return_value=[self.window]),patch.object(windows,'_api',return_value=(User(),None)),patch('subprocess.Popen',side_effect=AssertionError('No launch')):
            windows.deliver_script(self.window['key'],script)
        self.assertEqual(calls,[(100,0x4a,0x100,str(script.resolve()).encode()+b'\0',3000)])

    def test_recycled_hwnd_or_pid_is_rejected(self):
        with patch.object(windows,'enumerate_reaper_windows',return_value=[{**self.window,'key':'100:20:CHANGED'}]),patch.object(windows,'_api') as api:
            with self.assertRaises(RuntimeError):windows.deliver_script(self.window['key'],self.root/'a.lua')
            api.assert_not_called()

if __name__=='__main__':unittest.main()
