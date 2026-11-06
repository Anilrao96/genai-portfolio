"""D:-backed WSL container session through Microsoft's public C API."""
import ctypes as c
from ctypes import wintypes as w
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SESSION='genai-portfolio-code'
STORAGE=ROOT/'.tools/wslc-code'
READY=ROOT/'.runtime/wslc-code-ready.json'
SDK=ROOT/'.tools/wslc-sdk/wslcsdk.dll'
CLI=Path(r'C:\Program Files\WSL\wslc.exe')


class SessionError(RuntimeError):pass


class Vhd(c.Structure):
    _fields_=[('name',c.c_char_p),('sizeBytes',c.c_ulonglong),('type',c.c_int),('flags',c.c_int),('uid',w.DWORD),('gid',w.DWORD)]


def hold_session():
    if not STORAGE.resolve().is_relative_to(ROOT.resolve()):raise SessionError('Storage must stay under the portfolio root.')
    if not SDK.is_file():raise SessionError('Run scripts/setup-wslc-sdk.py first.')
    ole=c.WinDLL('ole32');ole.CoInitializeEx.argtypes=[c.c_void_p,w.DWORD];ole.CoInitializeEx.restype=c.c_long
    ole.CoTaskMemFree.argtypes=[c.c_void_p];ole.CoUninitialize.argtypes=[]
    hr=ole.CoInitializeEx(None,0)
    if hr<0:raise SessionError(f'COM initialization failed: 0x{hr&0xffffffff:08x}')
    sdk=c.WinDLL(str(SDK));handle=c.c_void_p()
    def api(name,args):
        fn=getattr(sdk,name);fn.argtypes=args;fn.restype=c.c_long;return fn
    def check(hr,operation,error=None):
        detail=c.wstring_at(error) if error and error.value else ''
        if error and error.value:ole.CoTaskMemFree(error)
        if hr<0:raise SessionError(f'{operation} failed: 0x{hr&0xffffffff:08x} {detail[:500]}')
    try:
        missing=w.DWORD()
        check(api('WslcGetMissingComponents',[c.POINTER(w.DWORD)])(c.byref(missing)),'WSL prerequisite check')
        if missing.value:raise SessionError(f'Windows WSL components missing (mask {missing.value}); no system installation attempted.')
        settings=(c.c_ulonglong*9)() # Public SDK 3.0.3: 72 bytes aligned to eight.
        # The C settings retain pointers; keep their backing buffers alive through CreateSession.
        session_name=c.create_unicode_buffer(SESSION)
        storage_path=c.create_unicode_buffer(str(STORAGE))
        check(api('WslcInitSessionSettings',[w.LPCWSTR,w.LPCWSTR,c.c_void_p])(session_name,storage_path,settings),'Initialize session settings')
        check(api('WslcSetSessionSettingsCpuCount',[c.c_void_p,w.DWORD])(settings,2),'Set session CPUs')
        check(api('WslcSetSessionSettingsMemory',[c.c_void_p,w.DWORD])(settings,768),'Set session memory')
        check(api('WslcSetSessionSettingsFeatureFlags',[c.c_void_p,w.DWORD])(settings,0),'Disable optional GPU')
        vhd=Vhd(None,2*1024**3,0,0,0,0)
        check(api('WslcSetSessionSettingsVhd',[c.c_void_p,c.POINTER(Vhd)])(settings,c.byref(vhd)),'Set project storage cap')
        error=c.c_void_p()
        check(api('WslcCreateSession',[c.c_void_p,c.POINTER(c.c_void_p),c.POINTER(c.c_void_p)])(settings,c.byref(handle),c.byref(error)),'Create session',error)
        READY.parent.mkdir(exist_ok=True)
        data={'session':SESSION,'storage_path':str(STORAGE),'creator_pid':os.getpid(),'cpus':2,'memory_mb':768,
              'max_storage_bytes':2*1024**3,'sdk_version':'3.0.3','global_settings_modified':False,'startup_service_installed':False}
        READY.write_text(json.dumps(data,indent=2),encoding='utf8');print(json.dumps(data),flush=True)
        event=w.HANDLE()
        check(api('WslcGetSessionTerminationEvent',[c.c_void_p,c.POINTER(w.HANDLE)])(handle,c.byref(event)),'Session termination event')
        kernel=c.WinDLL('kernel32');kernel.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD];kernel.WaitForSingleObject.restype=w.DWORD
        kernel.WaitForSingleObject(event,0xffffffff)
    finally:
        if handle:
            api('WslcTerminateSession',[c.c_void_p])(handle);api('WslcReleaseSession',[c.c_void_p])(handle)
        ole.CoUninitialize()


if __name__=='__main__':hold_session()
