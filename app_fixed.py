from __future__ import annotations

import os
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

import app as core

# -----------------------------------------------------------------------------
# Long-audio timestamp fix
# -----------------------------------------------------------------------------
# faster-whisper decodes audio on a sample-count timeline, while the old clip
# cutter sought on the original container timestamps. Long/edited MP3/AAC/video
# sources can therefore drift. Build one canonical, sample-timed lossless audio
# file and use that exact timeline for BOTH STT and clip extraction.
TIMELINE_DIR = core.BASE_DIR / "timeline_cache"
TIMELINE_DIR.mkdir(exist_ok=True)
TIMELINE_LOCK = threading.Lock()

PAD_BEFORE_S = max(0.0, float(os.environ.get("CLIP_PAD_BEFORE_MS", "40")) / 1000.0)
PAD_AFTER_S = max(0.0, float(os.environ.get("CLIP_PAD_AFTER_MS", "70")) / 1000.0)

_ORIGINAL_SAVE_DATA = core.save_data


def timeline_path_for_source(src: Path) -> Path:
    return TIMELINE_DIR / f"{src.stem}.timeline.flac"


def ensure_timeline_audio(src: Path) -> Path:
    """Create a linear, sample-count based timeline shared by STT and cutting."""
    dst = timeline_path_for_source(src)
    if dst.exists() and dst.stat().st_size > 0:
        return dst

    # One global lock is intentionally simple: timeline creation only happens
    # once per source and avoids two requests racing to replace the same cache.
    with TIMELINE_LOCK:
        if dst.exists() and dst.stat().st_size > 0:
            return dst

        tmp = dst.with_name(f"{dst.stem}.{uuid.uuid4().hex}.tmp.flac")
        try:
            subprocess.check_call([
                "ffmpeg", "-y",
                "-hide_banner", "-loglevel", "error",
                "-i", str(src),
                "-map", "0:a:0",
                "-vn", "-sn", "-dn",
                # Ignore the source container's PTS and rebuild timestamps from
                # actual decoded samples. This is the key to matching Whisper.
                "-af", "aresample=44100,asetpts=N/SR/TB",
                "-ar", "44100",
                "-ac", "2",
                "-sample_fmt", "s16",
                "-c:a", "flac",
                str(tmp),
            ])
            tmp.replace(dst)
        finally:
            tmp.unlink(missing_ok=True)

    return dst


def extract_clip_fixed(src: Path, start_s: float, end_s: float, dst: Path):
    """Cut from the same canonical timeline used for transcription."""
    dst.parent.mkdir(parents=True, exist_ok=True)

    start_s = max(0.0, float(start_s))
    end_s = max(start_s + 0.01, float(end_s))
    dur_s = max(0.01, end_s - start_s)

    timeline = ensure_timeline_audio(src)

    # On the canonical FLAC, timestamps are linear and deterministic. Input-side
    # accurate seek is fast while ffmpeg still decodes/discards to the exact time.
    subprocess.check_call([
        "ffmpeg", "-y",
        "-hide_banner", "-loglevel", "error",
        "-ss", f"{start_s:.6f}",
        "-i", str(timeline),
        "-t", f"{dur_s:.6f}",
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "44100",
        "-ac", "2",
        str(dst),
    ])


def _segment_bounds(seg: Any) -> Tuple[float, float]:
    """Prefer word-level boundaries, then add tiny anti-cutoff padding."""
    words = []
    for word in (getattr(seg, "words", None) or []):
        if getattr(word, "start", None) is None or getattr(word, "end", None) is None:
            continue
        words.append(word)

    if words:
        start_s = float(words[0].start)
        end_s = float(words[-1].end)
    else:
        start_s = float(seg.start)
        end_s = float(seg.end)

    start_s = max(0.0, start_s - PAD_BEFORE_S)
    end_s = max(start_s + 0.01, end_s + PAD_AFTER_S)
    return start_s, end_s


