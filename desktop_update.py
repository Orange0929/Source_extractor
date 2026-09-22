"""GitHub main updater. Code/runtime staging never overwrites user data."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
import zipfile

REPOSITORY = 'Orange0929/Source_extractor'
API_URL = f'https://api.github.com/repos/{REPOSITORY}/commits/main'
SHA = re.compile(r'^[0-9a-f]{40}$')
REQUIRED = ('app.py', 'app_fixed.py', 'desktop_app.py', 'desktop_server.py',
            'desktop_update.py', 'desktop_launcher.py', 'requirements.txt',
            'requirements-desktop.txt', 'templates/index.html', 'static/app.js', 'static/desktop_ui.js')
MAX_ARCHIVE = 100 * 1024 * 1024
MAX_UNPACKED = 300 * 1024 * 1024


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def read_state(root):
    path = Path(root) / '.desktop' / 'state.json'
    if not path.exists():
        return {'current': {'code': '.', 'runtime': '.venv', 'sha': None}}
    return json.loads(path.read_text(encoding='utf-8'))


def local_path(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError('설치 폴더 밖의 경로는 사용할 수 없습니다.')
    return path


def python_in(runtime, windowless=False):
    if os.name == 'nt':
        return Path(runtime) / 'Scripts' / ('pythonw.exe' if windowless else 'python.exe')
    return Path(runtime) / 'bin' / 'python'


def network_request(url):
    return urllib.request.Request(url, headers={'User-Agent': 'SourceExtractor-Desktop',
        'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'})


def latest_revision():
    try:
        with urllib.request.urlopen(network_request(API_URL), timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            raise RuntimeError('GitHub 요청 제한에 도달했습니다. 잠시 후 다시 확인하세요.') from exc
        raise RuntimeError(f'GitHub 업데이트 확인 실패 (HTTP {exc.code})') from exc
    sha = result.get('sha', '')
    if not SHA.fullmatch(sha):
        raise ValueError('GitHub 버전 응답이 올바르지 않습니다.')
    return {'sha': sha, 'message': result['commit']['message'].splitlines()[0],
            'url': f'https://github.com/{REPOSITORY}/commit/{sha}'}


def download_revision(sha, target, progress):
    if not SHA.fullmatch(sha):
        raise ValueError('Invalid revision')
    url = f'https://codeload.github.com/{REPOSITORY}/zip/{sha}'
    with urllib.request.urlopen(network_request(url), timeout=60) as response, open(target, 'wb') as out:
        size = 0
        while block := response.read(256 * 1024):
            size += len(block)
            if size > MAX_ARCHIVE:
                raise ValueError('업데이트 파일 크기가 제한을 초과했습니다.')
            out.write(block)
            progress(f'GitHub에서 다운로드 중… {size/1024/1024:.1f} MB')


def extract_revision(archive, destination, sha):
    """Reject traversal, links, multiple roots and oversized ZIPs before writing."""
    with zipfile.ZipFile(archive) as z:
        entries = z.infolist()
        if len(entries) > 10000 or sum(i.file_size for i in entries) > MAX_UNPACKED:
            raise ValueError('업데이트 압축 파일이 너무 큽니다.')
        prefix = f'Source_extractor-{sha}'
        for info in entries:
            path = PurePosixPath(info.filename)
            if (not path.parts or path.parts[0] != prefix or path.is_absolute()
                    or '..' in path.parts or '\\' in info.filename or ':' in info.filename
                    or ((info.external_attr >> 16) & 0o170000) == 0o120000):
                raise ValueError('업데이트 압축 파일 경로가 올바르지 않습니다.')
        for info in entries:
            parts = PurePosixPath(info.filename).parts[1:]
            if not parts:
                continue
            target = destination.joinpath(*parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as source, target.open('wb') as output:
                    shutil.copyfileobj(source, output)
    for name in REQUIRED:
        if not (destination/name).is_file():
            raise ValueError(f'업데이트 필수 파일 누락: {name}')
    for file in destination.glob('*.py'):
        compile(file.read_bytes(), str(file), 'exec')


def dependency_key(code):
    digest = hashlib.sha256()
    for name in ('requirements.txt', 'requirements-desktop.txt'):
        # CRLF from Windows ZIP/checkouts must not cause a large runtime reinstall.
        digest.update((Path(code)/name).read_text(encoding='utf-8').replace('\r\n','\n').encode())
    return digest.hexdigest()


def run_install(command, log):
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    with open(log, 'a', encoding='utf-8') as output:
        subprocess.run([str(arg) for arg in command], stdout=output, stderr=subprocess.STDOUT,
                       check=True, timeout=3600, creationflags=flags)


def prepare_runtime(root, code, current, progress):
    current_code = local_path(root, current['code'])
    if dependency_key(code) == dependency_key(current_code):
        return current['runtime']
    # Dependency upgrades happen in a separate venv, leaving the running and
    # previous versions usable even if pip or the download fails halfway.
    relative = f'.desktop/runtimes/{dependency_key(code)}'
    runtime = local_path(root, relative)
    marker = runtime / 'install-complete.json'
    if marker.exists():
        return relative
    if runtime.exists():
        shutil.rmtree(runtime)
    progress('실행 구성 요소 변경 감지: 별도 환경에 설치 중… update.log에서 진행 확인 가능')
    log = Path(root)/'.desktop'/'update.log'
    base_python = getattr(sys, '_base_executable', sys.executable)
    try:
        run_install([base_python, '-m', 'venv', runtime], log)
        python = python_in(runtime)
        run_install([python, '-m', 'pip', 'install', '--upgrade', 'pip'], log)
        cpu_packages = [line.strip() for line in (code/'requirements.txt').read_text().splitlines()
                        if re.fullmatch(r'(torch|torchaudio)==[0-9][A-Za-z0-9.+-]*',line.strip())]
        if cpu_packages:
            run_install([python, '-m', 'pip', 'install', *cpu_packages,
                         '--index-url', 'https://download.pytorch.org/whl/cpu'], log)
        run_install([python, '-m', 'pip', 'install', '-r', code/'requirements-desktop.txt'], log)
        run_install([python, '-c', 'import webview, uvicorn, faster_whisper, torchfcpe'], log)
        run_install([python, '-c',
                     'import sys; sys.path.insert(0, sys.argv[1]); '
                     'from korean_pronunciation import pronounce; '
                     'assert pronounce("학교") == "학꾜"', str(code)], log)
        atomic_json(marker, {'complete': True})
    except Exception:
        shutil.rmtree(runtime, ignore_errors=True)
        raise
    return relative


def stage_update(root, sha, progress):
    root = Path(root).resolve()
    state = read_state(root)
    if state['current'].get('sha') == sha:
        return state['current']
    folder = root/'.desktop'
    folder.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='download-', dir=folder) as temp:
        temp = Path(temp)
        archive = temp/'source.zip'
        download_revision(sha, archive, progress)
        code = temp/'code'; code.mkdir()
        progress('업데이트 파일 확인 중…')
        extract_revision(archive, code, sha)
        runtime = prepare_runtime(root, code, state['current'], progress)
        relative = f'.desktop/versions/{sha}'
        target = local_path(root, relative)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            code.replace(target)
        # Publish a candidate only after every download, validation and install.
        candidate = {'code': relative, 'runtime': runtime, 'sha': sha}
        state = read_state(root)
        state['pending'] = candidate
        atomic_json(folder/'state.json', state)
    progress('설치 준비 완료. 재시작하면 적용됩니다.')
    return candidate
