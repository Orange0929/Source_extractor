import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audio_analysis import RATE, envelope, pitch


class AudioAnalysisTests(unittest.TestCase):
    def test_pitch_timing_and_unvoiced_gap(self):
        t = np.arange(RATE) / RATE
        audio = np.concatenate([.2*np.sin(2*np.pi*220*t), np.zeros(RATE//2),
                                .1*np.sin(2*np.pi*440*t)]).astype(np.float32)
        points = pitch(audio, 104.26)['points']
        for start, end, expected in [(104.4,105.0,220), (105.9,106.6,440)]:
            values = [hz for at,hz in points if start < at < end and hz]
            self.assertTrue(values)
            self.assertLess(abs(float(np.median(values))-expected), 3)
        self.assertTrue(all(hz is None for at,hz in points if 105.4 < at < 105.65))
        self.assertLess(points[-1][0], 106.76)

    def test_envelope_keeps_final_peak(self):
        audio = np.zeros(1001, dtype=np.float32)
        audio[-1] = .4
        result = envelope(audio, bins=100)
        self.assertEqual(len(result['peaks']), 100)
        self.assertAlmostEqual(result['peaks'][-1], .4, places=5)
        self.assertTrue(all(x == 0 for x in result['peaks'][:-1]))
        self.assertLessEqual(max(result['peaks'])*result['gain'], .901)

    def test_silence(self):
        self.assertEqual(pitch(np.zeros(RATE), 0)['points'], [])
        self.assertFalse(any(envelope(np.zeros(1000))['peaks']))


if __name__ == '__main__':
    unittest.main()