def run_stt_job_fixed(job_id: str, profile_id: str, audio_id: str, saved_path: Path):
    cancel_ev = core._get_cancel_event(job_id)

    try:
        if cancel_ev.is_set():
            core.set_job(job_id, status="cancelled", progress=0, message="취소됨", clips_created=0)
            return

        core.set_job(
            job_id,
            status="running",
            progress=0,
            message="오디오 시간축 정규화 중...",
            clips_created=0,
        )

        timeline_path = ensure_timeline_audio(saved_path)
        duration = core.ffprobe_duration(timeline_path)

        if cancel_ev.is_set():
            core.set_job(job_id, status="cancelled", progress=0, message="취소됨", clips_created=0)
            return

        core.set_job(job_id, message="STT 분석 시작...")
        model = core.get_whisper_model()

        segments, info = model.transcribe(
            str(timeline_path),
            task="transcribe",
            language=None,
            # VAD timestamp remapping has known mismatch cases. For a source
            # extractor, timing correctness is more important than skipping
            # silence aggressively, so keep the original sample timeline.
            vad_filter=False,
            # Segment timestamps can start/end inside syllables. Word bounds +
            # small padding produce much cleaner source clips.
            word_timestamps=True,
            # Long files are less prone to context-loop timestamp desync when
            # each window does not condition on previous generated text.
            condition_on_previous_text=False,
        )

        created = 0
        last_p = 0.0
        new_clips: List[Dict[str, Any]] = []

        for seg in segments:
            if cancel_ev.is_set():
                core.set_job(
                    job_id,
                    status="cancelled",
                    progress=int(last_p * 100),
                    message="취소됨",
                    clips_created=created,
                )
                break

            text = (seg.text or "").strip()
            if not text:
                continue

            start_s, end_s = _segment_bounds(seg)
            if end_s - start_s < 0.15:
                continue

            clip = {
                "id": str(uuid.uuid4()),
                "profile_id": profile_id,
                "audio_id": audio_id,
                "start_s": start_s,
                "end_s": end_s,
                "transcript": text,
                "norm": core.norm_basic(text),
                "ko_pron_norm": core.norm_ko_sound(text),
                "jp_kana_norm": core.jp_kana_norm(text),
                "created_at": core.now_iso(),
            }
            new_clips.append(clip)
            created += 1

            if duration > 0:
                p = min(0.99, max(last_p, end_s / duration))
            else:
                p = min(0.99, max(last_p, 0.02 + created * 0.01))
            last_p = p

            core.set_job(
                job_id,
                progress=int(p * 100),
                message=f"STT 처리중... (구간 {created}개)",
                clips_created=created,
            )

        with core.DATA_LOCK:
            data = core.load_data()
            data["clips"].extend(new_clips)
            core.save_data(data)

        if cancel_ev.is_set():
            core.set_job(
                job_id,
                status="cancelled",
                progress=int(last_p * 100),
                message="취소됨",
                clips_created=created,
            )
        else:
            core.set_job(
                job_id,
                status="done",
                progress=100,
                message=f"완료! 클립 {created}개 생성",
                clips_created=created,
            )

    except Exception as exc:
        if cancel_ev.is_set():
            core.set_job(job_id, status="cancelled", progress=0, message="취소됨", clips_created=0)
        else:
            core.set_job(
                job_id,
                status="error",
                progress=0,
                message=f"에러: {type(exc).__name__}: {exc}",
                clips_created=0,
            )


def _cleanup_timeline_cache(data: Dict[str, Any]) -> None:
    valid_audio_ids = {
        Path(a.get("path") or "").stem
        for a in data.get("audios", [])
        if a.get("path")
    }

    for cached in TIMELINE_DIR.glob("*.timeline.flac"):
        audio_id = cached.name[:-len(".timeline.flac")]
        if audio_id not in valid_audio_ids:
            cached.unlink(missing_ok=True)


def save_data_fixed(data: Dict[str, Any]):
    _ORIGINAL_SAVE_DATA(data)
    try:
        _cleanup_timeline_cache(data)
    except Exception:
        # Cache cleanup must never make a DB save fail.
        pass


# Patch the globals used by the already-registered FastAPI endpoints.
core.extract_clip = extract_clip_fixed
core.audio_timeline_source = ensure_timeline_audio
core.audio_timeline_cached_source = timeline_path_for_source
core.run_stt_job = run_stt_job_fixed
core.save_data = save_data_fixed

try:
    _cleanup_timeline_cache(core.load_data())
except Exception:
    pass

app = core.app
