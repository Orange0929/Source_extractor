import io
from unittest.mock import patch
from fastapi import UploadFile
from test_retry_incomplete import RecoveryTests
import app as core

class UploadTests(RecoveryTests):
    def upload(self, payload, name='same.wav', profile='p'):
        with patch.object(core,'ffprobe_duration',return_value=1):
            return core.api_upload(profile, UploadFile(io.BytesIO(payload),filename=name))

    def test_content_not_filename_and_active_reuse(self):
        first=self.upload(b'new content')
        same=self.upload(b'new content','renamed.wav')
        different=self.upload(b'other content')
        self.assertEqual(first['job_id'],same['job_id'])
        self.assertTrue(same['duplicate'])
        self.assertNotEqual(first['audio']['id'],different['audio']['id'])
        self.assertEqual(len(self.queue.items),2)

    def test_legacy_completed_reused_and_failed_retried(self):
        data=core.load_data()
        data['audios']=[a for a in data['audios'] if a['id']=='complete']
        core.save_data(data)
        r=self.upload(b'audio')
        self.assertTrue(r['skipped']); self.assertIsNone(r['job_id'])
        data['clips']=[];data['audios'][0]['stt_status']='error';core.save_data(data)
        r=self.upload(b'audio')
        self.assertTrue(r['duplicate']);self.assertIsNotNone(r['job_id'])
        self.assertEqual(len(core.load_data()['audios']),1)

    def test_profile_isolation(self):
        a=self.upload(b'unique',profile='p')
        b=self.upload(b'unique',profile='q')
        self.assertNotEqual(a['audio']['id'],b['audio']['id'])

    def test_699_uploads_repeated_after_restart(self):
        def done(jid,*args): core.set_job(jid,status='done',progress=100)
        for i in range(699): self.upload(f'file-{i}'.encode())
        with patch.object(core,'run_stt_job',done): self.queue.finish()
        core.JOBS.clear();core._AUDIO_HASHES.clear()
        for i in range(699): self.assertTrue(self.upload(f'file-{i}'.encode())['skipped'])
        self.assertEqual(len(core.load_data()['audios']),707)
        self.assertEqual(len(self.queue.items),0)
        self.assertFalse(list(core.UPLOAD_DIR.glob('*.uploading')))

    def test_rename_preserves_ids_and_clips(self):
        before=core.load_data()
        core.api_rename_profile('p','Changed')
        after=core.load_data()
        self.assertEqual(after['profiles'][0]['name'],'Changed')
        self.assertEqual(after['audios'],before['audios'])
        self.assertEqual(after['clips'],before['clips'])

    def test_batch_hides_internal_objects(self):
        first=self.upload(b'unique')
        jobs=core.api_jobs_batch(core.JobBatchRequest(ids=[first['job_id'],'missing']))['jobs']
        self.assertNotIn('missing',jobs)
        self.assertNotIn('_future',jobs[first['job_id']])
