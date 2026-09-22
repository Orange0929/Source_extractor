"""Portable, versioned pitch results, identified by original audio bytes."""
import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
import uuid

VERSION = 'fcpe-0.0.4-timeline-v1'


@lru_cache(maxsize=128)
def _digest(path, size, modified):
    with open(path, 'rb') as source:
        digest = hashlib.sha256()
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
        return digest.hexdigest()


def fingerprint(path):
    path = Path(path).resolve()
    stat = path.stat()
    return _digest(str(path), stat.st_size, stat.st_mtime_ns)


def key(digest, start, end):
    return hashlib.sha256(f'{VERSION}|{digest}|{start:.6f}|{end:.6f}'.encode()).hexdigest()


def valid(result, digest=None):
    try:
        start, end = result['start'], result['end']
        source = result['source_sha256']
        if result['analysis_version'] != VERSION or result['method'] != 'FCPE':
            return False
        if not isinstance(source, str) or len(source) != 64 or any(c not in '0123456789abcdef' for c in source):
            return False
        if digest is not None and source != digest:
            return False
        if not all(math.isfinite(t) for t in (start, end)) or start < 0 or not .01 <= end-start <= 90:
            return False
        points = result['points']
        if not isinstance(points, list) or len(points) > 20000:
            return False
        previous = start - .05
        for time, hz in points:
            if not math.isfinite(time) or not start-.05 <= time <= end+.05 or time < previous:
                return False
            if hz is not None and (not math.isfinite(hz) or not 0 < hz < 24000):
                return False
            previous = time
        return True
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def read(path, digest=None):
    try:
        result = json.loads(path.read_text(encoding='utf-8'))
        return result if valid(result, digest) else None
    except (OSError, ValueError):
        return None


def save(directory, result, digest):
    result = dict(result, source_sha256=digest, analysis_version=VERSION)
    if not valid(result, digest):
        raise ValueError('Invalid pitch result')
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (key(digest, result['start'], result['end']) + '.json')
    tmp = target.with_suffix('.' + uuid.uuid4().hex + '.tmp')
    try:
        tmp.write_text(json.dumps(result, allow_nan=False), encoding='utf-8')
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)
    return target


def legacy_key(src, start, end):
    stat = src.stat()
    return hashlib.sha256(f'analysis-fcpe-v1|{src}|{stat.st_size}|{stat.st_mtime_ns}|{start:.6f}|{end:.6f}|pitch'.encode()).hexdigest()


def migrate(directory, src, digest):
    """Only migrate legacy files whose key proves they belong to this source."""
    for path in directory.glob('*.json'):
        try:
            result = json.loads(path.read_text(encoding='utf-8'))
            if result.get('method') != 'FCPE':
                continue
            if path.stem == legacy_key(src, result['start'], result['end']):
                save(directory / 'pitch', result, digest)
        except (OSError, ValueError, KeyError, TypeError):
            continue
