"""Local desktop backend: data stays in the original installation directory."""
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys


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
    active = 0
    closing = False

    def busy():
        with core.JOBS_LOCK:
            jobs = sum(1 for job in core.JOBS.values() if
                job.get('status') in ('running','queued') or
                (job.get('_future') is not None and not job['_future'].done()))
        return bool(active or jobs)

    @app.get('/api/desktop/health')
    async def health(request: core.Request):
        if request.headers.get('X-Desktop-Token') != token:
            return JSONResponse({'error':'Forbidden'}, status_code=403)
        return {'ok':True, 'busy':busy()}

    @app.post('/api/desktop/prepare-close')
    async def prepare_close(request: core.Request):
        nonlocal closing
        if request.headers.get('X-Desktop-Token') != token:
            return JSONResponse({'error':'Forbidden'}, status_code=403)
        if busy():
            return {'ok':False, 'busy':True}
        closing = True
        return {'ok':True, 'busy':False}

    class TrackRequests:
        def __init__(self, wrapped): self.app = wrapped
        async def __call__(self, scope, receive, send):
            nonlocal active
            tracked = scope['type']=='http' and scope['path'].startswith('/api/') and not scope['path'].startswith('/api/desktop/')
            if tracked and closing:
                await JSONResponse({'error':'앱을 재시작하는 중입니다.'},status_code=503)(scope,receive,send)
                return
            if tracked: active += 1
            try: await self.app(scope, receive, send)
            finally:
                if tracked: active -= 1

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
