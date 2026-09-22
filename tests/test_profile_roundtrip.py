"""Profile ZIP integration tests, without downloading STT or pitch models."""
import io
import json
import shutil
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import wave
import zipfile
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if 'faster_whisper' not in sys.modules:
    try:
        import faster_whisper
    except ImportError:
        stub = types.ModuleType('faster_whisper')
        stub.WhisperModel = object
        sys.modules['faster_whisper'] = stub
import app as core
import app_fixed
from fastapi.testclient import TestClient


class ProfileRoundtrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name in ['uploads','exports','imports','waves','clips','timeline']:
            (root/name).mkdir()
        for key,name in [('UPLOAD_DIR','uploads'),('EXPORT_DIR','exports'),('IMPORT_DIR','imports'),('WAVEFORM_DIR','waves'),('CACHE_DIR','clips')]:
            patcher=patch.object(core,key,root/name);patcher.start();self.addCleanup(patcher.stop)
        for obj,key,value in [(core,'DATA_PATH',root/'data.json'),(app_fixed,'TIMELINE_DIR',root/'timeline')]:
            patcher=patch.object(obj,key,value);patcher.start();self.addCleanup(patcher.stop)
        samples=(np.sin(2*np.pi*220*np.arange(48000)/16000)*10000).astype('<i2')
        for name in ['one.WAV','empty.wav']:
            with wave.open(str(root/'uploads'/name),'wb') as f:
                f.setparams((1,2,16000,0,'NONE','not compressed'));f.writeframes(samples.tobytes())
        self.data={'profiles':[{'id':'p','name':'test'}],
                   'audios':[{'id':'a','profile_id':'p','path':'one.WAV'}, {'id':'b','profile_id':'p','path':'empty.wav'}],
                   'clips':[{'id':'c','profile_id':'p','audio_id':'a','start_s':.5,'end_s':1.25,'text':'manual'}]}
        core.save_data(self.data)
        self.client=TestClient(core.app)
        self.addCleanup(self.client.close)

    def test_roundtrip_preserves_pitch_without_model(self):
        before=self.client.get('/api/audio_analysis/a',params={'start_s':.2,'end_s':1.8}).json()
        params = {'start_s':.2,'end_s':1.8,'kind':'pitch'}
        with patch.object(core, 'pitch', return_value={'points':[[.2,220.0],[.21,None]],'method':'FCPE'}) as detector:
            pitch_before = self.client.get('/api/audio_analysis/a', params=params).json()
            self.assertEqual(detector.call_count, 1)
        # Restart-equivalent: clear all in-memory content fingerprints.
        core.pitch_store._digest.cache_clear()
        with patch.object(core, 'pitch', side_effect=AssertionError('model must not run')):
            self.assertEqual(self.client.get('/api/audio_analysis/a', params=params).json(), pitch_before)
        exported=self.client.get('/api/export/profile/p')
        self.assertEqual(exported.status_code,200)
        with zipfile.ZipFile(io.BytesIO(exported.content)) as z:
            self.assertIn('uploads/empty.wav',z.namelist())
            self.assertTrue(any(n.startswith('pitch/') for n in z.namelist()))
        # A fresh installation has no local cached pitch or canonical timeline.
        shutil.rmtree(core.WAVEFORM_DIR / 'pitch')
        shutil.rmtree(app_fixed.TIMELINE_DIR)
        app_fixed.TIMELINE_DIR.mkdir()
        imported=self.client.post('/api/import',files={'file':('profile.zip',exported.content,'application/zip')})
        self.assertEqual(imported.status_code,200,imported.text)
        pid=imported.json()['imported_profile']['id']
        data=core.load_data()
        clip=next(c for c in data['clips'] if c['profile_id']==pid)
        self.assertNotEqual(clip['audio_id'],'a')
        self.assertEqual((clip['start_s'],clip['end_s']),(.5,1.25))
        aid=clip['audio_id']
        after=self.client.get('/api/audio_analysis/'+aid,params={'start_s':.2,'end_s':1.8})
        self.assertEqual(after.status_code,200,after.text)
        self.assertEqual(before,after.json())
        self.assertEqual(imported.json()['pitch_results'], 1)
        core.pitch_store._digest.cache_clear()
        with patch.object(core, 'pitch', side_effect=AssertionError('import must restore pitch')):
            r=self.client.get('/api/audio_analysis/'+aid, params=params)
            self.assertEqual(r.status_code,200,r.text)
            self.assertEqual(r.json(),pitch_before)
        r=self.client.get('/api/audio_range/'+aid,params={'start_s':.5,'end_s':1.25,'download':False})
        self.assertEqual(r.status_code,200,r.text)
        with wave.open(io.BytesIO(r.content),'rb') as f:
            self.assertAlmostEqual(f.getnframes()/f.getframerate(),.75,places=3)

    def test_legacy_cache_is_exported_and_imported(self):
        _, src = core._find_audio('a')
        result = {'start':.2,'end':1.8,'points':[[.2,220.0]],'method':'FCPE'}
        key = core.pitch_store.legacy_key(src,.2,1.8)
        (core.WAVEFORM_DIR / (key+'.json')).write_text(json.dumps(result))
        exported = self.client.get('/api/export/profile/p')
        self.assertEqual(exported.status_code,200)
        with zipfile.ZipFile(io.BytesIO(exported.content)) as z:
            self.assertTrue(any(n.startswith('pitch/') for n in z.namelist()))
        with patch.object(core,'pitch',side_effect=AssertionError('legacy migration must not infer')):
            r = self.client.get('/api/audio_analysis/a',params={'start_s':.2,'end_s':1.8,'kind':'pitch'})
            self.assertEqual(r.status_code,200,r.text)
            self.assertEqual(r.json()['points'],result['points'])

    def test_changed_range_and_corrupt_cache_reanalyze(self):
        params={'start_s':.2,'end_s':1.8,'kind':'pitch'}
        with patch.object(core,'pitch',return_value={'points':[[.2,220.0]],'method':'FCPE'}) as detector:
            self.assertEqual(self.client.get('/api/audio_analysis/a',params=params).status_code,200)
            cached=next((core.WAVEFORM_DIR/'pitch').glob('*.json'))
            cached.write_text('{broken')
            self.assertEqual(self.client.get('/api/audio_analysis/a',params=params).status_code,200)
            self.assertEqual(self.client.get('/api/audio_analysis/a',params=dict(params,end_s=2)).status_code,200)
            self.assertEqual(detector.call_count,3)

    def test_old_zip_without_pitch_remains_supported(self):
        exported=self.client.get('/api/export/profile/p')
        self.assertEqual(exported.status_code,200)
        imported=self.client.post('/api/import',files={'file':('old.zip',exported.content,'application/zip')})
        self.assertEqual(imported.status_code,200,imported.text)
        self.assertEqual(imported.json()['pitch_results'],0)
        self.assertEqual(imported.json()['pitch_warnings'],0)

    def test_wrong_source_pitch_is_not_restored(self):
        result={'start':.2,'end':1.8,'points':[[.2,220.0]],'method':'FCPE',
                'source_sha256':'0'*64,'analysis_version':core.pitch_store.VERSION}
        original=self.client.get('/api/export/profile/p')
        buf=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(original.content)) as source, zipfile.ZipFile(buf,'w') as archive:
            for name in source.namelist(): archive.writestr(name,source.read(name))
            archive.writestr('pitch/wrong.json',json.dumps(result))
        imported=self.client.post('/api/import',files={'file':('wrong.zip',buf.getvalue(),'application/zip')})
        self.assertEqual(imported.status_code,200,imported.text)
        self.assertEqual(imported.json()['pitch_results'],0)
        self.assertEqual(imported.json()['pitch_warnings'],1)

    def test_missing_original_rejected(self):
        (core.UPLOAD_DIR/'one.WAV').unlink()
        self.assertEqual(self.client.get('/api/export/profile/p').status_code,400)
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z:z.writestr('data.json',json.dumps(self.data))
        r=self.client.post('/api/import',files={'file':('bad.zip',buf.getvalue(),'application/zip')})
        self.assertEqual(r.status_code,400)
        self.assertEqual(len(core.load_data()['profiles']),1)

if __name__=='__main__':unittest.main()
