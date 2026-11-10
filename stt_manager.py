"""Single-consumer scheduler and killable, reusable Whisper subprocess."""
import atexit
from concurrent.futures import Future
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import threading
import time


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    tmp.replace(path)


class Manager:
    def __init__(self, root, command=None):
        self.path = Path(root)/'.desktop'/'stt_settings.json'
        self.settings = {'device':'auto', 'performance':'balanced', 'threads':0, 'gpu_index':0}
        self.paused = False
        self.pause_revision = 0
        try:
            saved = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(saved, dict): raise ValueError('invalid settings')
            self.settings.update({k:saved[k] for k in self.settings if k in saved})
            if self.settings['device'] not in ('auto','cpu','cuda'): self.settings['device']='auto'
            if self.settings['performance'] not in ('eco','balanced','maximum'): self.settings['performance']='balanced'
            if type(self.settings['threads']) is not int or not 0 <= self.settings['threads'] <= (os.cpu_count() or 1): self.settings['threads']=0
            if type(self.settings['gpu_index']) is not int or self.settings['gpu_index']<0: self.settings['gpu_index']=0
            # Idle pause is session state, not a preference. Recovery below
            # explicitly pauses only when unfinished files actually exist.
        except (OSError, ValueError, TypeError): pass
        self.cv = threading.Condition(threading.RLock())
        self.pending = []
        self.current = None
        self.process = None
        self.closed = False
        self.actual = {'device':None, 'message':'아직 분석하지 않았습니다.'}
        self.command = command or [sys.executable, '-u', str(Path(__file__).with_name('stt_worker.py'))]
        self.thread = threading.Thread(target=self._dispatch, daemon=True)
        self.thread.start()
        atexit.register(self.close)

    def _save(self): atomic(self.path, self.settings)

    def configure(self, data):
        settings = dict(self.settings)
        for key in settings:
            if key in data: settings[key] = data[key]
        if settings['device'] not in ('auto','cpu','cuda'): raise ValueError('잘못된 분석 장치')
        if settings['performance'] not in ('eco','balanced','maximum'): raise ValueError('잘못된 성능 모드')
        if type(settings['threads']) is not int or not 0 <= settings['threads'] <= (os.cpu_count() or 1):
            raise ValueError('CPU 스레드 수 범위를 확인하세요.')
        if type(settings['gpu_index']) is not int or not 0 <= settings['gpu_index'] <= 63:
            raise ValueError('잘못된 GPU 번호')
        with self.cv:
            self.settings = settings
            self._save()
        return self.status()

    def status(self):
        with self.cv:
            return dict(settings=dict(self.settings), paused=self.paused, running=self.current is not None,
                        waiting=sum(not f.cancelled() for f,_ in self.pending), actual=dict(self.actual))

    def pause(self):
        with self.cv:
            self.paused = True; self.pause_revision += 1; self.cv.notify_all()
            if self.current is None: self.terminate()

    def resume(self):
        with self.cv:
            self.paused = False; self.pause_revision += 1; self.cv.notify_all()

    def submit(self, fn):
        future = Future()
        with self.cv:
            self.pending.append((future, fn)); self.cv.notify_all()
        return future

    def _dispatch(self):
        while True:
            with self.cv:
                self.cv.wait_for(lambda:self.closed or (not self.paused and self.pending))
                if self.closed: return
                future, fn = self.pending.pop(0)
                if not future.set_running_or_notify_cancel(): continue
                self.current = future
            try: future.set_result(fn())
            except BaseException as exc: future.set_exception(exc)
            finally:
                with self.cv:
                    self.current = None
                    if self.paused: self.terminate()
            # Throttle between files without changing recognition parameters.
            delay = {'eco':1.0,'balanced':.15,'maximum':0}.get(self.settings['performance'],.15)
            with self.cv: self.cv.wait(timeout=delay)

    def terminate(self):
        with self.cv:
            process, self.process = self.process, None
        if process:
            if process.poll() is None:
                if os.name == 'nt':
                    taskkill = Path(os.environ.get('SystemRoot', r'C:\Windows'))/'System32'/'taskkill.exe'
                    try:
                        subprocess.run([str(taskkill), '/PID', str(process.pid), '/T', '/F'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
                    except (OSError, subprocess.TimeoutExpired): process.terminate()
                else:
                    try: os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError: pass
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
            for stream in (process.stdin, process.stdout):
                if stream:
                    try: stream.close()
                    except OSError: pass

    def close(self):
        with self.cv:
            self.closed = True; self.cv.notify_all()
        self.terminate()

    def run(self, request, cancel, progress):
        if cancel.is_set(): return {'status':'cancelled', 'message':'중단됨', 'clips':[]}
        with self.cv:
            if self.process is None or self.process.poll() is not None:
                env = dict(os.environ, SOURCE_EXTRACTOR_STT_CHILD='1', PYTHONIOENCODING='utf-8', SOURCE_EXTRACTOR_GPU_RUNTIME=str(self.path.parent/'gpu-runtime'))
                log = self.path.parent/'stt_worker.log'
                log.parent.mkdir(parents=True,exist_ok=True)
                with log.open('a',encoding='utf-8') as stderr:
                    self.process = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=stderr, text=True, encoding='utf-8', bufsize=1, env=env, start_new_session=os.name!='nt',
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                self.messages = queue.Queue()
                process, messages = self.process, self.messages
                def read():
                    try:
                        for line in process.stdout:
                            try: messages.put(json.loads(line))
                            except ValueError: continue
                    finally: messages.put({'type':'exit'})
                threading.Thread(target=read, daemon=True).start()
            process, messages = self.process, self.messages
            request = dict(request, settings=dict(self.settings))
            process.stdin.write(json.dumps(request,ensure_ascii=False)+'\n'); process.stdin.flush()
        while True:
            if cancel.is_set() or self.closed:
                self.terminate()
                return {'status':'cancelled','message':'중단됨 · 이 파일은 처음부터 재분석합니다.','clips':[]}
            try: message = messages.get(timeout=.1)
            except queue.Empty: continue
            if message['type']=='device':
                with self.cv: self.actual = message['actual']
            elif message['type']=='progress': progress(message['job'])
            elif message['type']=='result': return message['result']
            elif message['type']=='exit':
                self.terminate()
                raise RuntimeError('분석 프로세스가 종료됐습니다. .desktop/stt_worker.log를 확인하세요.')


def install(core):
    manager = Manager(core.DATA_DIR)
    core.STT_MANAGER = manager
    core.EXECUTOR.shutdown(wait=False)
    core.EXECUTOR = manager
    original_cancel = core.api_cancel_job
    def cancel_job(job_id: str):
        result = original_cancel(job_id)
        job = core.get_job(job_id) or {}
        if job.get('status') == 'cancelled':
            with core.DATA_LOCK:
                data = core.load_data()
                for audio in data['audios']:
                    if audio['id'] == job.get('audio_id'): audio.update(stt_status='cancelled',stt_message=job.get('message',''))
                core.save_data(data)
        return result
    for route in core.app.routes:
        if getattr(route, 'path', '') == '/api/jobs/{job_id}/cancel':
            # FastAPI stores its callable on the dependency graph.
            route.endpoint = cancel_job
            route.dependant.call = cancel_job

    def run(job_id, profile_id, audio_id, path):
        cancel = core._get_cancel_event(job_id)
        core.set_job(job_id,status='running',progress=0,message='Whisper 분석 프로세스 준비 중…')
        result = manager.run(dict(job_id=job_id,profile_id=profile_id,audio_id=audio_id,path=str(path)),cancel,
                            lambda job:core.set_job(job_id,**job))
        # The child never writes profile data. Commit only complete results under
        # the existing lock, revalidating ownership and preserving edited clips.
        with core.DATA_LOCK:
            data = core.load_data()
            audio = next((a for a in data['audios'] if a['id']==audio_id),None)
            if result['status']=='done' and not cancel.is_set() and audio:
                if not any(c.get('audio_id')==audio_id for c in data['clips']):
                    for clip in result['clips']: clip['profile_id'] = audio['profile_id']
                    data['clips'].extend(result['clips'])
                audio.update(stt_status='done',stt_message=result['message'])
                core.save_data(data)
            elif cancel.is_set(): result.update(status='cancelled',message='중단됨')
        core.set_job(job_id,status=result['status'],message=result['message'],
                     progress=100 if result['status']=='done' else 0,
                     clips_created=len(result['clips']) if result['status']=='done' else 0)
        core.audit('stt_result',job_id=job_id,status=result['status'],actual=manager.actual)
    core.run_stt_job = run

    from stt_hardware import Inventory
    inventory = Inventory()
    from stt_gpu_runtime import Installer
    installer = Installer(core.DATA_DIR,manager,inventory)
    core.STT_GPU_INSTALLER = installer

    @core.app.get('/api/stt/gpu-install')
    def gpu_install_status(): return installer.status()

    @core.app.post('/api/stt/gpu-install')
    def gpu_install():
        try: return installer.start()
        except ValueError as exc: raise core.HTTPException(409,str(exc))

    @core.app.get('/api/stt/hardware')
    def hardware(): return inventory.get()

    @core.app.get('/api/stt/control')
    def status():
        result = manager.status()
        with core.JOBS_LOCK:
            jobs = list(core.JOBS.values())
            result['counts'] = {state:sum(j.get('status')==state for j in jobs) for state in ('done','error','cancelled')}
            result['filename'] = next((j.get('filename','') for j in jobs if j.get('status')=='running'), '')
        return result

    @core.app.post('/api/stt/settings')
    def settings(data: dict):
        try: return manager.configure(data)
        except ValueError as exc: raise core.HTTPException(400,str(exc))

    @core.app.post('/api/stt/control/{action}')
    def control(action: str):
        if action=='pause': manager.pause()
        elif action=='resume':
            if installer.status()['busy']: raise core.HTTPException(409,'GPU 실행 구성 설치가 끝난 뒤 재개하세요.')
            manager.resume()
        elif action=='stop':
            installing = installer.status()['busy']
            if not installing: manager.pause()
            cancelled = set()
            with core.JOBS_LOCK:
                for job_id, job in core.JOBS.items():
                    if job.get('status') in ('queued','running'):
                        ev = job.get('_cancel_event')
                        if ev: ev.set()
                        else:
                            ev = threading.Event();ev.set();job['_cancel_event'] = ev
                        future = job.get('_future')
                        if future and future.cancel():
                            job.update(status='cancelled',message='중단됨(대기)',progress=0)
                            cancelled.add(job.get('audio_id'))
            with core.DATA_LOCK:
                data = core.load_data()
                for audio in data['audios']:
                    if audio['id'] in cancelled: audio.update(stt_status='cancelled',stt_message='중단됨(대기)')
                core.save_data(data)
            # Stop cancels this batch, not future uploads. Installation keeps
            # its temporary hold until it finishes.
            if not installing: manager.resume()
            # Running worker notices cancellation and kills the child itself.
        else: raise core.HTTPException(400,'잘못된 작업')
        core.audit('stt_control',command=action)
        return manager.status()

    @core.app.on_event('startup')
    def recover():
        data = core.load_data()
        unfinished = [a for a in data['audios'] if a.get('stt_status') in ('queued','running')]
        if unfinished:
            manager.pause()
            for audio in unfinished:
                if (core.UPLOAD_DIR/audio['path']).is_file(): core.submit_audio_job(audio)
            core.audit('stt_recovered',count=len(unfinished))

    @core.app.on_event('shutdown')
    def shutdown(): installer.close(); manager.close()
