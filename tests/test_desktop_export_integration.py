"""Save real audio while all network requests fail, matching WinError 10054."""
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
from desktop_app import DesktopApi
from desktop_export import source_info

class IntegrationTests(unittest.TestCase):
    def test_export_without_server_all_formats(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);uploads=root/'uploads';uploads.mkdir();audios=[]
            for ext in ('wav','mp3','flac'):
                src=uploads/('source.'+ext)
                subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=duration=1','-y',str(src)],check=True)
                audios.append(dict(id=str(uuid.uuid4()),path=src.name))
            (root/'data.json').write_text(json.dumps({'audios':audios}))
            # Both URL open mechanisms must remain unused, even when the server
            # is unavailable or resets every connection.
            with patch('urllib.request.urlopen',side_effect=ConnectionResetError(10054,'reset')) as net,patch('urllib.request.OpenerDirector.open',side_effect=ConnectionResetError(10054,'reset')) as opener,patch.dict(sys.modules,webview=types.SimpleNamespace(SAVE_DIALOG=1)):
                api=DesktopApi(root,'http://127.0.0.1:1','secret')
                for a in audios:
                    target=root/('.어라'+Path(a['path']).suffix)
                    api._window=types.SimpleNamespace(get_current_url=lambda:api._url,create_file_dialog=lambda *args,**kw:str(target))
                    result=api.save_audio_range(a['id'],.2,.6,'.어라')
                    self.assertTrue(result.get('ok'),result)
                    duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(target)]))
                    self.assertAlmostEqual(duration,.4,delta=.09)
                    self.assertFalse(api._export_lock.locked())
                net.assert_not_called();opener.assert_not_called()
                # Reuse the shared timeline on the next export.
                self.assertTrue(api.save_audio_range(a['id'],.4,.7,'again').get('ok'))

    def test_invalid_inventory_fails_without_modification(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'uploads').mkdir()
            state=root/'data.json';state.write_text('{broken')
            with self.assertRaises(ValueError):source_info(root,'x')
            self.assertEqual(state.read_text(),'{broken')
            state.write_text(json.dumps({'audios':[{'id':'x','path':'../data.json'}]}))
            with self.assertRaises(ValueError):source_info(root,'x')

if __name__=='__main__':unittest.main()
