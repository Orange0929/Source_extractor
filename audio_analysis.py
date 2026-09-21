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


_fcpe_model = None


def _get_fcpe():
    global _fcpe_model
    if _fcpe_model is None:
        import torch
        from torchfcpe import spawn_bundled_infer_model
        # CPU is predictable on Windows without a separate CUDA installation.
        torch.set_num_threads(min(4, torch.get_num_threads()))
        _fcpe_model = spawn_bundled_infer_model(device="cpu")
        _fcpe_model.eval()
    return _fcpe_model


def pitch(samples, start):
    import torch
    if len(samples) < 1024 or np.max(np.abs(samples)) < 0.0001:
        return {"points": [], "method": "FCPE"}
    model = _get_fcpe()
    frame_seconds = model.get_hop_size() / model.get_model_sr()
    # Use native frame spacing: stretching outputs to the requested duration
    # would shift the curve on clips whose length is not a hop-size multiple.
    waveform = torch.from_numpy(np.asarray(samples, dtype=np.float32).copy()).reshape(1, -1, 1)
    with torch.inference_mode():
        frequencies = model.infer(
            waveform, sr=RATE, decoder_mode="local_argmax",
            threshold=0.006, interp_uv=False,
        ).reshape(-1).cpu().numpy()
    points = []
    for i, hz in enumerate(frequencies):
        relative = i * frame_seconds
        if relative >= len(samples) / RATE:
            break
        # An absolute silence gate; do not suppress quiet endings relative to
        # the loudest syllable, or interpolate through unvoiced consonants.
        center = round(relative * RATE)
        window = samples[max(0, center-160):min(len(samples), center+161)]
        audible = len(window) and float(np.sqrt(np.mean(window ** 2))) > 0.0001
        valid = np.isfinite(hz) and hz > 0 and audible
        points.append([round(start+relative, 6), round(float(hz), 3) if valid else None])
    return {"points": points, "method": "FCPE"}
