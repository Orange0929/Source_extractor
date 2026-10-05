import io
import sys
import tempfile
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desktop_app import DesktopApi

class Response(io.BytesIO):
    def __init__(self, data, length):
        super().__init__(data)
        self.headers={'Content-Length':str(length)}
    def read(self,n=-1):
        if self.tell() == len(self.getvalue()):
            raise TimeoutError('server did not close connection')
        return super().read(n)

class ExportFailureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.target=self.root/'어라.wav'
        self.api=DesktopApi(self.root,'http://localhost','token')
        self.api._window=types.SimpleNamespace(create_file_dialog=lambda *a,**k:str(self.target))
        for p in (patch.object(self.api,'_trusted',return_value=True),patch.dict(sys.modules,webview=types.SimpleNamespace(SAVE_DIALOG=1))):
            p.start();self.addCleanup(p.stop)

    def save(self,response):
        with patch('desktop_app.urllib.request.urlopen',side_effect=[io.BytesIO(b'{"extension":"wav"}'),response]):
            return self.api.save_audio_range(str(uuid.uuid4()),0,1,'어라')

    def test_content_length_finishes_without_waiting_for_connection_close(self):
        # Update lock must not prevent remembering the export directory.
        self.api._lock.acquire()
        try:
            result=self.save(Response(b'audio',5))
        finally:self.api._lock.release()
        self.assertTrue(result['ok'])
        self.assertEqual(self.target.read_bytes(),b'audio')
        self.assertEqual(list(self.root.glob('*.partial')),[])

    def test_incomplete_transfer_preserves_existing_file(self):
        self.target.write_bytes(b'old')
        result=self.save(Response(b'ab',5))
        self.assertIn('error',result)
        self.assertEqual(self.target.read_bytes(),b'old')
        self.assertEqual(list(self.root.glob('*.partial')),[])

    def test_locked_cleanup_does_not_escape_bridge(self):
        with patch.object(Path,'unlink',side_effect=PermissionError('locked')):
            result=self.save(Response(b'ab',5))
        self.assertIn('error',result)
        events=(self.root/'.desktop/activity.jsonl').read_text()
        self.assertIn('audio_export_failed',events)
        self.assertIn('audio_export_cleanup_failed',events)

    def test_transient_replace_lock_retries(self):
        replace=Path.replace
        calls=[]
        def flaky(path,target):
            if path.suffix=='.partial':
                calls.append(path)
                if len(calls)==1:raise PermissionError('busy')
            return replace(path,target)
        with patch.object(Path,'replace',flaky),patch('desktop_app.time.sleep'):
            self.assertTrue(self.save(Response(b'audio',5))['ok'])
        self.assertEqual(len(calls),2)

if __name__=='__main__':unittest.main()
