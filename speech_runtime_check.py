"""Decode real WAV bytes through faster-whisper without downloading any model."""
import io
from importlib.metadata import version
import wave


def check_audio_decoder():
    from faster_whisper.audio import decode_audio
    audio = io.BytesIO()
    with wave.open(audio, 'wb') as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(b'\0\0' * 1600)
    audio.seek(0)
    try:
        samples = decode_audio(audio, sampling_rate=16000)
        if len(samples) != 1600:
            raise RuntimeError(f'Expected 1600 samples, decoded {len(samples)}')
    except Exception as exc:
        raise RuntimeError('Speech audio decode check failed '
            f'(faster-whisper={version("faster-whisper")}, av={version("av")}): {exc}. '
            'Reinstall the pinned requirements before transcribing audio.') from exc
    print(f'Audio decode OK: faster-whisper={version("faster-whisper")}, av={version("av")}', flush=True)


if __name__ == '__main__':
    check_audio_decoder()
