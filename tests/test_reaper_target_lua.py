"""Execute the shipped Lua in a simulated REAPER API (no REAPER installation)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from reaper_bridge import lua_string
try:
    from lupa import LuaRuntime
except ImportError:
    LuaRuntime=None

@unittest.skipIf(LuaRuntime is None,'lupa is needed only to execute Lua regression tests')
class LuaTargetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.response=Path(self.temp.name)/'response.json'
        self.lua=LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute('''
        local a={name='한글 "프로젝트".rpp',path='C:/A.rpp',cursor=5,tracks={{guid='a1',name='voice',number=1},{guid='a2',name='second',number=2}}}
        local b={name='B.rpp',path='C:/B.rpp',cursor=20,tracks={{guid='b1',name='other',number=1}}}
        projects={a,b}; active=1; selected=1; session='session-1'; insertions={}; undo=0
        reaper={
          GetExtState=function() return session end,
          SetExtState=function(_,_,v) session=v end,
          genGuid=function() return 'new-session' end,
          EnumProjects=function(i) local p=projects[i==-1 and active or i+1];return p,p and p.path end,
          GetSelectedTrack=function(p,i) return p.tracks[selected] end,
          GetProjectName=function(p) return p.name end,
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
        ''')

    def run_request(self,action,target=None,expired=False):
        fields=dict(target or {}, action=action,response=str(self.response),media='C:/한글.wav',name='발음')
        header='local req={'+','.join(k+'='+lua_string(v) for k,v in fields.items())+',expires='+('0' if expired else '9999999999')+'}\n'
        self.lua.execute(header+Path(__file__).resolve().parents[1].joinpath('reaper_target.lua').read_text())
        return json.loads(self.response.read_text())

    def test_pin_target_even_when_project_and_track_selection_change(self):
        target=self.run_request('capture')['target']
        self.assertEqual(target['project_name'],'한글 "프로젝트".rpp')
        self.lua.execute('active=2;selected=1;projects[1].tracks[1],projects[1].tracks[2]=projects[1].tracks[2],projects[1].tracks[1]')
        self.assertTrue(self.run_request('insert',target)['ok'])
        self.lua.execute("assert(insertions[1].track.guid=='a1');assert(insertions[1].D_POSITION==5);assert(projects[1].cursor==5.4);assert(projects[2].cursor==20);assert(undo==0)")
        self.assertTrue(self.run_request('insert',target)['ok'])
        self.lua.execute('assert(insertions[2].D_POSITION==5.4);assert(#projects==2)')

    def test_closed_project_or_deleted_track_is_not_replaced(self):
        target=self.run_request('capture')['target']
        self.lua.execute('projects={projects[2]};active=1')
        self.assertIn('error',self.run_request('insert',target))
        self.lua.execute('assert(#insertions==0);assert(#projects==1)')

    def test_saved_project_recovers_after_reaper_restart(self):
        target=self.run_request('capture')['target']
        self.lua.execute("session='session-2';projects[1]={name='same',path='C:/A.rpp',cursor=0,tracks={{guid='a1',name='renamed',number=3}}}")
        self.assertTrue(self.run_request('insert',target)['ok'])

    def test_unsaved_project_does_not_retarget_after_restart(self):
        self.lua.execute("projects[1].path='' ")
        target=self.run_request('capture')['target']
        self.lua.execute("session='session-2'")
        self.assertIn('error',self.run_request('insert',target))

    def test_expired_request_never_inserts(self):
        target=self.run_request('capture')['target']
        self.assertIn('error',self.run_request('insert',target,expired=True))
        self.lua.execute('assert(#insertions==0)')

    def test_missing_track_selection_and_insert_failure(self):
        self.lua.execute('selected=99')
        self.assertIn('error',self.run_request('capture'))
        self.lua.execute('selected=1')
        target=self.run_request('capture')['target']
        self.lua.execute('reaper.SetMediaItemTake_Source=function() return false end')
        self.assertIn('error',self.run_request('insert',target))
        self.lua.execute('assert(#insertions==0);assert(undo==0)')

if __name__=='__main__':unittest.main()
