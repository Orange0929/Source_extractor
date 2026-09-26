"""Read failures must preserve the database rather than silently reset it."""
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault('faster_whisper', types.SimpleNamespace(WhisperModel=object))
import app as core

class ReadSafety(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root/'uploads').mkdir()
        for key, value in [('DATA_DIR', self.root), ('DATA_PATH', self.root/'data.json'), ('UPLOAD_DIR',self.root/'uploads')]:
            p=patch.object(core,key,value); p.start(); self.addCleanup(p.stop)

    def test_valid_and_new_database(self):
        self.assertEqual(core.load_data(), dict(profiles=[],audios=[],clips=[]))
        data=dict(profiles=[{'id':'p'}],audios=[],clips=[])
        core.DATA_PATH.write_text(json.dumps(data),encoding='utf-8-sig')
        self.assertEqual(core.load_data(),data)

    def test_permission_error_never_moves_valid_file(self):
        raw=b'{"profiles":[],"audios":[],"clips":[]}'
        core.DATA_PATH.write_bytes(raw)
        with patch.object(Path,'read_text',side_effect=PermissionError('locked')):
            with self.assertRaises(core.HTTPException): core.load_data()
        self.assertEqual(core.DATA_PATH.read_bytes(),raw)
        self.assertFalse(list(self.root.glob('data.broken.*')))

    def test_invalid_or_empty_data_preserved(self):
        for raw in [b'',b'{',b'[]',b'{}']:
            core.DATA_PATH.write_bytes(raw)
            with self.assertRaises(core.HTTPException): core.load_data()
            self.assertEqual(core.DATA_PATH.read_bytes(),raw)

    def test_missing_database_with_existing_uploads_is_not_new_install(self):
        (core.UPLOAD_DIR/'original.wav').write_bytes(b'audio')
        with self.assertRaises(core.HTTPException): core.load_data()

    def test_missing_database_with_recovery_file_is_not_new_install(self):
        (self.root/'data.broken.20260101.json').write_text('{}')
        with self.assertRaises(core.HTTPException): core.load_data()

if __name__=='__main__': unittest.main()
