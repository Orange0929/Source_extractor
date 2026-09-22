"""Windows WebView2 host with a narrow local-only update bridge."""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path
import platform
import secrets
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from datetime import datetime

from desktop_update import (REPOSITORY, atomic_json, latest_revision, read_state,
                            stage_update)


class DesktopApi:
    def __init__(self, root, url, token):
        self._root = root; self._url = url; self._token = token
        self._window = None; self._restart = False; self._closing = False; self._process = None
        self._lock = threading.Lock(); self._status_lock = threading.Lock()
        self._latest = None
        self._close_reason = ''
        pending = read_state(root).get('pending')
        if pending and pending.get('sha') == os.environ.get('SOURCE_EXTRACTOR_REVISION'):
            pending = None
        self._status = {'phase':'ready' if pending else 'idle',
                        'message':'설치 준비 완료. 재시작하면 적용됩니다.' if pending else '',
                        'version':os.environ.get('SOURCE_EXTRACTOR_REVISION','local')[:8]}

    def _trusted(self):
        return bool(not self._closing and self._window and (self._window.get_current_url() or '').split('?')[0].rstrip('/') == self._url)

    def _set(self, phase, message):
        with self._status_lock:
            self._status.update(phase=phase, message=message)

    def _server(self, method='GET'):
        path = '/api/desktop/health' if method=='GET' else '/api/desktop/prepare-close'
        req = urllib.request.Request(self._url+path, method=method,
                                      headers={'X-Desktop-Token':self._token})
        with urllib.request.urlopen(req,timeout=5) as response:
            return json.load(response)

    def desktop_info(self):
        if not self._trusted(): return {'error':'앱 화면에서만 사용할 수 있습니다.'}
        return {'repository':REPOSITORY, 'version':os.environ.get('SOURCE_EXTRACTOR_REVISION','local')[:8]}

    def ui_ready(self):
        if not self._trusted(): return False
        ready = os.environ.get('SOURCE_EXTRACTOR_READY')
        if ready: atomic_json(Path(ready), {'ready':True})
        return True

    def update_status(self):
        if not self._trusted(): return {'phase':'error','message':'앱 화면을 확인하세요.'}
        with self._status_lock: return dict(self._status)

    def save_diagnostic_log(self):
        if not self._trusted(): return {'error':'앱 화면에서만 사용할 수 있습니다.'}
        try:
            import webview
            name = 'source_extractor_diagnostic_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.txt'
            selected = self._window.create_file_dialog(webview.SAVE_DIALOG,
                save_filename=name, file_types=('Text files (*.txt)', 'All files (*.*)'))
            if not selected: return {'message':'로그 저장을 취소했습니다.'}
            target = Path(selected[0] if isinstance(selected, (tuple, list)) else selected)
            state = read_state(self._root)
            sections = [
                'Source Extractor diagnostic log',
                f'created: {datetime.now().isoformat(timespec="seconds")}',
                f'platform: {platform.platform()}',
                f'python: {sys.version}',
                f'app revision: {os.environ.get("SOURCE_EXTRACTOR_REVISION", "local")}',
                f'local server: {self._url}',
                '\n[state]\n' + json.dumps(state, ensure_ascii=False, indent=2),
            ]
            for label, path in (
                ('app.log', self._root/'.desktop'/'app.log'),
                ('server.log', self._root/'.desktop'/'server.log'),
                ('update.log', self._root/'.desktop'/'update.log'),
                ('install_log.txt', self._root/'install_log.txt'),
            ):
                if path.is_file():
                    # The tail contains the useful failure while preventing an
                    # old installation log from creating an unbounded report.
                    raw = path.read_bytes()[-2 * 1024 * 1024:]
                    sections.append(f'\n[{label}]\n' + raw.decode('utf-8', errors='replace'))
            target.write_text('\n'.join(sections), encoding='utf-8')
            return {'message':f'진단 로그 저장 완료: {target}'}
        except Exception as exc:
            return {'error':f'로그 저장 실패: {exc}'}

    def open_debug_cmd(self):
        if not self._trusted(): return {'error':'앱 화면에서만 사용할 수 있습니다.'}
        if os.name != 'nt': return {'error':'서버 CMD는 Windows에서만 열 수 있습니다.'}
        try:
            script = self._root/'.desktop'/'show-server-log.ps1'
            script.write_text(
                "param([string]$LogPath,[string]$ServerUrl)\n"
                "$Host.UI.RawUI.WindowTitle='Source Extractor - Local Server Log'\n"
                "Write-Host ('Local server: '+$ServerUrl) -ForegroundColor Cyan\n"
                "Write-Host ('Live log: '+$LogPath) -ForegroundColor DarkGray\n"
                "Write-Host 'This is a viewer. Closing it does not stop the app.' -ForegroundColor Yellow\n"
                "if (!(Test-Path -LiteralPath $LogPath)) { New-Item -ItemType File -Path $LogPath -Force | Out-Null }\n"
                "Get-Content -LiteralPath $LogPath -Tail 200 -Wait\n",
                encoding='utf-8')
            subprocess.Popen(['cmd.exe','/k','powershell.exe','-NoLogo','-NoProfile','-NoExit',
                '-ExecutionPolicy','Bypass','-File',str(script),'-LogPath',
                str(self._root/'.desktop'/'server.log'),'-ServerUrl',self._url],
                cwd=self._root, creationflags=subprocess.CREATE_NEW_CONSOLE)
            return {'message':'로컬 서버 실시간 로그 CMD를 열었습니다.'}
        except Exception as exc:
            return {'error':f'CMD 열기 실패: {exc}'}

    def check_update(self):
        if not self._trusted(): return {'error':'앱 화면에서만 사용할 수 있습니다.'}
        if not self._lock.acquire(blocking=False): return self.update_status()
        try:
            self._set('checking','GitHub 새 버전 확인 중…')
            self._latest = latest_revision()
            current = os.environ.get('SOURCE_EXTRACTOR_REVISION','local')
            if current == self._latest['sha']:
                self._set('current','최신 버전입니다.')
            elif read_state(self._root).get('pending',{}).get('sha') == self._latest['sha']:
                self._set('ready','설치 준비 완료. 재시작하면 적용됩니다.')
            else:
                self._set('available',f"새 버전 {self._latest['sha'][:8]} · {self._latest['message']}")
        except Exception as exc: self._set('error',str(exc))
        finally: self._lock.release()
        return self.update_status()

    def start_update(self):
        if not self._trusted(): return {'error':'앱 화면에서만 사용할 수 있습니다.'}
        if not self._latest: return {'error':'먼저 업데이트 확인을 눌러 주세요.'}
        if not self._lock.acquire(blocking=False): return self.update_status()
        sha = self._latest['sha']
        self._set('downloading','업데이트 준비 중…')
        def worker():
            try:
                stage_update(self._root, sha, lambda message:self._set('downloading',message))
                self._set('ready','설치 준비 완료. 재시작하면 적용됩니다.')
            except Exception as exc: self._set('error',f'업데이트 실패: {exc} · 기존 버전은 유지됩니다.')
            finally: self._lock.release()
        threading.Thread(target=worker, daemon=True).start()
        return self.update_status()

    def _can_close(self):
        if self._closing: return True
        self._close_reason = ''
        if not self._lock.acquire(blocking=False):
            with self._status_lock:
                message = self._status.get('message') or '업데이트 상태 변경 중'
            return self._block_close('업데이트 작업: ' + message)
        try:
            try:
                result = self._server('POST')
                if not result['ok']:
                    return self._block_close('\n'.join(result.get('reasons') or
                        ['서버가 작업 중이라고 응답했지만 세부 이유를 제공하지 않았습니다.']))
            except Exception as exc:
                # Allow a dead server or the initial splash to close, but never
                # apply an update when a live server cannot confirm it is idle.
                if self._url and self._process is not None and self._process.poll() is None:
                    return self._block_close(f'서버 응답 확인 실패 ({type(exc).__name__}: {exc})\n'
                        '작업 진행 여부는 확인되지 않았습니다.')
            self._closing = True
            return True
        finally:
            self._lock.release()

    def _block_close(self, reason):
        self._close_reason = reason
        logging.getLogger(__name__).warning('Desktop close blocked: %s', reason)
        return False

    def restart_app(self):
        if not self._trusted(): return {'error':'앱 화면에서만 사용할 수 있습니다.'}
        if not read_state(self._root).get('pending'): return {'error':'준비된 업데이트가 없습니다.'}
        if not self._can_close(): return {'error':'재시작할 수 없습니다.\n' + self._close_reason}
        self._restart = True
        threading.Timer(.2, self._window.destroy).start()
        return {'ok':True}


