import json
import subprocess
import sys
import tempfile
import time
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import reaper_bridge as bridge
from desktop_app import DesktopApi

class ReaperTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.api=DesktopApi(self.root,'http://localhost','token')
        self.destination=dict(project_id='project-1',instance='instance-1',track_guid='t1',project_name='A',track_name='1 · voice')
        (self.root/'.desktop').mkdir()
        bridge.target_path(self.root).write_text(json.dumps(self.destination))
        self.aid=str(uuid.uuid4())
        p=patch.object(self.api,'_trusted',return_value=True);p.start();self.addCleanup(p.stop)

    def heartbeat(self,session='instance-1',project='project-1',age=0):
        folder=bridge.ipc_root(self.root)/session;folder.mkdir(parents=True,exist_ok=True)
        data=dict(protocol=2,session=session,projects={project:True},updated=time.time()-age,active_project='A')
        (folder/'heartbeat.json').write_text(json.dumps(data))
        return folder

    def inventory(self):
        uploads=self.root/'uploads';uploads.mkdir()
        source=uploads/'source.wav'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=duration=1','-y',str(source)],check=True)
        (self.root/'data.json').write_text(json.dumps({'audios':[{'id':self.aid,'path':source.name}]}))

    def test_real_extract_targets_ipc_without_launch(self):
        self.inventory()
        original=subprocess.Popen
        def media_process(args,**kwargs):
            self.assertIn(Path(args[0]).stem,('ffmpeg','ffprobe'))
            return original(args,**kwargs)
        with patch.object(bridge,'run_target_request',return_value={'ok':True,'project_name':'A','track_name':'1 · voice'}) as request,patch('subprocess.Popen',side_effect=media_process):
            result=self.api.send_to_reaper(self.aid,.2,.6,'한글 발음.wav')
            self.assertTrue(result.get('ok'),result)
            path=Path(result['path']);self.assertTrue(path.is_file())
            request.assert_called_once_with(self.root,None,'insert',self.destination,path,'한글 발음')
        duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)]))
        self.assertAlmostEqual(duration,.4,delta=.005)
        self.assertFalse(self.api._export_lock.locked())

    def test_ipc_capture_payload_and_ack_never_launch(self):
        folder=self.heartbeat()
        def receiver(_):
            request=next(folder.glob('*.req'))
            data={k:bytes.fromhex(v).decode() for k,v in (line.split('=',1) for line in request.read_text().splitlines())}
            self.assertEqual(data['action'],'capture')
            request.with_suffix('.json').write_text(json.dumps({'ok':True,'target':self.destination}))
        with patch('time.sleep',side_effect=receiver),patch('subprocess.Popen',side_effect=AssertionError('No app launch')):
            result=bridge.run_target_request(self.root,None,'capture')
        self.assertTrue(result['ok'])
        self.assertEqual(list(folder.glob('*.req')),[])

    def test_target_capture_failure_preserves_previous_selection(self):
        replacement={**self.destination,'track_guid':'t2'}
        with patch.object(bridge,'run_target_request',return_value={'ok':True,'target':replacement}):
            self.assertTrue(self.api.set_reaper_target()['ok'])
        with patch.object(bridge,'run_target_request',return_value={'error':'No track'}):
            self.assertIn('error',self.api.set_reaper_target())
        self.assertEqual(bridge.read_target(self.root),replacement)
        self.assertFalse(self.api._export_lock.locked())

    def test_offline_or_stale_receiver_requests_setup_without_launch(self):
        self.heartbeat(age=20)
        with patch('subprocess.Popen',side_effect=AssertionError('No app launch')):
            result=self.api.set_reaper_target()
        self.assertTrue(result['needs_receiver'])
        self.assertTrue(Path(result['script_path']).is_file())
        self.assertEqual(bridge.live_receivers(self.root),[])

    def test_multiple_instances_require_explicit_capture_selection(self):
        self.heartbeat();self.heartbeat('instance-2','project-2')
        result=bridge.run_target_request(self.root,None,'capture')
        self.assertIn('error',result)
        self.assertEqual(len(result['receivers']),2)
        self.assertEqual(list(bridge.ipc_root(self.root).glob('*/*.req')),[])

    def test_pinned_instance_validates_live_project_without_switching(self):
        pinned=self.heartbeat(project='other-project');other=self.heartbeat('instance-2','project-1')
        def receiver(_):
            request=next(pinned.glob('*.req'))
            request.with_suffix('.json').write_text(json.dumps({'error':'Project is closed'}))
        with patch('time.sleep',side_effect=receiver):
            result=bridge.run_target_request(self.root,None,'insert',self.destination)
        self.assertIn('error',result)
        self.assertEqual(list(other.glob('*.req')),[])

    def test_no_ack_is_not_success_and_pending_request_is_removed(self):
        folder=self.heartbeat()
        with patch('time.monotonic',side_effect=[0,16]):
            result=bridge.run_target_request(self.root,None,'capture')
        self.assertIn('error',result)
        self.assertEqual(list(folder.glob('*.req')),[])

    def test_legacy_pointer_target_requires_recapture(self):
        bridge.target_path(self.root).write_text(json.dumps(dict(session='old',project_pointer='address',track_guid='t1')))
        with patch('desktop_app.render_range') as render:
            self.assertTrue(self.api.send_to_reaper(self.aid,0,1,'x')['needs_target'])
            render.assert_not_called()

    def test_untrusted_or_busy_actions_do_not_mutate(self):
        self.api._export_lock.acquire()
        self.assertIn('error',self.api.set_reaper_target());self.api._export_lock.release()
        with patch.object(self.api,'_trusted',return_value=False):
            self.assertIn('error',self.api.prepare_reaper_connection())
            self.assertIn('error',self.api.open_reaper_connection_folder())
            self.assertIn('error',self.api.send_to_reaper(self.aid,0,1,'x'))

    def test_prepared_script_location_survives_version_changes(self):
        first=bridge.prepare_receiver(self.root)
        self.assertEqual(first.parent,self.root/'reaper_connection')
        self.assertEqual(bridge.prepare_receiver(self.root),first)
        self.assertNotIn('/versions/',str(first))
        self.assertIn('local ROOT=',first.read_text())

if __name__=='__main__':unittest.main()
