"""Bounded, isolated device discovery; never download a model to probe hardware."""
import csv
import ctypes
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import threading
import time


def cpu_info():
    name = platform.processor() or platform.machine() or 'CPU'
    try:
        if os.name == 'nt':
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
                name = winreg.QueryValueEx(key,'ProcessorNameString')[0].strip()
        else:
            for line in Path('/proc/cpuinfo').read_text().splitlines():
                if line.startswith('model name'):
                    name = line.split(':',1)[1].strip();break
    except (OSError,ValueError): pass
    return {'name':name,'logical_threads':os.cpu_count() or 1}


def gpu_probe():
    from stt_gpu_runtime import activate
    activate()
    devices=[]
    smi=shutil.which('nvidia-smi')
    if not smi and os.name=='nt':
        for path in (Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32'/'nvidia-smi.exe',
                     Path(os.environ.get('ProgramFiles',r'C:\Program Files'))/'NVIDIA Corporation'/'NVSMI'/'nvidia-smi.exe'):
            if path.is_file():smi=str(path);break
    if smi:
        try:
            text=subprocess.check_output([smi,'--query-gpu=index,name','--format=csv,noheader'],text=True,
                encoding='utf-8',timeout=4,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            devices=[{'index':int(index.strip()),'name':name.strip()} for index,name in csv.reader(io.StringIO(text))]
        except (OSError,ValueError,subprocess.SubprocessError):pass
    try:
        import ctranslate2
        count=ctranslate2.get_cuda_device_count()
        if not devices: devices=[{'index':i,'name':f'NVIDIA GPU {i}'} for i in range(count)]
        # Loading these in an isolated process catches missing runtime libraries
        # without risking the running server's native library environment.
        handles=[]
        if count:
            for name in (('cublas64_12.dll','cudnn64_9.dll') if os.name=='nt' else ('libcublas.so.12','libcudnn.so.9')):
                library=name
                if os.name=='nt':
                    folders=os.environ.get('PATH','').split(os.pathsep)
                    if os.environ.get('CUDA_PATH'): folders.append(str(Path(os.environ['CUDA_PATH'])/'bin'))
                    library=next((str(Path(folder)/name) for folder in folders if folder and (Path(folder)/name).is_file()),name)
                handles.append(ctypes.CDLL(library))
        for device in devices:
            try:
                supported=ctranslate2.get_supported_compute_types('cuda',device_index=device['index']) if device['index']<count else set()
                device.update(ready='float16' in supported,reason='런타임 확인됨 · 실제 분석에서 최종 확인' if 'float16' in supported else '호환 CUDA 장치를 사용할 수 없습니다.')
            except Exception as exc:device.update(ready=False,reason=str(exc))
        return {'gpus':devices,'message':'' if count else 'Whisper에서 사용 가능한 NVIDIA GPU가 없습니다.'}
    except Exception as exc:
        for device in devices:device.update(ready=False,reason='실행 구성 확인 필요: '+str(exc))
        return {'gpus':devices,'message':'GPU 실행 구성 확인 필요: '+str(exc)}


class Inventory:
    def __init__(self):self.lock=threading.Lock();self.cached=None;self.expires=0
    def get(self):
        with self.lock:
            if self.cached and time.monotonic()<self.expires:return self.cached
            result={'cpu':cpu_info(),'gpus':[],'message':''}
            try:
                run=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--probe'],capture_output=True,
                    text=True,encoding='utf-8',timeout=12,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                # Native libraries may write diagnostic lines before the JSON.
                result.update(json.loads(run.stdout.strip().splitlines()[-1]))
            except (OSError,ValueError,IndexError,subprocess.SubprocessError) as exc:
                result['message']='GPU 확인을 완료하지 못했습니다. CPU 사용은 가능합니다. '+str(exc)
            self.cached=result;self.expires=time.monotonic()+60
            return result


if __name__=='__main__':print(json.dumps(gpu_probe(),ensure_ascii=False))
