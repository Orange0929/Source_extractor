"""Exercise real HTTP, ffmpeg and desktop copying, not mocked audio responses."""
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import types
import unittest
import urllib.request
import uuid
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault('faster_whisper',types.SimpleNamespace(WhisperModel=object))
import app
import uvicorn
from desktop_app import DesktopApi
from desktop_server import blocks_close

class IntegrationTests(unittest.TestCase):
    def test_real_http_render_and_local_save_all_formats(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);cache=root/'clips_cache';cache.mkdir()
            audios=[]
            for ext in ('wav','mp3','flac'):
                src=root/('source.'+ext)
                subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=duration=1','-y',str(src)],check=True)
                audios.append(dict(id=str(uuid.uuid4()),path=src.name))
            with patch.object(app,'load_data',return_value={'audios':audios}),patch.object(app,'UPLOAD_DIR',root),patch.object(app,'CACHE_DIR',cache),patch.object(app,'audio_timeline_source',side_effect=lambda p:p),patch.object(app,'audit'),patch.dict(os.environ,SOURCE_EXTRACTOR_SERVER_TOKEN='test-secret'),patch.dict(sys.modules,webview=types.SimpleNamespace(SAVE_DIALOG=1)):
                sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(10)
                url='http://127.0.0.1:'+str(sock.getsockname()[1])
                server=uvicorn.Server(uvicorn.Config(app.app,log_level='error'))
                thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
                try:
                    api=DesktopApi(root,url,'test-secret')
                    for a in audios:
                        ext=Path(a['path']).suffix
                        target=root/('.어라'+ext)
                        api._window=types.SimpleNamespace(get_current_url=lambda:url,create_file_dialog=lambda *args,**kw:str(target))
                        result=api.save_audio_range(a['id'],.2,.6,'.어라')
                        self.assertTrue(result.get('ok'),result)
                        duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(target)]))
                        self.assertAlmostEqual(duration,.4,delta=.09)
                    req=urllib.request.Request(url+'/api/desktop/audio-export/'+audios[0]['id']+'?start_s=0&end_s=1',method='POST')
                    with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(req,timeout=5)
                    self.assertEqual(caught.exception.code,403)
                    self.assertTrue(blocks_close({'type':'http','method':'POST','path':'/api/desktop/audio-export/a'}))
                finally:
                    server.should_exit=True;thread.join(5);sock.close()

if __name__=='__main__':unittest.main()
