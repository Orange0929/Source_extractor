"""Execute the real persistent receiver and Python IPC against a simulated REAPER."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import reaper_bridge as bridge
try:
    from lupa import LuaRuntime
except ImportError:
    LuaRuntime=None

@unittest.skipIf(LuaRuntime is None,'lupa is only needed for Lua regression tests')
class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.lua=LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().mkdir=lambda p,flags:Path(p).mkdir(parents=True,exist_ok=True)
        listing={}
        def files(path,index):
            if index==-1:
                listing[path]=sorted(x.name for x in Path(path).iterdir())
                return None
            if path not in listing:listing[path]=sorted(x.name for x in Path(path).iterdir())
            return next(iter(listing[path][int(index):int(index)+1]),None)
        self.lua.globals().files=files
        self.lua.execute('''
        local a={name='',path='',cursor=5,tracks={{guid='a1',name='voice',number=1},{guid='a2',name='second',number=2}}}
        local b={name='B.rpp',path='C:/B.rpp',cursor=20,tracks={{guid='b1',name='other',number=1}}}
        projects={a,b}; active=1;selected=1;insertions={};undo=0;clock=0;ext={};counter=0
        reaper={
          GetExtState=function(s,k) return ext[s..k] or '' end,
          SetExtState=function(s,k,v) ext[s..k]=v end,
          genGuid=function() counter=counter+1;return '{id-'..counter..'}' end,
          RecursiveCreateDirectory=mkdir,EnumerateFiles=files,
          time_precise=function() return clock end,
          defer=function(f) deferred=f end,atexit=function(f) at_exit=f end,
          EnumProjects=function(i) local p=projects[i==-1 and active or i+1];return p,p and p.path end,
          GetSelectedTrack=function(p,i) return p.tracks[selected] end,
          GetProjectName=function(p) return p.name end,
          GetProjExtState=function(p) return p.identity and 1 or 0,p.identity or '' end,
          SetProjExtState=function(p,_,_,v) p.identity=v end,
          GetTrackName=function(t) return true,t.name end,
          GetTrackGUID=function(t) return t.guid end,
          GetMediaTrackInfo_Value=function(t) return t.number end,
          CountTracks=function(p) return #p.tracks end,
          GetTrack=function(p,i) return p.tracks[i+1] end,
          PCM_Source_CreateFromFile=function(p) return {file=p} end,
          GetMediaSourceLength=function(s) return .4,false end,
          PCM_Source_Destroy=function() end,
          GetCursorPositionEx=function(p) return p.cursor end,
          Undo_BeginBlock2=function() undo=undo+1 end,
          Undo_EndBlock2=function() undo=undo-1 end,
          AddMediaItemToTrack=function(t) local item={track=t};insertions[#insertions+1]=item;return item end,
          AddTakeToMediaItem=function(i) i.take={};return i.take end,
          SetMediaItemTake_Source=function(t,s) t.source=s;return true end,
          SetMediaItemInfo_Value=function(i,k,v) i[k]=v end,
          GetSetMediaItemTakeInfo_String=function(t,k,v) t.name=v end,
          SetEditCurPos2=function(p,v) p.cursor=v end,
          UpdateArrange=function() end,
          DeleteTrackMediaItem=function() insertions[#insertions]=nil end
        }
        function step() clock=clock+1;deferred() end
        ''')
        self.lua.execute(bridge.prepare_receiver(self.root).read_text())

    def request(self,action,target=None,**kwargs):
        with patch('time.sleep',side_effect=lambda _:self.lua.globals().step()),patch('subprocess.Popen',side_effect=AssertionError('Must never launch REAPER')):
            return bridge.run_target_request(self.root,None,action,target,media=self.root/'한글.wav',name='발음',**kwargs)

    def test_unsaved_then_save_as_pointer_change_and_selection_change(self):
        target=self.request('capture')['target']
        self.assertEqual(target['project_name'],'(저장 안 된 프로젝트)')
        self.lua.execute('''local old=projects[1];projects[1]={name='saved.rpp',path='C:/saved.rpp',identity=old.identity,cursor=old.cursor,tracks={old.tracks[2],old.tracks[1]}};active=2''')
        self.assertTrue(self.request('insert',target)['ok'])
        self.lua.execute("assert(insertions[1].track.guid=='a1');assert(insertions[1].D_POSITION==5);assert(projects[2].cursor==20);assert(#projects==2);assert(undo==0)")
        self.assertTrue(self.request('insert',target)['ok'])
        self.lua.execute('assert(insertions[2].D_POSITION==5.4)')
        self.lua.globals().step()
        self.lua.execute('assert(#insertions==2)')

    def test_closed_project_and_deleted_track_do_not_retarget(self):
        target=self.request('capture')['target']
        self.lua.execute('projects[1].tracks={projects[1].tracks[2]}')
        self.assertIn('error',self.request('insert',target))
        self.lua.execute('projects={projects[2]};active=1');self.lua.globals().step()
        self.assertIn('error',self.request('insert',target))
        self.lua.execute('assert(#insertions==0);assert(#projects==1)')

    def test_receiver_restart_recovers_saved_project_identity(self):
        target=self.request('capture')['target']
        # The old project marker survives an RPP save/load, even with new paths.
        self.lua.execute("local p=projects[1];projects[1]={name='SaveAs.rpp',path='D:/SaveAs.rpp',identity=p.identity,cursor=0,tracks=p.tracks}")
        self.lua.execute(bridge.prepare_receiver(self.root).read_text())
        live=bridge.live_receivers(self.root)
        self.assertEqual(len(live),1)
        self.assertNotEqual(live[0]['session'],target['instance'])
        self.assertTrue(self.request('insert',target)['ok'])

    def test_duplicate_project_ids_are_rejected_and_recapture_disambiguates(self):
        target=self.request('capture')['target']
        self.lua.execute('projects[2].identity=projects[1].identity')
        self.assertIn('error',self.request('insert',target))
        replacement=self.request('capture')['target']
        self.assertNotEqual(replacement['project_id'],target['project_id'])
        self.assertTrue(self.request('insert',replacement)['ok'])

    def test_windows_crlf_request_format(self):
        target=self.request('capture')['target']
        folder=bridge.ipc_root(self.root)/target['instance']
        fields=dict(action='capture',expires='9999999999')
        request=folder/('b'*32+'.req')
        request.write_bytes(''.join(k+'='+v.encode().hex()+'\r\n' for k,v in fields.items()).encode('ascii'))
        self.lua.globals().step()
        self.assertTrue(json.loads(request.with_suffix('.json').read_text())['ok'])

    def test_expired_request_does_not_insert(self):
        target=self.request('capture')['target']
        folder=bridge.ipc_root(self.root)/target['instance']
        data=dict(action='insert',expires='0',project_id=target['project_id'],track_guid=target['track_guid'],media='x')
        request=folder/('a'*32+'.req')
        request.write_text(''.join(k+'='+v.encode().hex()+'\n' for k,v in data.items()))
        self.lua.globals().step()
        self.assertIn('error',json.loads(request.with_suffix('.json').read_text()))
        self.lua.execute('assert(#insertions==0)')

    def test_insert_failure_rolls_back_and_receiver_stays_available(self):
        target=self.request('capture')['target']
        self.lua.execute('reaper.SetMediaItemTake_Source=function() return false end')
        self.assertIn('error',self.request('insert',target))
        self.lua.execute('assert(#insertions==0);assert(undo==0)')
        self.assertEqual(len(bridge.live_receivers(self.root)),1)

if __name__=='__main__':unittest.main()
