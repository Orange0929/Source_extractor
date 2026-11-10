"""Optional Windows NVIDIA wheels isolated from the application's Python packages."""
import atexit
import json
import hashlib
import urllib.request
from urllib.parse import urlparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import uuid

SUPPORTED = os.name == 'nt'
PACKAGES = ('nvidia-cublas-cu12==12.4.5.8','nvidia-cudnn-cu12==9.1.0.70','nvidia-cuda-runtime-cu12==12.4.127')
_dll_handles=[]


def runtime_path(root=None):
    if os.environ.get('SOURCE_EXTRACTOR_GPU_RUNTIME'):
        return Path(os.environ['SOURCE_EXTRACTOR_GPU_RUNTIME'])
    root=Path(root or os.environ.get('SOURCE_EXTRACTOR_DATA_DIR') or Path(__file__).parent)
    return root/'.desktop'/'gpu-runtime'


def activate(root=None):
    """Call only in a probe/worker before importing native inference libraries."""
    base=runtime_path(root)
    folders=sorted({str(p.parent) for p in base.glob('nvidia/**/*.dll')}) if base.is_dir() else []
    if folders:
        os.environ['PATH']=os.pathsep.join(folders+[os.environ.get('PATH','')])
        if os.name=='nt':
            for folder in folders:_dll_handles.append(os.add_dll_directory(folder))
    return folders


class Installer:
    def __init__(self, root, manager, inventory):
        self.root=Path(root);self.target=self.root/'.desktop'/'gpu-runtime'
        self.manager=manager;self.inventory=inventory
        self.lock=threading.RLock();self.process=None;self.closed=False
        self.state={'busy':False,'phase':'idle','message':''}
        self.log=self.target.parent/'gpu_install.log'
        atexit.register(self.close)

    def status(self):
        with self.lock:return dict(self.state)

    def start(self):
        if not SUPPORTED:raise ValueError('앱 내 GPU 구성 설치는 Windows에서 지원합니다.')
        with self.lock:
            if self.state['busy']:return dict(self.state)
            # Never replace DLLs while a model/file is using them.
            with self.manager.cv:
                if self.manager.current is not None:raise ValueError('일시정지를 누르고 현재 파일이 끝난 뒤 설치하세요.')
                self.manager.pause()
            self.closed=False
            self.state={'busy':True,'phase':'preparing','downloaded_bytes':0,'total_bytes':0,'message':'NVIDIA 패키지 용량 확인 중…'}
            threading.Thread(target=self._install,daemon=True).start()
            return dict(self.state)

    def _update(self, **fields):
        with self.lock:self.state.update(fields)

    def _download_wheels(self, folder):
        wheels=[]
        for spec in PACKAGES:
            if self.closed:raise RuntimeError('설치 중단됨')
            name,version=spec.split('==')
            with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json',timeout=30) as response:
                metadata=json.load(response)
            wheel=next((f for f in metadata['urls'] if f['filename'].endswith('-win_amd64.whl')),None)
            if not wheel:raise RuntimeError('Windows 패키지를 찾지 못했습니다: '+spec)
            if Path(wheel['filename']).name!=wheel['filename'] or urlparse(wheel['url']).scheme!='https':
                raise RuntimeError('패키지 다운로드 경로가 올바르지 않습니다.')
            wheels.append(wheel)
        total=sum(w['size'] for w in wheels)
        self._update(total_bytes=total,downloaded_bytes=0,phase='downloading',busy=True)
        downloaded=0;paths=[]
        for i,wheel in enumerate(wheels):
            filename=wheel['filename'];path=folder/filename;part=path.with_suffix('.part')
            self._update(message=f'다운로드 중 ({i+1}/{len(wheels)}): {filename}')
            digest=hashlib.sha256();size=0
            with urllib.request.urlopen(wheel['url'],timeout=30) as response, part.open('wb') as output:
                while True:
                    if self.closed:raise RuntimeError('설치 중단됨')
                    chunk=response.read(512*1024)
                    if not chunk:break
                    output.write(chunk);digest.update(chunk);size+=len(chunk);downloaded+=len(chunk)
                    self._update(downloaded_bytes=downloaded)
            if size!=wheel['size'] or digest.hexdigest()!=wheel['digests']['sha256']:
                raise RuntimeError('다운로드 검증 실패: '+filename)
            part.rename(path);paths.append(str(path))
        return paths

    def _install(self):
        stage=self.target.with_name('gpu-runtime-stage-'+uuid.uuid4().hex)
        wheels=self.target.with_name('gpu-wheels-'+uuid.uuid4().hex)
        backup=self.target.with_name('gpu-runtime-backup-'+uuid.uuid4().hex)
        outcome={'busy':False,'phase':'error','message':'설치 중단됨'}
        try:
            stage.mkdir(parents=True);wheels.mkdir(parents=True)
            self._update(busy=True,phase='preparing',downloaded_bytes=0,total_bytes=0,message='NVIDIA 패키지 용량 확인 중…')
            paths=self._download_wheels(wheels)
            self._update(phase='installing',message='다운로드 완료 · 압축 해제 및 설치 중…')
            command=[sys.executable,'-m','pip','install','--isolated','--disable-pip-version-check',
                     '--no-deps','--no-index','--target',str(stage),*paths]
            with self.log.open('a',encoding='utf-8') as log:
                log.write('\nGPU runtime installation: '+str(PACKAGES)+'\n');log.flush()
                with self.lock:
                    if self.closed:raise RuntimeError('설치 중단됨')
                    self.process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                    process=self.process
                if process.wait(timeout=1800)!=0:raise RuntimeError('패키지 설치 실패. .desktop/gpu_install.log를 확인하세요.')
            self._update(phase='checking',message='설치 파일 확인 및 적용 중…')
            for name in ('cublas64_12.dll','cudnn64_9.dll','cudart64_12.dll'):
                if not any(stage.glob('nvidia/**/'+name)):raise RuntimeError('설치된 파일 누락: '+name)
            (stage/'manifest.json').write_text(json.dumps({'packages':PACKAGES}),encoding='utf-8')
            with self.lock:
                if self.closed:raise RuntimeError('설치 중단됨')
                if self.target.exists():self.target.rename(backup)
                try:stage.rename(self.target)
                except Exception:
                    if backup.exists():backup.rename(self.target)
                    raise
                with self.inventory.lock:self.inventory.cached=None;self.inventory.expires=0
                outcome={'busy':False,'phase':'done','message':'GPU 실행 구성 설치 완료. 장치 확인 후 재개를 눌러주세요.'}
        except Exception as exc:
            try:
                with self.log.open('a',encoding='utf-8') as log:log.write('GPU setup failed: '+str(exc)+'\n')
            except OSError:pass
            outcome={'busy':False,'phase':'error','message':str(exc)}
        finally:
            with self.lock:
                if self.process and self.process.poll() is None:
                    self.process.terminate()
                    try:self.process.wait(timeout=3)
                    except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
                self.process=None
            shutil.rmtree(stage,ignore_errors=True);shutil.rmtree(wheels,ignore_errors=True)
            if outcome['phase']=='done':shutil.rmtree(backup,ignore_errors=True)
            with self.lock:self.state.update(outcome)

    def close(self):
        with self.lock:
            self.closed=True
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
