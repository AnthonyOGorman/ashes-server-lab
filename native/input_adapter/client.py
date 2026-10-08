"""Fixed local IPC and exact-client LoadLibrary attachment for the offline Lab.

The only remote execution operation is loading the compiled adapter path; no
addresses, memory contents or arbitrary function calls are accepted as commands.
"""
from __future__ import annotations
import ctypes
import hashlib
import json
import os
import struct
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
DLL=Path(__file__).resolve().parent/'build'/'ashes_input_adapter.dll'
MAGIC=0x414F4349
REQUEST=struct.Struct('<IIIiiI')
RESPONSE=struct.Struct('<IIIIIIiiQII')


class AdapterError(RuntimeError): pass
class AdapterBuildMismatch(AdapterError): pass


def decode_response(payload,pid,build_id):
    if len(payload)!=RESPONSE.size:raise AdapterError('Invalid adapter response length.')
    values=RESPONSE.unpack(payload)
    if values[0]!=MAGIC or values[2]!=pid:raise AdapterError('Adapter response did not match the exact game PID/protocol.')
    if values[-1]!=build_id:raise AdapterBuildMismatch('A different adapter build is already resident; exit and relaunch the game before using this build.')
    if values[1]:raise AdapterError(f'Adapter rejected command: WinError {values[1]}')
    return dict(zip(('magic','status','pid','active','hooks','held','cursor_x','cursor_y','hwnd','foreground_pid','build_id'),values))


