import unittest
from transcript_scripts import scripts,parse_exclusions,filter_clips

class ScriptTests(unittest.TestCase):
 def test_scripts_and_mixed_text(self):
  self.assertEqual(scripts('안녕 ㅋㅋ'),{'ko'})
  self.assertEqual(scripts('こんにちは 時々 ｶﾅ'),{'ja'})
  self.assertEqual(scripts('Hello ＡＢＣ'),{'en'})
  self.assertEqual(scripts('안녕 hello かな'),{'ko','en','ja'})
  self.assertEqual(scripts('Привет مرحبا ไทย'),{'other'})
  self.assertEqual(scripts('123!? 😀 ・'),set())
 def test_all_three_exclusions_find_other_scripts(self):
  clips=[{'transcript':t} for t in ['안녕','かな','hello','Привет','안녕 hello']]
  self.assertEqual(filter_clips(clips,{'ko','ja','en'}),[{'transcript':'Привет'}])
  self.assertEqual(filter_clips(clips,{'other'}),clips[:3]+clips[4:])
 def test_invalid_filter(self):
  self.assertEqual(parse_exclusions('ko, ja,ko'),{'ko','ja'})
  with self.assertRaises(ValueError):parse_exclusions('invalid')

if __name__=='__main__':unittest.main()
