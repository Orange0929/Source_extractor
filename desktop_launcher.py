"""Stable, stdlib-only launcher. Keep this file in the original install folder."""
from __future__ import annotations
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parent
STATE = ROOT/'.desktop'/'state.json'
RESTART = 75


def message(text):
    if os.name == 'nt':
        ctypes.windll.user32.MessageBoxW(None, text, 'Source Extractor', 0x10)
    else:
        print(text, file=sys.stderr)


def load_state(root=ROOT):
    path = root/'.desktop'/'state.json'
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    return {'current': {'code': '.', 'runtime': '.venv', 'sha': None}}


def write_state(root, state):
    path = root/'.desktop'/'state.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def resolve(root, relative):
    path = (root/relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Invalid application path')
    return path


def launch_choice(state):
    return state.get('pending') or state['current']


def commit_started(state, candidate):
    if state.get('pending') == candidate:
        state['previous'] = state['current']
        state['current'] = state.pop('pending')
    return state


def rollback_failed(state, candidate):
    if state.get('pending') == candidate:
        state.pop('pending')
        return state, True
    if state.get('previous') and state['previous'] != candidate:
        state['current'] = state.pop('previous')
        return state, True
    return state, False


def single_instance(root):
    if os.name != 'nt':
        return None
    import hashlib
    name = 'Local\\SourceExtractor-' + hashlib.sha256(str(root).lower().encode()).hexdigest()[:24]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel.CreateMutexW(None, False, name)
    if not handle:
        raise OSError('앱 실행 잠금을 만들 수 없습니다.')
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle(handle)
        raise RuntimeError('Source Extractor가 이미 실행 중입니다. 열려 있는 앱 창을 확인하세요.')
    return handle


def main():
    lock = single_instance(ROOT)
    folder = ROOT/'.desktop'; folder.mkdir(exist_ok=True)
    try:
        if '--browser' in sys.argv:
            current = load_state()['current']
            code = resolve(ROOT,current['code']);runtime = resolve(ROOT,current['runtime'])
            python = runtime/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
            env = dict(os.environ,SOURCE_EXTRACTOR_DATA_DIR=str(ROOT))
            subprocess.run([str(python),'-m','uvicorn','app_fixed:app','--host','127.0.0.1','--port','8000'],cwd=code,env=env,check=True)
            return
        while True:
            state = load_state()
            candidate = launch_choice(state)
            code = resolve(ROOT, candidate['code'])
            runtime = resolve(ROOT, candidate['runtime'])
            python = runtime/('Scripts/pythonw.exe' if os.name == 'nt' else 'bin/python')
            ready = folder/('ready-'+uuid.uuid4().hex+'.json')
            env = dict(os.environ, SOURCE_EXTRACTOR_HOME=str(ROOT),
                       SOURCE_EXTRACTOR_DATA_DIR=str(ROOT), SOURCE_EXTRACTOR_READY=str(ready),
                       SOURCE_EXTRACTOR_REVISION=candidate.get('sha') or 'local',
                       SOURCE_EXTRACTOR_LAUNCHER='1', PYTHONIOENCODING='utf-8')
            started = False
            try:
                with (folder/'app.log').open('a', encoding='utf-8') as log:
                    process = subprocess.Popen([str(python), str(code/'desktop_app.py')], cwd=code,
                        env=env, stdout=log, stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                    deadline = time.monotonic()+240
                    # UI-ready handshake is emitted only after the JS bridge loads.
                    while process.poll() is None:
                        if not started and time.monotonic()>deadline:
                            if os.name == 'nt':
                                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],
                                    stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW,timeout=15)
                            else: process.terminate()
                            process.wait(timeout=15)
                            break
                        if not started and ready.exists():
                            latest = load_state()
                            write_state(ROOT, commit_started(latest, candidate))
                            started = True
                        time.sleep(.2)
                    status = process.returncode
                    if not started and ready.exists():
                        write_state(ROOT, commit_started(load_state(), candidate)); started = True
            except OSError:
                status = 1
            finally:
                ready.unlink(missing_ok=True)
            if started:
                if status == RESTART:
                    continue
                if status != 0:
                    message('앱이 종료되었습니다. 설치 폴더의 .desktop/app.log를 확인하세요.')
                break
            if status == 0:
                break
            state, retry = rollback_failed(load_state(), candidate)
            write_state(ROOT, state)
            if retry:
                message('새 버전을 시작하지 못해 이전 버전으로 복구합니다. .desktop/app.log에서 원인을 확인할 수 있습니다.')
                continue
            message('앱을 시작하지 못했습니다. install_windows.bat을 실행하고 .desktop/app.log를 확인하세요. Windows의 Microsoft Edge WebView2 Runtime도 필요합니다.')
            break
    finally:
        if lock:
            kernel = ctypes.WinDLL('kernel32'); kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel.CloseHandle(lock)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        message(str(exc))
