import json
import subprocess
import sys
import tempfile
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import reaper_bridge
from desktop_app import DesktopApi

class ReaperTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.exe=self.root/'REAPER portable'/'reaper.exe'
        self.exe.parent.mkdir();self.exe.write_bytes(b'test')
        self.api=DesktopApi(self.root,'http://localhost','token')
        self.api._window=types.SimpleNamespace(create_file_dialog=lambda *a,**k:str(self.exe))
        self.aid=str(uuid.uuid4())
        self.destination=dict(session='session-1',project_pointer='p1',project_path='C:/A.rpp',track_guid='t1',project_name='A',track_name='1 · voice')
        (self.root/'.desktop').mkdir(exist_ok=True)
        reaper_bridge.target_path(self.root).write_text(json.dumps(self.destination))
        for p in (patch.object(self.api,'_trusted',return_value=True),patch.dict(sys.modules,webview=types.SimpleNamespace(OPEN_DIALOG=1))):
            p.start();self.addCleanup(p.stop)

    def inventory(self):
        uploads=self.root/'uploads';uploads.mkdir()
        source=uploads/'source.wav'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=duration=1','-y',str(source)],check=True)
        (self.root/'data.json').write_text(json.dumps({'audios':[{'id':self.aid,'path':source.name}]}))
        return source

    def test_real_extract_persistent_handoff_and_discovery(self):
        self.inventory()
        with patch.object(reaper_bridge,'find_reaper',return_value=None),patch.object(reaper_bridge,'run_target_request',return_value={'ok':True,'project_name':'A','track_name':'1 · voice'}) as launch:
            result=self.api.send_to_reaper(self.aid,.2,.6,'한글 발음.wav')
            self.assertTrue(result.get('ok'),result)
            path=Path(result['path'])
            self.assertEqual(path.parent,self.root/'reaper_media')
            self.assertTrue(path.is_file())
            self.assertEqual(path.suffix,'.wav')
            launch.assert_called_once_with(self.root,self.exe.resolve(),'insert',self.destination,path,'한글 발음')
        duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)]))
        self.assertAlmostEqual(duration,.4,delta=.005)
        self.assertFalse(self.api._export_lock.locked())
        # A restarted host finds the remembered portable executable.
        self.assertEqual(reaper_bridge.find_reaper(self.root),self.exe.resolve())
        self.assertTrue(path.exists())

    def test_launch_passes_only_lua_not_media_as_argument(self):
        media=self.root/'한글; & name.wav'
        def launch(args,**kwargs):
            self.assertEqual(args[:2],[str(self.exe),'-nonewinst'])
            script=Path(args[2])
            self.assertEqual(script.suffix,'.lua')
            self.assertNotIn(str(media),args)
            self.assertIn(str(media),script.read_text())
            script.with_suffix('.json').write_text(json.dumps({'ok':True,'project_name':'A','track_name':'voice'}))
        with patch.object(reaper_bridge.subprocess,'Popen',side_effect=launch):
            result=reaper_bridge.run_target_request(self.root,self.exe,'insert',self.destination,media,'test')
            self.assertTrue(result['ok'])
        self.assertEqual(list((self.root/'.desktop/reaper_requests').glob('*')),[])

    def test_target_capture_and_failure_preserve_last_selection(self):
        replacement={**self.destination,'track_guid':'t2','track_name':'2 · other'}
        with patch.object(reaper_bridge,'find_reaper',return_value=self.exe),patch.object(reaper_bridge,'run_target_request',return_value={'ok':True,'target':replacement}):
            self.assertTrue(self.api.set_reaper_target()['ok'])
        self.assertEqual(reaper_bridge.read_target(self.root),replacement)
        with patch.object(reaper_bridge,'find_reaper',return_value=self.exe),patch.object(reaper_bridge,'run_target_request',return_value={'error':'No track selected'}):
            self.assertIn('error',self.api.set_reaper_target())
        self.assertEqual(reaper_bridge.read_target(self.root),replacement)
        self.assertFalse(self.api._export_lock.locked())

    def test_no_target_does_not_extract_or_launch(self):
        reaper_bridge.target_path(self.root).unlink()
        with patch('desktop_app.render_range') as render,patch.object(reaper_bridge,'run_target_request') as request:
            self.assertTrue(self.api.send_to_reaper(self.aid,0,1,'x')['needs_target'])
            render.assert_not_called();request.assert_not_called()

    def test_no_acknowledgement_does_not_report_success(self):
        with patch.object(reaper_bridge.subprocess,'Popen'),patch('time.monotonic',side_effect=[0,16]):
            result=reaper_bridge.run_target_request(self.root,self.exe,'capture')
        self.assertIn('error',result)
        self.assertEqual(reaper_bridge.read_target(self.root),self.destination)

    def test_cancel_does_not_extract(self):
        self.inventory();self.api._window.create_file_dialog=lambda *a,**k:None
        with patch.object(reaper_bridge,'find_reaper',return_value=None),patch('desktop_app.render_range') as render:
            self.assertTrue(self.api.send_to_reaper(self.aid,0,.5,'clip')['cancelled'])
            render.assert_not_called()
        self.assertFalse(self.api._export_lock.locked())

    def test_rejected_if_export_is_busy_or_not_trusted(self):
        self.api._export_lock.acquire()
        self.assertIn('error',self.api.send_to_reaper(self.aid,0,1,'x'))
        self.api._export_lock.release()
        with patch.object(self.api,'_trusted',return_value=False),patch('desktop_app.source_info') as source:
            self.assertIn('error',self.api.send_to_reaper(self.aid,0,1,'x'))
            source.assert_not_called()

    def test_launch_failure_preserves_export_and_releases_lock(self):
        self.inventory()
        with patch.object(reaper_bridge,'find_reaper',return_value=self.exe),patch.object(reaper_bridge,'run_target_request',side_effect=OSError('test launch failure')):
            self.assertIn('error',self.api.send_to_reaper(self.aid,0,.5,'x'))
        self.assertEqual(len(list((self.root/'reaper_media').glob('*.wav'))),1)
        self.assertEqual(list((self.root/'reaper_media').glob('*.partial.wav')),[])
        self.assertFalse(self.api._export_lock.locked())

if __name__=='__main__':unittest.main()
