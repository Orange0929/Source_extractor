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
        self.assertEqual(app.norm_continuous_phones('옷이'), app.norm_continuous_phones('오시'))

    def test_pronunciation_rules_in_both_modes(self):
        pairs = [('학교', '학꾜'), ('같이', '가치'), ('굳이', '구지'),
                 ('좋다', '조타'), ('놓아', '노아'), ('많다', '만타'),
                 ('국화', '구콰'), ('닫히다', '다치다'), ('솜이불', '솜니불'),
                 ('읽고', '일꼬'), ('읽어', '일거'), ('밟다', '밥따'),
                 ('값이', '갑씨'), ('꽃', '꼳'), ('국물', '궁물'), ('신라', '실라')]
        for spelling, sound in pairs:
            for normalize in (app.norm_ko_sound, app.norm_continuous_phones):
                with self.subTest(spelling=spelling, mode=normalize.__name__):
                    self.assertEqual(normalize(spelling), normalize(sound))

    def test_all_final_consonant_classes(self):
        for spellings in ('각갂갘', '간', '갇갓갔갖갗같갛', '갈', '감', '갑갚', '강'):
            self.assertEqual(len({app.norm_ko_sound(s) for s in spellings}), 1)

    def test_context_and_stale_imported_keys(self):
        from korean_pronunciation import pronounce
        sentence = '신을 신고 얼른 동사무소에 가서 혼인 신고 해라'
        self.assertIn('신꼬', pronounce(sentence))
        self.assertIn('호닌 신고', pronounce(sentence))
        data = app.load_data()
        data['clips'] = [{'id': 'old', 'profile_id': 'p', 'transcript': '학교',
                          'ko_pron_norm': 'obsolete', 'continuous_norm': 'obsolete'}]
        app.DATA_PATH.write_text(json.dumps(data), encoding='utf-8')
        for mode in ('ko_sound', 'continuous'):
            for query in ('학교', '학꾜'):
                self.assertEqual(app.search_clips(query, 'p', mode)[0]['id'], 'old')

    def test_romanization_and_final_ng_are_preserved(self):
        self.assertEqual(app.norm_continuous_phones('ㅜ do'), 'ㅜㄷㅗ')
        self.assertNotEqual(app.norm_continuous_phones('아'), app.norm_continuous_phones('앙'))
        self.assertEqual(app.norm_continuous_phones('강아지'), 'ㄱㅏㅇㅏㅈㅣ')

    def test_empty_continuous_query_keeps_existing_list_behavior(self):
        self.assertEqual(len(app.search_clips('', 'p', 'continuous')), 4)


if __name__ == '__main__':
    unittest.main()
