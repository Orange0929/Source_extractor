"""File IPC with a receiver running inside REAPER; never starts REAPER."""
import json
from pathlib import Path


def target_path(root):
    return Path(root)/'.desktop'/'reaper_target.json'


def read_target(root):
    try:
        data = json.loads(target_path(root).read_text(encoding='utf-8'))
        required=('project_id','instance','track_guid','project_name','track_name')
        if all(isinstance(data.get(k),str) and data[k] for k in required):
            return data
    except (OSError,ValueError,AttributeError,TypeError):
        pass
    return None


def lua_string(value):
    value=str(value)
    equals=''
    while ']'+equals+']' in value: equals+='='
    return '['+equals+'['+value+']'+equals+']'


def ipc_root(root):
    return Path(root)/'.desktop'/'reaper_ipc'


def prepare_receiver(root):
    folder=Path(root)/'reaper_connection'
    folder.mkdir(parents=True,exist_ok=True)
    ipc=ipc_root(root).resolve()
    ipc.mkdir(parents=True,exist_ok=True)
    # Stable location outside version directories: the registered REAPER action
    # continues to work after app updates and does not reference cleaned caches.
    script=folder/'Source Extractor - Connect.lua'
    content='local ROOT='+lua_string(ipc)+'\n'+Path(__file__).with_name('reaper_receiver.lua').read_text(encoding='utf-8')
    try:
        if script.read_text(encoding='utf-8')==content:return script
    except OSError:
        pass
    import uuid
    temporary=folder/(uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(content,encoding='utf-8')
        temporary.replace(script)
    finally:
        temporary.unlink(missing_ok=True)
    return script


def live_receivers(root):
    import time
    result={}
    for heartbeat in ipc_root(root).glob('*/heartbeat*.json'):
        try:
            data=json.loads(heartbeat.read_text(encoding='utf-8'))
            if (data.get('protocol')==2 and data.get('session')==heartbeat.parent.name
                and 0 <= time.time()-float(data['updated']) <= 5):
                existing=result.get(data['session'])
                if existing is None or (data['updated'],data.get('sequence',0)) > (existing['updated'],existing.get('sequence',0)):
                    result[data['session']]=data
        except (OSError,ValueError,TypeError,KeyError,AttributeError):
            continue
    return list(result.values())


def run_target_request(root, executable, action, target=None, media=None, name='', instance=None):
    # Deliberately no Popen: reconnecting or sending can never launch REAPER.
    import time
    import uuid
    script=prepare_receiver(root)
    live=live_receivers(root)
    if action=='capture':
        candidates=[r for r in live if not instance or r['session']==instance]
    else:
        pinned=[r for r in live if r['session']==(target or {}).get('instance')]
        # The receiver validates its live projects itself. Its heartbeat may lag
        # a just-captured identity by one polling interval. Never switch away
        # from a still-live pinned instance based on a stale project listing.
        candidates=pinned or [r for r in live if (r.get('projects') or {}).get((target or {}).get('project_id'))]
    if len(candidates)!=1:
        if not live:
            return {'error':'REAPER 연결 스크립트가 실행 중이 아닙니다. 연결 안내를 열어 REAPER 안에서 스크립트를 실행하세요.',
                    'needs_receiver':True,'script_path':str(script)}
        if len(candidates)>1:
            return {'error':'REAPER 창이 여러 개 연결돼 있습니다. 받을 창을 선택한 뒤 대상을 다시 지정하세요.',
                    'receivers':live}
        return {'error':'지정한 프로젝트가 연결된 REAPER에 없습니다. 프로젝트를 열거나 전송 대상을 다시 지정하세요.'}
    folder=ipc_root(root)/candidates[0]['session']
    key=uuid.uuid4().hex
    request=folder/(key+'.req')
    response=folder/(key+'.json')
    fields={k:str(v) for k,v in (target or {}).items() if k in ('project_id','track_guid')}
    fields.update(action=action,name=name,expires=str(int(time.time())+12))
    if media is not None: fields['media']=str(Path(media).resolve())
    packed=''.join(k+'='+v.encode('utf-8').hex()+'\n' for k,v in fields.items())
    temp=request.with_suffix('.tmp')
    temp.write_bytes(packed.encode('ascii'))
    temp.replace(request)
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        try:
            data=json.loads(response.read_text(encoding='utf-8'))
            if isinstance(data,dict) and ('ok' in data or 'error' in data):
                for completed in (request,response):
                    try: completed.unlink(missing_ok=True)
                    except OSError: pass
                if data.get('ok'):data['instance']=candidates[0]['session']
                return data
        except (OSError,ValueError):
            pass
        time.sleep(.05)
    # Do not retry automatically: REAPER may have inserted before an ACK failed.
    try: request.unlink(missing_ok=True)
    except OSError: pass
    return {'error':'REAPER 완료 응답을 받지 못했습니다. REAPER의 대화상자와 실제 삽입 여부를 확인한 뒤 다시 시도하세요.'}
