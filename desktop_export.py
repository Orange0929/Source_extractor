"""Native range export using the same sample timeline as the backend, without HTTP."""
import json
import math
import os
from pathlib import Path
import subprocess
import uuid

CODECS = {'wav':['-c:a','pcm_s16le'], 'mp3':['-c:a','libmp3lame','-q:a','2'],
          'flac':['-c:a','flac'], 'm4a':['-c:a','aac','-b:a','192k'],
          'aac':['-c:a','aac','-b:a','192k'], 'ogg':['-c:a','libvorbis','-q:a','5']}


def source_info(root, audio_id):
    root = Path(root)
    data = json.loads((root/'data.json').read_text(encoding='utf-8-sig'))
    audio = next((a for a in data['audios'] if a.get('id') == audio_id), None)
    if audio is None:
        raise ValueError('원본 오디오 정보를 찾을 수 없습니다.')
    uploads = (root/'uploads').resolve()
    source = (uploads/audio['path']).resolve()
    if not source.is_relative_to(uploads) or not source.is_file():
        raise ValueError('원본 오디오 파일을 찾을 수 없습니다.')
    ext = source.suffix.lower().lstrip('.')
    return source, ext if ext in CODECS else 'wav'


def run_media(args, timeout):
    options = {'creationflags':subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    try:
        return subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True,
                              check=True, timeout=timeout, **options).stdout
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b'').decode('utf-8', errors='replace')[-2000:]
        raise RuntimeError(f'{args[0]} 실패: {detail}') from exc
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f'{args[0]} 처리 시간이 {timeout}초를 초과했습니다.') from exc


def render_range(root, source, start, end, ext, destination):
    if not all(math.isfinite(n) for n in (start,end)) or start < 0 or end-start < .01:
        raise ValueError('올바른 구간을 선택하세요.')
    timeline_dir = Path(root)/'timeline_cache'
    timeline_dir.mkdir(exist_ok=True)
    timeline = timeline_dir/(source.stem+'.timeline.flac')
    if not timeline.is_file() or timeline.stat().st_size == 0:
        temporary = timeline.with_name(source.stem+'.'+uuid.uuid4().hex+'.tmp.flac')
        try:
            run_media(['ffmpeg','-nostdin','-y','-hide_banner','-loglevel','error',
                       '-i',str(source),'-map','0:a:0','-vn','-sn','-dn',
                       '-af','aresample=44100,asetpts=N/SR/TB','-ar','44100',
                       '-ac','2','-sample_fmt','s16','-c:a','flac',str(temporary)],120)
            temporary.replace(timeline)
        finally:
            try: temporary.unlink(missing_ok=True)
            except OSError: pass
    duration = float(run_media(['ffprobe','-v','error','-show_entries','format=duration',
        '-of','default=noprint_wrappers=1:nokey=1',str(timeline)],15).decode().strip())
    end = min(end,duration)
    if end-start < .01:
        raise ValueError('선택 구간이 원본 길이를 벗어났습니다.')
    run_media(['ffmpeg','-nostdin','-y','-hide_banner','-loglevel','error',
               '-ss',f'{start:.6f}','-i',str(timeline),'-t',f'{end-start:.6f}',
               '-vn',*CODECS[ext],str(destination)],180)
    size = Path(destination).stat().st_size
    if size <= 0:
        raise IOError('추출된 오디오가 비어 있습니다.')
    return size
