"""Desktop update transaction tests: no GUI, network, pip or AI models needed."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import desktop_update as update
import desktop_launcher as launcher
from desktop_app import DesktopApi

SHA = 'a'*40


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root.joinpath('requirements.txt').write_text('numpy\n')
        self.root.joinpath('requirements-desktop.txt').write_text('-r requirements.txt\npywebview==6.2.1\n')
        for name in ['uploads','timeline_cache','waveform_cache','clips_cache']:
            (self.root/name).mkdir();(self.root/name/'keep').write_bytes(b'unchanged')
        (self.root/'data.json').write_text('{"profiles":[{"id":"original"}]}')
        self.data = {p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.archive = self.root/'fixture.zip'
        self.zip()

    def zip(self, extras=None, changed_deps=False):
        with zipfile.ZipFile(self.archive,'w') as z:
            for name in update.REQUIRED:
                content = ''
                if name.startswith('requirements'):
                    content = (self.root/name).read_text()
                    if changed_deps: content += '# changed\n'
                z.writestr(f'Source_extractor-{SHA}/{name}', content)
            for name,content in (extras or {}).items(): z.writestr(name,content)

    def download(self, sha, target, progress):
        self.assertEqual(sha,SHA);shutil.copyfile(self.archive,target)

    def check_data(self):
        for path,content in self.data.items(): self.assertEqual((self.root/path).read_bytes(),content)

    def test_stage_preserves_data_and_current_runtime(self):
        with patch.object(update,'download_revision',side_effect=self.download), patch.object(update,'run_install',side_effect=AssertionError('No reinstall for code-only update')):
            candidate=update.stage_update(self.root,SHA,lambda _:None)
        state=update.read_state(self.root)
        self.assertEqual(state['current']['code'],'.')
        self.assertEqual(state['pending'],candidate)
        self.assertEqual(candidate['runtime'],'.venv')
        self.assertTrue((self.root/candidate['code']/'desktop_app.py').exists())
        self.check_data()
        activated=launcher.commit_started(copy.deepcopy(state),candidate)
        self.assertEqual(activated['current'],candidate)
        self.assertEqual(activated['previous'],state['current'])
        self.assertNotIn('pending',activated)

    def test_failed_candidate_rolls_back_without_touching_data(self):
        old={'code':'.','runtime':'.venv','sha':None}
        candidate={'code':'.desktop/versions/'+SHA,'runtime':'.venv','sha':SHA}
        state={'current':old,'pending':candidate}
        fixed,retry=launcher.rollback_failed(state,candidate)
        self.assertTrue(retry);self.assertEqual(fixed['current'],old);self.assertNotIn('pending',fixed)
        self.check_data()

    def test_download_failure_publishes_nothing(self):
        with patch.object(update,'download_revision',side_effect=OSError('offline')):
            with self.assertRaises(OSError): update.stage_update(self.root,SHA,lambda _:None)
        self.assertNotIn('pending',update.read_state(self.root));self.check_data()

    def test_dependency_failure_keeps_current_version(self):
        self.zip(changed_deps=True)
        with patch.object(update,'download_revision',side_effect=self.download),patch.object(update,'run_install',side_effect=RuntimeError('pip failed')):
            with self.assertRaises(RuntimeError):update.stage_update(self.root,SHA,lambda _:None)
        self.assertNotIn('pending',update.read_state(self.root));self.check_data()

    def test_crlf_does_not_trigger_runtime_reinstall(self):
        second=self.root/'second';second.mkdir()
        for name in ['requirements.txt','requirements-desktop.txt']:
            (second/name).write_bytes((self.root/name).read_text().replace('\n','\r\n').encode())
        self.assertEqual(update.dependency_key(second),update.dependency_key(self.root))

    def test_reject_archive_traversal_and_wrong_revision(self):
        for name in [f'Source_extractor-{SHA}/../../data.json','Source_extractor-wrong/app.py',f'Source_extractor-{SHA}/C:/data.json']:
            self.zip({name:'bad'})
            with self.assertRaises(ValueError):update.extract_revision(self.archive,self.root/'out',SHA)
            self.assertFalse((self.root/'out').exists())
        self.check_data()

    def test_restart_waits_for_jobs_and_untrusted_page_cannot_update(self):
        api=DesktopApi(self.root,'http://127.0.0.1:8000','secret')
        self.assertIn('error',api.start_update())
        api._window=type('Window',(),{'get_current_url':lambda _: 'https://example.com/'})()
        self.assertIn('error',api.check_update())
        api._window=type('Window',(),{'get_current_url':lambda _: 'http://127.0.0.1:8000/'})()
        with patch.object(api,'_server',return_value={'ok':False,'busy':True}):
            self.assertFalse(api._can_close())
            self.assertFalse(api._closing)
        with patch.object(api,'_server',return_value={'ok':True,'busy':False}):
            self.assertTrue(api._can_close())

if __name__=='__main__':unittest.main()