def terminate_tree(process):
    if process.poll() is not None: return
    if os.name == 'nt':
        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
    else: process.terminate()
    try: process.wait(timeout=10)
    except subprocess.TimeoutExpired: process.kill()


def main():
    if os.environ.get('SOURCE_EXTRACTOR_LAUNCHER') != '1':
        raise RuntimeError('run_windows.bat으로 앱을 실행하세요.')
    import webview
    root = Path(os.environ['SOURCE_EXTRACTOR_HOME']).resolve()
    folder = root/'.desktop'; folder.mkdir(exist_ok=True)
    port_file = folder/('port-'+uuid.uuid4().hex)
    token = secrets.token_urlsafe(32)
    settings_file = folder/'window.json'
    settings = json.loads(settings_file.read_text(encoding='utf-8')) if settings_file.exists() else {}
    env = dict(os.environ, SOURCE_EXTRACTOR_SERVER_TOKEN=token,
               SOURCE_EXTRACTOR_PORT_FILE=str(port_file), SOURCE_EXTRACTOR_PORT=str(settings.get('port',0)))
    python = Path(sys.executable).with_name('python.exe') if os.name=='nt' else Path(sys.executable)
    log = (folder/'server.log').open('a',encoding='utf-8')
    process = subprocess.Popen([str(python),str(Path(__file__).with_name('desktop_server.py'))],
        env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    try:
        api = DesktopApi(root,'',token)
        api._process = process
        failed = threading.Event()
        webview.settings['ALLOW_DOWNLOADS'] = True
        webview.settings['ALLOW_FILE_URLS'] = False
        splash = '<html><body style="background:#0b0c10;color:#e8e8ea;font:18px Segoe UI;padding:48px"><h2>Source Extractor</h2><p>앱을 시작하는 중…</p><p style="font-size:14px;color:#a4a6b3">음성 분석 구성 요소를 불러오고 있습니다.</p></body></html>'
        window = webview.create_window('Source Extractor',html=splash,js_api=api,
            width=1280,height=900,min_size=(850,600),zoomable=False,text_select=True,background_color='#0b0c10')
        api._window = window
        def closing():
            if api._can_close(): return True
            # A stalled request or unavailable health endpoint must not trap
            # the user. This is exit only; restart/update activation still
            # requires the strict idle gate in restart_app().
            if window.create_confirmation_dialog('Source Extractor 종료',
                    '종료가 차단된 이유:\n' + api._close_reason + '\n\n' +
                    '지금 종료하면 진행 중인 분석·파일 저장·업데이트 설치가 중단될 수 있습니다.\n'
                    '그래도 종료하시겠습니까?'):
                api._restart = False
                api._closing = True
                return True
            return False
        window.events.closing += closing
        def load_app():
            try:
                deadline = time.monotonic()+180
                while time.monotonic()<deadline:
                    if api._closing: return
                    if process.poll() is not None: raise RuntimeError('로컬 서버 시작 실패: .desktop/server.log 확인')
                    if port_file.exists():
                        try:
                            port = int(port_file.read_text(encoding='ascii'))
                            api._url = f'http://127.0.0.1:{port}'
                            if api._server().get('ok'):
                                atomic_json(settings_file, {'port':port})
                                window.load_url(api._url+'/')
                                return
                        except (ValueError, OSError): pass
                    time.sleep(.15)
                raise RuntimeError('서버 시작 시간이 초과되었습니다. .desktop/server.log 확인')
            except Exception as exc:
                failed.set()
                print(str(exc),file=sys.stderr,flush=True)
                if os.name=='nt':
                    import ctypes
                    ctypes.windll.user32.MessageBoxW(None,str(exc),'Source Extractor',0x10)
                window.destroy()
        webview.start(load_app, gui='edgechromium' if os.name=='nt' else None, private_mode=False,
                          storage_path=str(folder/'webview'))
        return 1 if failed.is_set() else 75 if api._restart else 0
    finally:
        terminate_tree(process); log.close(); port_file.unlink(missing_ok=True)


if __name__=='__main__':
    sys.exit(main())
