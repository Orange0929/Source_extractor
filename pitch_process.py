"""Keep native FCPE/PyTorch faults outside the HTTP server."""
import atexit
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

class PitchProcess:
    def __init__(self, command=None):
        self.command=command or [sys.executable,'-u',str(Path(__file__).resolve()),'--worker']
        self.process=None;self.lock=threading.RLock();atexit.register(self.close)

    def close(self):
        with self.lock:
            process,self.process=self.process,None
            if process:
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=3)
                    except subprocess.TimeoutExpired:process.kill();process.wait()
                for stream in (process.stdin,process.stdout):
                    if stream:stream.close()

    def analyze(self,path,start,end):
        with self.lock:
            if self.process is None or self.process.poll() is not None:
                self.close()
                root=Path(os.environ.get('SOURCE_EXTRACTOR_DATA_DIR',Path(__file__).parent))
                folder=root/'.desktop';folder.mkdir(parents=True,exist_ok=True)
                with (folder/'pitch_worker.log').open('a',encoding='utf-8') as log:
                    self.process=subprocess.Popen(self.command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,
                        text=True,encoding='utf-8',bufsize=1,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                process=self.process;messages=self.messages=queue.Queue()
                def read():
                    try:
                        for line in process.stdout:
                            try:messages.put(json.loads(line))
                            except ValueError:continue
                    finally:
                        code=process.poll()
                        messages.put({'error':f'피치 분석 프로세스가 종료됐습니다 (exit={code}). .desktop/pitch_worker.log를 확인하세요.'})
                threading.Thread(target=read,daemon=True).start()
            try:
                self.process.stdin.write(json.dumps({'path':str(path),'start':start,'end':end})+'\n');self.process.stdin.flush()
                result=self.messages.get(timeout=180)
                if 'error' in result:raise RuntimeError(result['error'])
                return result
            except (OSError,queue.Empty,RuntimeError) as exc:
                self.close()
                raise RuntimeError('피치 분석 실패 (재생·검색 서버는 유지됩니다): '+str(exc)) from exc

process=PitchProcess()
def analyze_pitch(path,start,end):return process.analyze(path,start,end)


def worker():
    import contextlib
    import faulthandler
    faulthandler.enable()
    output=sys.stdout
    with contextlib.redirect_stdout(sys.stderr):
        from audio_analysis import read_audio,pitch
    for line in sys.stdin:
        try:
            req=json.loads(line)
            with contextlib.redirect_stdout(sys.stderr):result=pitch(read_audio(req['path'],req['start'],req['end']),req['start'])
        except Exception as exc:result={'error':f'{type(exc).__name__}: {exc}'}
        output.write(json.dumps(result,allow_nan=False)+'\n');output.flush()

if __name__=='__main__':worker()
