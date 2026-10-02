import json
from pathlib import Path
from unittest.mock import patch
from test_retry_incomplete import RecoveryTests
import app as core
import activity_log

class MoveTests(RecoveryTests):
    def setUp(self):
        super().setUp()
        p=patch.object(core,'DATA_DIR',core.DATA_PATH.parent);p.start();self.addCleanup(p.stop)

    def test_move_preserves_ids_files_and_updates_all_clips(self):
        before=core.load_data(); original=(core.UPLOAD_DIR/'edited.wav').read_bytes()
        result=core.api_move_audios(core.MoveAudiosRequest(source_profile_id='p',target_profile_id='q',audio_ids=['edited','failed']))
        after=core.load_data()
        self.assertEqual(result,dict(ok=True,audios=2,clips=1))
        self.assertEqual(next(a for a in after['audios'] if a['id']=='edited')['profile_id'],'q')
        self.assertEqual(next(c for c in after['clips'] if c['audio_id']=='edited')['profile_id'],'q')
        self.assertEqual(next(c for c in after['clips'] if c['audio_id']=='edited')['transcript'],'manual')
        self.assertEqual((core.UPLOAD_DIR/'edited.wav').read_bytes(),original)
        backup=next(core.DATA_DIR.glob('data.before-move.*.json'))
        self.assertEqual(json.loads(backup.read_text()),before)
        log=(core.DATA_DIR/'.desktop/activity.jsonl').read_text()
        self.assertIn('audio_move',log)
        core.api_move_audios(core.MoveAudiosRequest(source_profile_id='q',target_profile_id='p',audio_ids=['edited','failed']))
        self.assertEqual(core.load_data(),before)

    def test_active_and_stale_selection_rejected(self):
        before=core.load_data()
        core.set_job('busy',audio_id='failed',status='running')
        for ids in [['failed'],['other'],['missing-id']]:
            with self.assertRaises(core.HTTPException):
                core.api_move_audios(core.MoveAudiosRequest(source_profile_id='p',target_profile_id='q',audio_ids=ids))
        self.assertEqual(core.load_data(),before)

    def test_windows_replace_retry_preserves_data(self):
        data=core.load_data(); original=Path.replace; tries=[]
        def replace(path,target):
            tries.append(1)
            if len(tries)<3: raise PermissionError('temporary Windows lock')
            return original(path,target)
        with patch.object(Path,'replace',replace),patch.object(core.time,'sleep'):
            core.save_data_atomic(data)
        self.assertEqual(len(tries),3)
        self.assertEqual(core.load_data(),data)

    def test_inventory_has_mapping_without_transcripts(self):
        # Inventory expects the production uploads subdirectory.
        (core.DATA_DIR/'uploads').mkdir()
        snapshot=activity_log.inventory(core.DATA_DIR)
        self.assertEqual(len(snapshot['audios']),8)
        self.assertEqual(snapshot['clip_count'],2)
        self.assertNotIn('transcript',json.dumps(snapshot))
