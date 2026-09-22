"""Search normalization tests without loading Whisper or pitch models."""
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if 'faster_whisper' not in sys.modules:
    stub = types.ModuleType('faster_whisper')
    stub.WhisperModel = object
    sys.modules['faster_whisper'] = stub

import app


class SearchModesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name) / 'data.json'
        self.patcher = patch.object(app, 'DATA_PATH', path)
        self.patcher.start(); self.addCleanup(self.patcher.stop)
        data = {
            'profiles': [{'id': 'p', 'name': 'test'}],
            'audios': [],
            'clips': [
                {'id': 'exact', 'profile_id': 'p', 'transcript': '우도'},
                {'id': 'aspirated', 'profile_id': 'p', 'transcript': '우토'},
                {'id': 'other', 'profile_id': 'p', 'transcript': '아직'},
                {'id': 'liaison', 'profile_id': 'p', 'transcript': '옷 안'},
            ],
        }
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    def test_query_spellings_share_the_same_phone_stream(self):
        variants = ['u do', 'udo', '우도', 'ㅜ도', 'ㅜㄷㅗ']
        keys = {app.norm_continuous_phones(value) for value in variants}
        self.assertEqual(keys, {'ㅜㄷㅗ'})
        for value in variants:
            matches = app.search_clips(value, 'p', 'continuous')
            self.assertEqual(matches[0]['id'], 'exact')

    def test_strict_result_ranks_above_loose_consonant_match(self):
        matches = app.search_clips('u do', 'p', 'continuous')
        self.assertEqual([item['id'] for item in matches[:2]], ['exact', 'aspirated'])

    def test_korean_sound_mode_does_not_change_meaning(self):
        self.assertEqual(app.search_clips('u do', 'p', 'ko_sound'), [])
        self.assertEqual(app.norm_continuous_phones('옷 안'), app.norm_continuous_phones('오산'))

    def test_empty_continuous_query_keeps_existing_list_behavior(self):
        self.assertEqual(len(app.search_clips('', 'p', 'continuous')), 4)


if __name__ == '__main__':
    unittest.main()
