import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault('faster_whisper', types.SimpleNamespace(WhisperModel=object))
import app
from fastapi.testclient import TestClient

class TranscriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for mock in (patch.object(app, 'DATA_PATH', Path(self.temp.name)/'data.json'),
                     patch.object(app, 'pronounce', side_effect=lambda t:t), patch.object(app, 'audit')):
            mock.start(); self.addCleanup(mock.stop)
        self.clip = dict(id='c',profile_id='p',audio_id='a',start_s=1.2,end_s=2.4,transcript='여유',norm='여유')
        app.save_data(dict(profiles=[dict(id='p',name='test')], audios=[], clips=[self.clip]))
        self.client = TestClient(app.app)

    def edit(self, text, expected='여유', clip='c'):
        return self.client.post('/api/clips/'+clip+'/transcript',json=dict(transcript=text,expected_transcript=expected))

    def test_persist_search_and_preserve_boundaries(self):
        self.assertEqual(self.edit('여우').status_code,200)
        c=app.load_data()['clips'][0]
        for key in ('id','profile_id','audio_id','start_s','end_s'):
            self.assertEqual(c[key],self.clip[key])
        self.assertEqual(c['original_transcript'],'여유')
        for key,fn in [('norm',app.norm_basic),('ko_pron_norm',app.norm_ko_sound),('jp_kana_norm',app.jp_kana_norm),('continuous_norm',app.norm_continuous_phones)]:
            self.assertEqual(c[key],fn('여우'))
        for mode in ('basic','ko_sound','continuous'):
            self.assertEqual(len(app.search_clips('여우','p',mode)),1)
            self.assertEqual(app.search_clips('여유','p',mode),[])
        self.assertEqual(self.edit('안','여우').status_code,200)
        self.assertEqual(app.load_data()['clips'][0]['original_transcript'],'여유')
        self.assertEqual(len(app.search_clips('ㄴ','p','basic',True)),1)

    def test_invalid_and_conflicting_updates_do_not_overwrite(self):
        self.assertEqual(self.edit(' ').status_code,400)
        self.assertEqual(self.edit('x'*20001).status_code,400)
        self.assertEqual(self.edit('여우',clip='missing').status_code,404)
        self.assertEqual(self.edit('여우',expected='old').status_code,409)
        self.assertEqual(app.load_data()['clips'][0]['transcript'],'여유')

if __name__=='__main__': unittest.main()
