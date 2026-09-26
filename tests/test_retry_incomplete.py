"""Recovery must retain completed audio and survive loss of in-memory jobs."""
import sys
import tempfile
import types
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault('faster_whisper', types.SimpleNamespace(WhisperModel=object))
import app as core


class Queue:
    def __init__(self):
        self.items = []

    def submit(self, fn):
        future = Future()
        self.items.append((fn, future))
        return future

    def finish(self):
        for fn, future in self.items:
            fn()
            future.set_result(None)
        self.items.clear()


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.queue = Queue()
        for key, value in {'DATA_PATH': root/'data.json', 'UPLOAD_DIR': root,
                           'CACHE_DIR': root, 'WAVEFORM_DIR': root,
                           'JOBS': {}, 'EXECUTOR': self.queue}.items():
            p = patch.object(core, key, value)
            p.start()
            self.addCleanup(p.stop)
        audios = []
        for aid, status in [('legacy', None), ('failed', 'error'), ('interrupted', 'queued'),
                            ('complete', 'done'), ('edited', 'error'), ('silent', 'done'),
                            ('missing', 'error'), ('other', None)]:
            audio = dict(id=aid, path=aid+'.wav', profile_id='q' if aid == 'other' else 'p')
            if status:
                audio['stt_status'] = status
            audios.append(audio)
            if aid != 'missing':
                (root/audio['path']).write_bytes(b'audio')
        self.clips = [dict(id='c1', audio_id='complete', profile_id='p'),
                      dict(id='c2', audio_id='edited', profile_id='p', transcript='manual')]
        core.save_data(dict(profiles=[dict(id='p'), dict(id='q')], audios=audios, clips=self.clips))

    def test_retry_preserves_results_and_skips_active(self):
        result = core.api_retry_incomplete('p')
        self.assertEqual(len(result['jobs']), 3)
        self.assertEqual(result['missing'], ['missing.wav'])
        self.assertEqual(core.api_retry_incomplete('p')['jobs'], [])
        self.assertEqual(core.load_data()['clips'], self.clips)
        self.assertEqual(core.api_delete_profile('p').status_code, 409)
        def done(job_id, *args):
            core.set_job(job_id, status='done', message='done')
        with patch.object(core, 'run_stt_job', done):
            self.queue.finish()
        core.JOBS.clear()  # application restart
        self.assertEqual(core.api_retry_incomplete('p')['jobs'], [])
        self.assertEqual(core.load_data()['clips'], self.clips)

    def test_failure_is_retryable_after_restart(self):
        core.api_retry_incomplete('p')
        with patch.object(core, 'run_stt_job', side_effect=RuntimeError('test failure')):
            self.queue.finish()
        statuses = {a['id']: a.get('stt_status') for a in core.load_data()['audios']}
        self.assertEqual(statuses['legacy'], 'error')
        core.JOBS.clear()
        self.assertEqual(len(core.api_retry_incomplete('p')['jobs']), 3)

    def test_delete_cleans_audio_without_clips_and_keeps_other_profile(self):
        result = core.api_delete_profile('p')
        self.assertEqual(result['deleted_audios'], 7)
        self.assertEqual([a['id'] for a in core.load_data()['audios']], ['other'])
        self.assertFalse((core.UPLOAD_DIR/'legacy.wav').exists())
        self.assertTrue((core.UPLOAD_DIR/'other.wav').exists())
        self.assertIsNone(core.submit_audio_job(dict(id='legacy', path='legacy.wav')))

    def test_create_adds_profile_without_replacing_existing(self):
        result = core.api_create_profile('New')
        self.assertEqual(result['profile']['name'], 'New')
        self.assertEqual(len(core.load_data()['profiles']), 3)
        self.assertEqual(core.load_data()['clips'], self.clips)


if __name__ == '__main__':
    unittest.main()
