import sys,types,unittest
from unittest.mock import patch
sys.modules.setdefault('faster_whisper',types.SimpleNamespace(WhisperModel=object))
import app
from fastapi.testclient import TestClient

class FilterApiTests(unittest.TestCase):
 def setUp(self):
  self.clips=[dict(id=str(i),profile_id='p',transcript=t) for i,t in enumerate(['안녕','かな','漢字','hello','Привет','안녕 hello'])]
  self.patch=patch.object(app,'load_data',return_value={'clips':self.clips});self.patch.start();self.addCleanup(self.patch.stop)
  self.client=TestClient(app.app)
 def test_pagination_totals_ids_use_same_filter(self):
  query={'exclude_languages':'ko,ja','profile_id':'p','limit':1}
  page=self.client.get('/api/search',params=query).json()
  ids=self.client.get('/api/search/ids',params=query).json()
  self.assertEqual(page['total'],2);self.assertTrue(page['has_more'])
  second=self.client.get('/api/search',params=dict(query,offset=1)).json()
  self.assertEqual({page['results'][0]['id'],second['results'][0]['id']},set(ids['ids']))
  self.assertEqual(set(ids['ids']),{'3','4'})
 def test_empty_query_all_modes_and_coda_filter(self):
  for mode in ('basic','ko_sound','jp_sound','continuous'):
   result=self.client.get('/api/search',params={'mode':mode,'exclude_languages':'ko,ja,en'}).json()
   self.assertEqual([c['id'] for c in result['results']],['4'])
  self.clips[:]=[dict(id='a',profile_id='p',transcript='안'),dict(id='b',profile_id='p',transcript='안 hello')]
  result=self.client.get('/api/search',params={'q':'ㄴ','coda_only':'true','exclude_languages':'en'}).json()
  self.assertEqual([c['id'] for c in result['results']],['a'])
 def test_invalid_filter_400(self):
  self.assertEqual(self.client.get('/api/search',params={'exclude_languages':'bad'}).status_code,400)

if __name__=='__main__':unittest.main()
