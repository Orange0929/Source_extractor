"""Local desktop backend: data stays in the original installation directory."""
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from collections import Counter


def operation_label(scope):
    path = scope.get('path', '')
    for prefix, label in (
        ('/api/upload', '오디오 업로드'), ('/api/import', '프로필 가져오기'),
        ('/api/export/', '프로필 내보내기'),
        ('/api/audio_analysis/', '피치 분석'), ('/api/audio_waveform/', '파형 분석'),
        ('/api/clips/bulk_download', '선택 소스 ZIP 생성·다운로드'),
        ('/api/clips/manual', '선택 구간 저장'), ('/api/jobs/', '분석 작업 변경'),
        ('/api/profiles', '프로필 변경'), ('/api/clips', '소스 변경')):
        if path.startswith(prefix): return label
    return f"서버 작업 ({scope.get('method', 'GET')} {path})"


def job_reason(job):
    status = job.get('status')
    future = job.get('_future')
    if status not in ('running', 'queued') and (future is None or future.done()):
        return None
    stage = {'running':'분석 중', 'queued':'분석 대기'}.get(status, '분석 종료 처리 중')
    name = job.get('filename') or job.get('job_id', '알 수 없는 작업')
    return f"{stage}: {name} · {job.get('progress', 0)}% · {job.get('message', '')}"


def blocks_close(scope):
    """Protect writes/exports/analysis, not playback streams or UI polling."""
    if scope.get('type') != 'http':
        return False
    path = scope.get('path', '')
    if not path.startswith('/api/') or path.startswith('/api/desktop/'):
        return False
    return (scope.get('method', 'GET') not in ('GET', 'HEAD', 'OPTIONS') or
            path.startswith(('/api/export/', '/api/clips/bulk_download/',
                             '/api/audio_analysis/', '/api/audio_waveform/')))


def main():
    # ffmpeg children must not flash command windows when launched by pythonw.
    if os.name == 'nt':
        original = subprocess.Popen
        class HiddenPopen(original):
            def __init__(self, *args, **kwargs):
                kwargs['creationflags'] = kwargs.get('creationflags', 0) | subprocess.CREATE_NO_WINDOW
                super().__init__(*args, **kwargs)
        subprocess.Popen = HiddenPopen
    import uvicorn
    import app_fixed
    import app as core
    from fastapi.responses import JSONResponse
    app = app_fixed.app
    token = os.environ['SOURCE_EXTRACTOR_SERVER_TOKEN']
    active = {}
    closing = False

    def close_reasons():
        counts = Counter(item['label'] for item in active.values())
        reasons = [f'{label}: {count}건 (최장 {int(max(time.monotonic()-x["started"] for x in active.values() if x["label"] == label))}초 경과)'
                   for label, count in counts.items()]
        with core.JOBS_LOCK:
            reasons.extend(reason for job in core.JOBS.values() if (reason := job_reason(job)))
        return reasons

    @app.get('/api/desktop/health')
    async def health(request: core.Request):
        if request.headers.get('X-Desktop-Token') != token:
            return JSONResponse({'error':'Forbidden'}, status_code=403)
        reasons = close_reasons()
        return {'ok':True, 'busy':bool(reasons), 'active_operations':len(active), 'reasons':reasons}

    @app.post('/api/desktop/prepare-close')
    async def prepare_close(request: core.Request):
        nonlocal closing
        if request.headers.get('X-Desktop-Token') != token:
            return JSONResponse({'error':'Forbidden'}, status_code=403)
        reasons = close_reasons()
        if reasons:
            return {'ok':False, 'busy':True, 'reasons':reasons}
        closing = True
        return {'ok':True, 'busy':False}

    class TrackRequests:
        def __init__(self, wrapped): self.app = wrapped
        async def __call__(self, scope, receive, send):
            nonlocal active
            tracked = blocks_close(scope)
            api_request = scope['type']=='http' and scope['path'].startswith('/api/') and not scope['path'].startswith('/api/desktop/')
            if api_request and closing:
                await JSONResponse({'error':'앱을 재시작하는 중입니다.'},status_code=503)(scope,receive,send)
                return
            request_key = object()
            if tracked: active[request_key] = {'label':operation_label(scope), 'started':time.monotonic()}
            try: await self.app(scope, receive, send)
            finally:
                if tracked: active.pop(request_key, None)

    async def serve():
        # Reuse the same port when available so WebView localStorage stays stable.
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try: sock.bind(('127.0.0.1', int(os.environ.get('SOURCE_EXTRACTOR_PORT','0'))))
        except OSError: sock.bind(('127.0.0.1',0))
        sock.listen(128); sock.setblocking(False)
        Path(os.environ['SOURCE_EXTRACTOR_PORT_FILE']).write_text(str(sock.getsockname()[1]),encoding='ascii')
        server = uvicorn.Server(uvicorn.Config(TrackRequests(app), log_level='warning', access_log=False))
        await server.serve(sockets=[sock])
    asyncio.run(serve())


if __name__ == '__main__':
    main()
