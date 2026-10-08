"""Use a reviewed resident legacy or C++ input adapter. Never inject a DLL."""
import ctypes
import hashlib
import json
import os
from ctypes import wintypes as w
from pathlib import Path

from .telemetry import WORKSPACE, Unavailable


def loaded_adapter_paths(pid):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    class Module(ctypes.Structure):
        _fields_ = [('size', w.DWORD), ('id', w.DWORD), ('pid', w.DWORD),
                    ('global_usage', w.DWORD), ('process_usage', w.DWORD),
                    ('base', ctypes.POINTER(ctypes.c_byte)), ('base_size', w.DWORD),
                    ('module', w.HMODULE), ('name', w.WCHAR * 256), ('path', w.WCHAR * 260)]
    kernel.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = w.HANDLE
    kernel.Module32FirstW.argtypes = [w.HANDLE, ctypes.POINTER(Module)]
    kernel.Module32NextW.argtypes = [w.HANDLE, ctypes.POINTER(Module)]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    handle = kernel.CreateToolhelp32Snapshot(0x18, pid)
    if handle == ctypes.c_void_p(-1).value:
        raise Unavailable('Cannot inspect resident adapter modules')
    matches = []
    try:
        module = Module()
        module.size = ctypes.sizeof(module)
        more = kernel.Module32FirstW(handle, ctypes.byref(module))
        while more:
            if module.name.lower() == 'ashes_input_adapter.dll':
                matches.append(Path(module.path).resolve())
            more = kernel.Module32NextW(handle, ctypes.byref(module))
    finally:
        kernel.CloseHandle(handle)
    return matches


def loaded_adapter_path(pid):
    matches = loaded_adapter_paths(pid)
    if len(matches) != 1:
        raise Unavailable('Exactly one reviewed input adapter must already be resident; no DLL will be injected')
    return matches[0]


def adapter_contract(path, records):
    allowed = {os.path.normcase(str((WORKSPACE / 'native/input_adapter/build/ashes_input_adapter.dll').resolve())),
               os.path.normcase(str((WORKSPACE / 'CPP/build/msvc/Release/ashes_input_adapter.dll').resolve())),
               os.path.normcase(str((WORKSPACE / 'CPP/runs/loading-readiness-20261008/shift-release-candidate-0c32ad42/ashes_input_adapter.dll').resolve()))}
    canonical = os.path.normcase(str(path.resolve()))
    matches = [row for row in records if os.path.normcase(str(Path(row['path']).resolve())) == canonical]
    if canonical not in allowed or len(matches) != 1:
        raise Unavailable('Resident adapter module path is not reviewed')
    row = matches[0]
    if path.stat().st_size != row['size'] or hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
        raise Unavailable('Resident adapter disk artifact changed; review and refresh its pinned contract')
    if row.get('protocol_version') not in (1, 2) or not isinstance(row.get('build_id'), int):
        raise Unavailable('Pinned adapter wire contract is missing')
    return row


def resident_adapter(pid):
    import sys
    if str(WORKSPACE) not in sys.path:
        sys.path.insert(0, str(WORKSPACE))
    from native.input_adapter.client import NativeInputAdapter, AdapterError
    from protocol_proof import client_proof

    class ResidentAdapter(NativeInputAdapter):
        def _verify_process(self):
            client_proof(self.pid)
            module = loaded_adapter_path(self.pid)
            records = json.loads((WORKSPACE / 'client-testing/vendor/input-adapters.json').read_text(encoding='utf-8-sig'))
            contract = adapter_contract(module, records)
            self.version, self.build_id = contract['protocol_version'], contract['build_id']

        def _load(self):
            raise AdapterError('Resident input IPC unavailable; bridge will not attach a new DLL')

    return ResidentAdapter(pid)
