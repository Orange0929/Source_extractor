"""Whisper worker: stdout is JSON IPC; model and decode logs go to stderr."""
import contextlib
import json
import os
import sys


def main():
    output = sys.stdout
    def send(value):
        output.write(json.dumps(value,ensure_ascii=False)+'\n');output.flush()
    with contextlib.redirect_stdout(sys.stderr):
        import app_fixed
        import app as core
        import ctranslate2
        from faster_whisper import WhisperModel
    model = None
    model_key = None
    for line in sys.stdin:
        request = json.loads(line)
        settings = request['settings']
        count = os.cpu_count() or 1
        threads = settings['threads'] or {'eco':max(1,count//4),'balanced':max(1,count//2),'maximum':count}[settings['performance']]
        fallback = ''
        requested = settings['device']
        device = requested
        if device=='auto':
            try: device = 'cuda' if ctranslate2.get_cuda_device_count()>0 else 'cpu'
            except Exception: device = 'cpu'
            if device=='cpu': fallback = '사용 가능한 NVIDIA GPU 런타임이 없어 CPU 사용'
        def execute(device):
            nonlocal model, model_key
            send({'type':'device','actual':dict(device=None,threads=threads,message=device+' 모델 준비 중…')})
            key = (device,threads,core.WHISPER_MODEL_NAME,settings.get('gpu_index',0))
            if model_key != key:
                model = None;model_key = None
                compute = 'float16' if device=='cuda' else 'int8'
                model = WhisperModel(core.WHISPER_MODEL_NAME,device=device,compute_type=compute,cpu_threads=threads,num_workers=1,device_index=settings.get('gpu_index',0) if device=='cuda' else 0)
                model_key = key
            send({'type':'device','actual':dict(device=device,threads=threads,gpu_index=settings.get('gpu_index',0) if device=='cuda' else None,message=fallback or '분석 준비 완료')})
            core.get_whisper_model = lambda:model
            result = {'status':'error','message':'분석 결과 없음','clips':[]}
            core.load_data = lambda:{'clips':[]}
            core.save_data = lambda data:result.update(clips=data['clips'])
            def progress(job_id,**job):
                result.update({k:v for k,v in job.items() if k in ('status','message')})
                if job.get('status') not in ('done','error','cancelled'):
                    send({'type':'progress','job':job})
            core.set_job = progress
            from pathlib import Path
            app_fixed.run_stt_job_fixed(request['job_id'],request['profile_id'],request['audio_id'],Path(request['path']))
            return result
        try:
            with contextlib.redirect_stdout(sys.stderr):
                try: result = execute(device)
                except Exception as exc: result = {'status':'error','message':str(exc),'clips':[]}
                if requested=='auto' and device=='cuda' and result['status']=='error':
                    fallback = 'GPU 분석 실패 → CPU로 재시도: '+result['message']
                    result = execute('cpu')
        except Exception as exc:
            result = {'status':'error','message':f'{type(exc).__name__}: {exc}','clips':[]}
        if result['status']=='error':
            send({'type':'device','actual':dict(device=None,message=result['message'])})
        send({'type':'result','result':result})


if __name__=='__main__': main()
