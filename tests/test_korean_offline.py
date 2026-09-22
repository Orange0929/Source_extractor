"""Fresh-process initialization must not install or download resources."""
import subprocess
import sys
from pathlib import Path
import unittest


class OfflineInitializationTest(unittest.TestCase):
    def test_no_runtime_network_or_installer(self):
        code = '''
from unittest.mock import patch
with patch('nltk.download', side_effect=AssertionError('download')), \
     patch('subprocess.Popen', side_effect=AssertionError('installer')):
    from korean_pronunciation import pronounce
    assert pronounce('학교') == '학꾜'
    assert pronounce('같이') == '가치'
'''
        result = subprocess.run([sys.executable, '-c', code],
                                cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
