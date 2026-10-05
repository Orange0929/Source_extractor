import io
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
sys.modules.setdefault('faster_whisper',types.SimpleNamespace(WhisperModel=object))
import app as core
import desktop_app

class CodaTests(unittest.TestCase):
    def test_coda_not_onset_and_profile_scope(self):
        clips=[dict(id=str(i),transcript=t,profile_id='p') for i,t in enumerate(['니','나','안','눈','산','값','아'])]
        clips.append(dict(id='other',transcript='안',profile_id='q'))
        with patch.object(core,'load_data',return_value={'clips':clips}):
            for mode in ['basic','ko_sound','continuous','jp_sound']:
                self.assertEqual({c['transcript'] for c in core.search_clips('ㄴ','p',mode,True)}, {'안','눈','산'})
            self.assertEqual(core.search_clips('ㅄ','p','basic',True)[0]['transcript'],'값')
            with self.assertRaises(core.HTTPException): core.search_clips('나','p','basic',True)
            ids=core.api_search_ids('ㄴ','p','basic',True)['ids']
            page=core.api_search('ㄴ','p',100,0,'basic',True)['results']
            self.assertEqual(ids,[c['id'] for c in page])

class ExportTests(unittest.TestCase):
    def test_real_formats_and_trim_duration(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for ext,codec in [('wav','pcm_s16le'),('mp3','mp3'),('flac','flac')]:
                src=root/('source.'+ext)
                subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=1','-y',str(src)],check=True)
                audio={'id':'a','path':src.name}
                with patch.object(core,'_find_audio',return_value=(audio,src)),patch.object(core,'UPLOAD_DIR',root),patch.object(core,'CACHE_DIR',root),patch.object(core,'audio_timeline_source',side_effect=lambda p:p):
                    r=core.api_audio_range('a',.2,.6,'발음')
                    meta=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(r.path)]))
                    self.assertEqual(meta['streams'][0]['codec_name'],codec)
                    self.assertAlmostEqual(float(meta['format']['duration']),.4,delta=.09)
                    self.assertEqual(r.filename,'발음.'+ext)

    def test_desktop_extension_and_existing_file_confirmation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); api=desktop_app.DesktopApi(root,'http://127.0.0.1:1234','token')
            target=root/'발음'
            window=types.SimpleNamespace(create_file_dialog=lambda *a,**kw:str(target),create_confirmation_dialog=lambda *a:False)
            api._window=window
            with patch.object(api,'_trusted',return_value=True),patch.dict(sys.modules,webview=types.SimpleNamespace(SAVE_DIALOG=1)):
                with patch.object(desktop_app.urllib.request,'urlopen',side_effect=[io.BytesIO(b'{"extension":"mp3"}'),io.BytesIO(b'audio')]):
                    self.assertTrue(api.save_audio_range(str(uuid.uuid4()),0,1,'발음')['ok'])
                self.assertEqual((root/'발음.mp3').read_bytes(),b'audio')
                with patch.object(desktop_app.urllib.request,'urlopen',return_value=io.BytesIO(b'{"extension":"mp3"}')):
                    self.assertTrue(api.save_audio_range(str(uuid.uuid4()),0,1,'발음')['cancelled'])
                self.assertEqual((root/'발음.mp3').read_bytes(),b'audio')

if __name__=='__main__':unittest.main()
