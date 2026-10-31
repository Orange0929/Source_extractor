"""Address an existing REAPER main window; never execute reaper.exe."""
import ctypes as C
import os
from pathlib import Path


class COPYDATASTRUCT(C.Structure):
    _fields_=[('dwData',C.c_size_t),('cbData',C.c_uint32),('lpData',C.c_void_p)]


def _api():
    if os.name!='nt':raise RuntimeError('자동 연결은 Windows 전용입니다. 보조 스크립트 연결을 사용하세요.')
    user=C.WinDLL('user32',use_last_error=True);kernel=C.WinDLL('kernel32',use_last_error=True)
    user.IsWindowVisible.argtypes=[C.c_void_p];user.IsWindowVisible.restype=C.c_int
    user.GetWindow.argtypes=[C.c_void_p,C.c_uint];user.GetWindow.restype=C.c_void_p
    user.GetClassNameW.argtypes=[C.c_void_p,C.c_wchar_p,C.c_int]
    user.GetWindowTextW.argtypes=[C.c_void_p,C.c_wchar_p,C.c_int]
    user.GetWindowThreadProcessId.argtypes=[C.c_void_p,C.POINTER(C.c_uint32)]
    kernel.OpenProcess.argtypes=[C.c_uint32,C.c_int,C.c_uint32];kernel.OpenProcess.restype=C.c_void_p
    kernel.CloseHandle.argtypes=[C.c_void_p]
    kernel.QueryFullProcessImageNameW.argtypes=[C.c_void_p,C.c_uint32,C.c_wchar_p,C.POINTER(C.c_uint32)]
    kernel.GetProcessTimes.argtypes=[C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p]
    user.SendMessageTimeoutW.argtypes=[C.c_void_p,C.c_uint,C.c_size_t,C.c_ssize_t,C.c_uint,C.c_uint,C.POINTER(C.c_size_t)]
    user.SendMessageTimeoutW.restype=C.c_ssize_t
    return user,kernel


def enumerate_reaper_windows():
    if os.name!='nt':return []
    user,kernel=_api();result=[]
    callback_type=C.WINFUNCTYPE(C.c_int,C.c_void_p,C.c_ssize_t)
    user.EnumWindows.argtypes=[callback_type,C.c_ssize_t]
    def visit(hwnd,_):
        if not user.IsWindowVisible(hwnd) or user.GetWindow(hwnd,4):return 1
        cls=C.create_unicode_buffer(256);user.GetClassNameW(hwnd,cls,len(cls))
        if cls.value!='REAPERwnd':return 1
        pid=C.c_uint32();user.GetWindowThreadProcessId(hwnd,C.byref(pid))
        handle=kernel.OpenProcess(0x1000,False,pid.value)
        if not handle:return 1
        try:
            exe=C.create_unicode_buffer(32768);size=C.c_uint32(len(exe))
            if not kernel.QueryFullProcessImageNameW(handle,0,exe,C.byref(size)):return 1
            if Path(exe.value).name.lower() not in ('reaper.exe','reaper64.exe'):return 1
            created=C.c_uint64();exit_time=C.c_uint64();system=C.c_uint64();used=C.c_uint64()
            if not kernel.GetProcessTimes(handle,C.byref(created),C.byref(exit_time),C.byref(system),C.byref(used)):return 1
            title=C.create_unicode_buffer(1024);user.GetWindowTextW(hwnd,title,len(title))
            key=f'{int(hwnd)}:{pid.value}:{created.value}'
            result.append(dict(key=key,hwnd=int(hwnd),pid=pid.value,created=created.value,title=title.value or 'REAPER',executable=exe.value))
        finally:kernel.CloseHandle(handle)
        return 1
    callback=callback_type(visit)
    user.EnumWindows(callback,0)
    return result


def deliver_script(window_key,script):
    # Re-enumerate immediately before sending: HWNDs/PIDs can be recycled.
    match=next((w for w in enumerate_reaper_windows() if w['key']==window_key),None)
    if match is None:raise RuntimeError('선택한 REAPER 창이 종료됐습니다. 창 목록을 새로 확인하세요.')
    script=Path(script).resolve()
    if script.suffix.lower()!='.lua' or not script.is_file():raise ValueError('연결 스크립트가 없습니다.')
    user,_=_api()
    # REAPER's existing-instance COPYDATA command accepts a raw UTF-8 path.
    # Lua/EEL scripts are dispatched before project/media loading. Prefixes or
    # shell quotes become part of the filename and prevent the script opening.
    encoded=str(script).encode('utf-8')
    payload=C.create_string_buffer(encoded)
    packet=COPYDATASTRUCT(0x100,len(encoded)+1,C.cast(payload,C.c_void_p))
    acknowledged=C.c_size_t()
    sent=user.SendMessageTimeoutW(match['hwnd'],0x4a,0,C.addressof(packet),3,3000,C.byref(acknowledged))
    if not sent:
        code=C.get_last_error()
        if code==5:raise RuntimeError('REAPER와 앱의 실행 권한이 달라 연결이 차단됐습니다. 같은 권한으로 실행하거나 보조 연결을 사용하세요.')
        raise RuntimeError('REAPER가 연결 요청에 응답하지 않습니다. 대화상자를 닫은 뒤 다시 시도하세요.')
    # A transport ACK is not evidence that Lua ran; the caller waits for the
    # receiver's fresh, request-specific connection token before reporting success.
    return match
