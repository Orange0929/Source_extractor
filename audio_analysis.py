"""Display-only waveform and monophonic F0 analysis; never changes source audio."""
import subprocess
import numpy as np

RATE = 16000


def read_audio(path, start, end):
    raw = subprocess.check_output([
        'ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
        '-ss', f'{start:.6f}', '-i', str(path), '-t', f'{end-start:.6f}',
        '-vn', '-ac', '1', '-ar', str(RATE), '-f', 'f32le', 'pipe:1',
    ], timeout=120)
    return np.frombuffer(raw, dtype='<f4').copy()


def envelope(samples, bins=16000):
    if not len(samples):
        return {'peaks': [], 'rms': [], 'gain': 1.0}
    # Equal time buckets, including the final partial bucket.
    edges = np.linspace(0, len(samples), min(bins, len(samples)) + 1, dtype=int)
    magnitude = np.abs(samples)
    peaks = np.maximum.reduceat(magnitude, edges[:-1])
    sums = np.concatenate(([0.0], np.cumsum(samples.astype(float) ** 2)))
    rms = np.sqrt(np.maximum(0, np.diff(sums[edges])) / np.diff(edges))
    gain = min(32.0, 0.9 / max(float(np.max(peaks)), 0.0001))
    return {'peaks': np.round(peaks, 5).tolist(),
            'rms': np.round(rms, 5).tolist(), 'gain': gain}


def pitch(samples, start):
    import librosa
    if len(samples) < 1024 or np.max(np.abs(samples)) < 0.0001:
        return {'points': [], 'method': 'pYIN'}
    hop = 320  # 20ms; timestamps use centered frames, same origin as waveform.
    f0, voiced, probability = librosa.pyin(
        samples, sr=RATE, fmin=65.4, fmax=1046.5,
        frame_length=1024, hop_length=hop, fill_na=np.nan,
    )
    rms = librosa.feature.rms(y=samples, frame_length=1024, hop_length=hop)[0]
    floor = max(0.0001, float(np.max(rms)) * 0.015)
    points = []
    for i, hz in enumerate(f0):
        relative = i * hop / RATE
        if relative >= len(samples) / RATE:
            break
        valid = bool(voiced[i] and np.isfinite(hz) and probability[i] >= 0.15 and rms[i] > floor)
        points.append([round(start + relative, 6), round(float(hz), 3) if valid else None])
    return {'points': points, 'method': 'pYIN'}
