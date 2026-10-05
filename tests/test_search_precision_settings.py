import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault('faster_whisper',types.SimpleNamespace(WhisperModel=object))
import app
from desktop_app import DesktopApi

class PrecisionTests(unittest.TestCase):
    def test_substring_required(self):
        self.assertEqual(app.score_contains('abcdef','abcXYZdef'),0)
        self.assertEqual(app.score_contains('abcdef','prefixabcdefsuffix'),100)

    def test_modes_exclude_partial_matches(self):
        for mode, query, texts in [('basic','여우',['여우','여유']),('ko_sound','여우',['여우','여유']),('continuous','u do',['우도','우토']),('jp_sound','さくら',['さくら','さくや'])]:
            clips=[dict(id=str(i),profile_id='p',transcript=t) for i,t in enumerate(texts)]
            with patch.object(app,'load_data',return_value={'clips':clips}),patch.object(app,'pronounce',side_effect=lambda t:t):
                self.assertEqual([c['id'] for c in app.search_clips(query,'p',mode)],['0'])

    def test_unconvertible_query_not_all_results(self):
        with patch.object(app,'load_data',return_value={'clips':[{'id':'a','transcript':'あ'}]}):
            self.assertEqual(app.search_clips('123','', 'jp_sound'),[])
            self.assertEqual(len(app.search_clips('','', 'basic')),1)

class DirectoryTests(unittest.TestCase):
    def test_persist_restart_and_missing_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); saved=root/'exports';saved.mkdir()
            api=DesktopApi(root,'http://localhost','token')
            self.assertEqual(api._export_directory(),'')
            api._remember_export_directory(saved)
            restarted=DesktopApi(root,'http://localhost','token')
            self.assertEqual(restarted._export_directory(),str(saved))
            saved.rmdir()
            self.assertEqual(restarted._export_directory(),'')

    def test_corrupt_preferences_safe(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'.desktop').mkdir();(root/'.desktop/preferences.json').write_text('{bad')
            api=DesktopApi(root,'http://localhost','token')
            self.assertEqual(api._export_directory(),'')
            api._remember_export_directory(root)
            self.assertEqual(api._export_directory(),str(root))

if __name__=='__main__':unittest.main()
