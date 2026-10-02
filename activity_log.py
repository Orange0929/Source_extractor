"""Bounded diagnostic events; no audio content or transcript text."""
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import threading
from datetime import datetime

_lock = threading.Lock()
_loggers = {}

def event(root, action, **fields):
    try:
        path = Path(root) / '.desktop' / 'activity.jsonl'
        with _lock:
            key = str(path.resolve())
            if key not in _loggers:
                path.parent.mkdir(parents=True, exist_ok=True)
                logger = logging.getLogger('source.activity.' + key)
                logger.setLevel(logging.INFO)
                logger.propagate = False
                handler = RotatingFileHandler(path, maxBytes=2*1024*1024, backupCount=3, encoding='utf-8')
                handler.setFormatter(logging.Formatter('%(message)s'))
                logger.addHandler(handler)
                _loggers[key] = logger
            _loggers[key].info(json.dumps(dict(time=datetime.now().astimezone().isoformat(), event=action, **fields), ensure_ascii=False, default=str))
    except Exception:
        logging.getLogger(__name__).exception('Could not write diagnostic event')

def inventory(root):
    root = Path(root)
    data = json.loads((root/'data.json').read_text(encoding='utf-8-sig'))
    profiles = {p['id']:p.get('name') for p in data['profiles']}
    counts = {}
    for clip in data['clips']:
        aid = clip.get('audio_id'); counts[aid] = counts.get(aid, 0) + 1
    return {'data_path':str(root/'data.json'), 'profiles':data['profiles'],
            'clip_count':len(data['clips']), 'audios':[
                {**{k:a.get(k) for k in ('id','profile_id','orig_filename','path','created_at','stt_status','stt_message','upload_batch_id')},
                 'profile_name':profiles.get(a.get('profile_id')), 'clips':counts.get(a['id'],0),
                 'original_exists':(root/'uploads'/a['path']).is_file()}
                for a in data['audios']]}