class NativeInputAdapter:
    def __init__(self,pid):
        if os.name!='nt':raise AdapterError('Attached input requires Windows.')
        if isinstance(pid,bool) or not isinstance(pid,int) or pid<=0:raise ValueError('An exact positive game PID is required.')
        from ctypes import wintypes as w
        self.pid,self.w=pid,w
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.pipe=f'\\\\.\\pipe\\ashes-lab-input-{pid}'
        self.kernel.CallNamedPipeW.argtypes=[w.LPCWSTR,ctypes.c_void_p,w.DWORD,ctypes.c_void_p,w.DWORD,ctypes.POINTER(w.DWORD),w.DWORD]
        self.kernel.CallNamedPipeW.restype=w.BOOL
        self.kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD]
        self.kernel.OpenProcess.restype=w.HANDLE
        self.kernel.CloseHandle.argtypes=[w.HANDLE]
        self.kernel.QueryFullProcessImageNameW.argtypes=[w.HANDLE,w.DWORD,w.LPWSTR,ctypes.POINTER(w.DWORD)]
        self._verify_process()
        try:self.status()
        except AdapterBuildMismatch:raise
        except AdapterError:self._load()
        self.status()

    def _verify_process(self):
        inventory=json.loads((ROOT/'evidence'/'client_inventory.json').read_text(encoding='utf-8'))
        expected=Path(inventory['exe']).resolve()
        process=self.kernel.OpenProcess(0x1000,False,self.pid)
        if not process:raise AdapterError(f'Cannot verify game PID: WinError {ctypes.get_last_error()}')
        try:
            buffer=ctypes.create_unicode_buffer(32768);length=self.w.DWORD(len(buffer))
            if not self.kernel.QueryFullProcessImageNameW(process,0,buffer,ctypes.byref(length)):raise AdapterError('Cannot verify target executable path.')
            if os.path.normcase(str(Path(buffer.value).resolve()))!=os.path.normcase(str(expected)):raise AdapterError('Attached input targets only the inventoried Ashes executable.')
        finally:self.kernel.CloseHandle(process)
        digest=hashlib.sha256()
        with expected.open('rb') as source:
            for chunk in iter(lambda:source.read(1024*1024),b''):digest.update(chunk)
        if digest.hexdigest()!=inventory['sha256']:raise AdapterError('Client SHA256 changed; review this adapter against the new binary first.')
        if not DLL.is_file():raise AdapterError('Native adapter is not compiled. Run native/input_adapter/build.cmd first.')
        manifest=DLL.parent/'manifest.json'
        if not manifest.is_file():raise AdapterError('Native build manifest is missing; run build.cmd again.')
        manifest_data=json.loads(manifest.read_text(encoding='utf-8'))
        self.version=manifest_data['protocol_version']
        self.build_id=manifest_data.get('build_id',0)
        expected_dll=manifest_data['artifacts'][DLL.name]
        if DLL.stat().st_size!=expected_dll['size'] or hashlib.sha256(DLL.read_bytes()).hexdigest()!=expected_dll['sha256']:
            raise AdapterError('Native adapter does not match the compiled build manifest; rebuild before attaching.')

    def _remote_loader(self):
        """Match the module that actually owns LoadLibraryW, including forwarding."""
        w=self.w;k=self.kernel
        k.GetModuleHandleExW.argtypes=[w.DWORD,ctypes.c_void_p,ctypes.POINTER(w.HMODULE)]
        k.GetModuleFileNameW.argtypes=[w.HMODULE,w.LPWSTR,w.DWORD]
        local=ctypes.cast(k.LoadLibraryW,ctypes.c_void_p).value;owner=w.HMODULE()
        if not k.GetModuleHandleExW(0x6,local,ctypes.byref(owner)):raise AdapterError('Cannot resolve local LoadLibraryW owner.')
        path=ctypes.create_unicode_buffer(32768);k.GetModuleFileNameW(owner,path,len(path))
        class Module(ctypes.Structure):
            _fields_=[('size',w.DWORD),('id',w.DWORD),('pid',w.DWORD),('global_usage',w.DWORD),('process_usage',w.DWORD),('base',ctypes.POINTER(ctypes.c_byte)),('base_size',w.DWORD),('module',w.HMODULE),('name',w.WCHAR*256),('path',w.WCHAR*260)]
        k.CreateToolhelp32Snapshot.argtypes=[w.DWORD,w.DWORD];k.CreateToolhelp32Snapshot.restype=w.HANDLE
        k.Module32FirstW.argtypes=[w.HANDLE,ctypes.POINTER(Module)];k.Module32NextW.argtypes=[w.HANDLE,ctypes.POINTER(Module)]
        snapshot=k.CreateToolhelp32Snapshot(0x18,self.pid)
        if snapshot==ctypes.c_void_p(-1).value:raise AdapterError(f'Cannot inspect game modules: WinError {ctypes.get_last_error()}')
        try:
            entry=Module();entry.size=ctypes.sizeof(entry)
            more=k.Module32FirstW(snapshot,ctypes.byref(entry))
            while more:
                if os.path.normcase(entry.path)==os.path.normcase(path.value):
                    return ctypes.cast(entry.base,ctypes.c_void_p).value+local-owner.value
                more=k.Module32NextW(snapshot,ctypes.byref(entry))
        finally:k.CloseHandle(snapshot)
        raise AdapterError('The target does not contain the matching Windows loader module.')

    def _load(self):
        w=self.w;k=self.kernel
        address=self._remote_loader()
        # CREATE_THREAD | VM_OPERATION | VM_READ | VM_WRITE | QUERY_INFORMATION.
        process=k.OpenProcess(0x43A,False,self.pid)
        if not process:raise AdapterError(f'Cannot attach adapter to verified game: WinError {ctypes.get_last_error()}')
        k.VirtualAllocEx.argtypes=[w.HANDLE,ctypes.c_void_p,ctypes.c_size_t,w.DWORD,w.DWORD];k.VirtualAllocEx.restype=ctypes.c_void_p
        k.VirtualFreeEx.argtypes=[w.HANDLE,ctypes.c_void_p,ctypes.c_size_t,w.DWORD]
        k.WriteProcessMemory.argtypes=[w.HANDLE,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
        k.CreateRemoteThread.argtypes=[w.HANDLE,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_void_p,w.DWORD,ctypes.POINTER(w.DWORD)];k.CreateRemoteThread.restype=w.HANDLE
        k.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD];k.WaitForSingleObject.restype=w.DWORD
        memory=thread=None;finished=False
        try:
            encoded=(str(DLL.resolve())+'\0').encode('utf-16-le');payload=ctypes.create_string_buffer(encoded)
            memory=k.VirtualAllocEx(process,None,len(encoded),0x3000,0x04)
            if not memory:raise AdapterError('Cannot allocate the adapter pathname in the game.')
            written=ctypes.c_size_t()
            if not k.WriteProcessMemory(process,memory,payload,len(encoded),ctypes.byref(written)) or written.value!=len(encoded):raise AdapterError('Cannot copy the fixed adapter pathname to the game.')
            thread=k.CreateRemoteThread(process,None,0,address,memory,0,None)
            if not thread:raise AdapterError(f'Cannot load local adapter: WinError {ctypes.get_last_error()}')
            finished=k.WaitForSingleObject(thread,10000)==0
            if not finished:raise AdapterError('Adapter loading timed out; retry checks its pipe before attempting another load.')
        finally:
            if memory and (finished or not thread):k.VirtualFreeEx(process,memory,0,0x8000)
            if thread:k.CloseHandle(thread)
            k.CloseHandle(process)
        deadline=time.monotonic()+5
        while True:
            try:self.status();return
            except AdapterError:
                if time.monotonic()>=deadline:raise AdapterError('Adapter pipe did not become ready; the client may have refused loading the local DLL.')
                time.sleep(.05)

    def _command(self,command,x=0,y=0):
        if command not in range(6):raise ValueError('Unsupported fixed adapter command.')
        payload=ctypes.create_string_buffer(REQUEST.pack(MAGIC,self.version,command,x,y,0));out=ctypes.create_string_buffer(RESPONSE.size);count=self.w.DWORD()
        if not self.kernel.CallNamedPipeW(self.pipe,payload,REQUEST.size,out,RESPONSE.size,ctypes.byref(count),500):raise AdapterError(f'Adapter pipe unavailable: WinError {ctypes.get_last_error()}')
        return decode_response(out.raw[:count.value],self.pid,self.build_id)

    def status(self):return self._command(0)
    def activate(self):return self._command(1)
    def set_cursor(self,x,y):return self._command(2,x,y)
    def set_key(self,vk,down):return self._command(3,vk,int(bool(down)))
    def deactivate(self):return self._command(4)
    def restore(self):return self._command(5)
