"""Locate REAPER and hand persistent media to its existing instance."""
import json
import os
from pathlib import Path
import shutil
import subprocess


def valid_executable(path):
    path = Path(path)
    return path.is_file() and path.name.lower() in ('reaper.exe', 'reaper')


def find_reaper(root):
    candidates = []
    try:
        preferences = json.loads((Path(root)/'.desktop'/'preferences.json').read_text(encoding='utf-8'))
        if preferences.get('reaper_executable'):
            candidates.append(Path(preferences['reaper_executable']))
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    if os.name == 'nt':
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive, r'Software\Microsoft\Windows\CurrentVersion\App Paths\reaper.exe', 0, winreg.KEY_READ|view) as key:
                        candidates.append(Path(winreg.QueryValueEx(key, '')[0].strip('"')))
                except OSError:
                    pass
        for variable in ('ProgramW6432','ProgramFiles','ProgramFiles(x86)'):
            folder = os.environ.get(variable)
            if folder:
                candidates.extend((Path(folder)/'REAPER (x64)'/'reaper.exe', Path(folder)/'REAPER'/'reaper.exe'))
    found = shutil.which('reaper.exe' if os.name == 'nt' else 'reaper')
    if found:
        candidates.append(Path(found))
    return next((p.resolve() for p in candidates if valid_executable(p)), None)


def target_path(root):
    return Path(root)/'.desktop'/'reaper_target.json'


def read_target(root):
    try:
        data = json.loads(target_path(root).read_text(encoding='utf-8'))
        required = ('session','project_pointer','project_path','track_guid','project_name','track_name')
        if all(isinstance(data.get(k), str) for k in required) and data['track_guid']:
            return data
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    return None


def lua_string(value):
    # Long brackets preserve UTF-8 paths literally, including backslashes.
    value = str(value)
    equals = ''
    while ']'+equals+']' in value:
        equals += '='
    return '['+equals+'['+value+']'+equals+']'


def run_target_request(root, executable, action, target=None, media=None, name=''):
    import time
    import uuid
    folder = Path(root)/'.desktop'/'reaper_requests'
    folder.mkdir(parents=True, exist_ok=True)
    key = uuid.uuid4().hex
    script = folder/(key+'.lua')
    response = folder/(key+'.json')
    fields = dict(target or {})
    fields.update(action=action, response=str(response.resolve()), name=name)
    if media is not None: fields['media'] = str(Path(media).resolve())
    header = 'local req = {'+','.join(k+'='+lua_string(v) for k,v in fields.items())
    header += ',expires='+str(int(time.time())+12)+'}\n'
    script.write_text(header+Path(__file__).with_name('reaper_target.lua').read_text(encoding='utf-8'), encoding='utf-8')
    subprocess.Popen([str(executable), '-nonewinst', str(script.resolve())], cwd=str(Path(executable).parent))
    deadline = time.monotonic()+15
    while time.monotonic() < deadline:
        try:
            result = json.loads(response.read_text(encoding='utf-8'))
            if isinstance(result, dict) and ('ok' in result or 'error' in result):
                for completed in (script, response):
                    try: completed.unlink(missing_ok=True)
                    except OSError: pass
                return result
        except (OSError, ValueError):
            pass
        time.sleep(.05)
    return {'error':'REAPER 응답이 없습니다. 받을 REAPER 창을 열고 대화상자를 닫은 뒤 다시 시도하세요.'}
