"""Attach only the reviewed immutable CPP adapter to a released fresh client."""
import ctypes
import hashlib
import json
import sys
import time

from ashes_testing.bridge import HOME, InputGate
from ashes_testing.input import adapter_contract, loaded_adapter_paths
from ashes_testing.telemetry import NativeTelemetry, Unavailable, WORKSPACE

CPP_CANDIDATE = WORKSPACE / 'CPP/runs/loading-readiness-20261008/shift-release-candidate-0c32ad42'
CPP_DLL = CPP_CANDIDATE / 'ashes_input_adapter.dll'


def reviewed_contract():
    records = json.loads((HOME / 'vendor/input-adapters.json').read_text())
    row = adapter_contract(CPP_DLL, records)
    manifest = CPP_CANDIDATE / 'manifest.json'
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != row.get('manifest_sha256'):
        raise Unavailable('CPP candidate manifest changed')
    data = json.loads(manifest.read_text())
    if (data.get('status') != 'release_fixture_passed_not_adopted' or data.get('fixture_exit_code') != 0 or
            data.get('protocol_version') != row['protocol_version'] or data.get('build_id') != row['build_id']):
        raise Unavailable('Reviewed Release fixture and wire contract required')
    for name, expected in data['artifacts'].items():
        if name not in ('adapter.cpp', 'fixture.cpp', 'protocol.h', 'build_tag.h',
                        'ashes_input_adapter.dll', 'ashes_input_fixture.exe'):
            raise Unavailable('Unreviewed candidate artifact')
        artifact = CPP_CANDIDATE / name
        if artifact.stat().st_size != expected['size'] or hashlib.sha256(artifact.read_bytes()).hexdigest() != expected['sha256']:
            raise Unavailable('CPP candidate source or fixture changed')
    return row


def attach(pid, created):
    # Explicit setup lease precedes all process/module/loader operations.
    native = NativeTelemetry(pid)
    proof = native.proof()
    if proof['process_created_filetime'] != created:
        raise Unavailable('Requested fresh client lifetime changed')
    gate = InputGate(True)
    lease = gate.verify(proof, action='adapter-setup')
    if lease.get('adapter_profile') != 'cpp-release-shift-0c32ad42':
        raise Unavailable('CPP adapter attachment requires its explicit released profile')
    reviewed_contract()
    if loaded_adapter_paths(pid):
        raise Unavailable('Refuse CPP attachment with any input adapter already resident')
    sys.path.insert(0, str(WORKSPACE))
    from native.input_adapter.client import NativeInputAdapter, AdapterError

    class ReviewedCppAdapter(NativeInputAdapter):
        def _verify_process(self):
            fresh = native.proof()
            gate.verify(fresh, action='adapter-setup')
            if not native.same_process(proof, fresh):
                raise Unavailable('Client identity changed before adapter attachment')
            row = reviewed_contract()
            self.version, self.build_id = row['protocol_version'], row['build_id']

        def _load(self):
            # Existing reviewed LoadLibraryW-owner algorithm. Only the fixed,
            # pinned pathname is written; no caller-supplied address or function.
            self._verify_process()
            if loaded_adapter_paths(pid):
                raise Unavailable('An input adapter appeared before CPP attachment')
            w, k = self.w, self.kernel
            address = self._remote_loader()
            gate.verify(native.proof(), action='adapter-setup')
            process = k.OpenProcess(0x43A, False, pid)
            if not process:
                raise AdapterError('Cannot open verified fresh client for fixed DLL attachment')
            k.VirtualAllocEx.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.c_size_t, w.DWORD, w.DWORD]
            k.VirtualAllocEx.restype = ctypes.c_void_p
            k.VirtualFreeEx.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.c_size_t, w.DWORD]
            k.WriteProcessMemory.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
            k.CreateRemoteThread.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)]
            k.CreateRemoteThread.restype = w.HANDLE
            k.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
            k.WaitForSingleObject.restype = w.DWORD
            memory = thread = None
            finished = False
            try:
                encoded = (str(CPP_DLL.resolve()) + '\0').encode('utf-16-le')
                payload = ctypes.create_string_buffer(encoded)
                memory = k.VirtualAllocEx(process, None, len(encoded), 0x3000, 0x04)
                if not memory:
                    raise AdapterError('Cannot allocate the fixed reviewed DLL pathname')
                written = ctypes.c_size_t()
                if not k.WriteProcessMemory(process, memory, payload, len(encoded), ctypes.byref(written)) or written.value != len(encoded):
                    raise AdapterError('Cannot copy the fixed reviewed DLL pathname')
                self._verify_process()
                if loaded_adapter_paths(pid):
                    raise Unavailable('An adapter became resident before LoadLibrary')
                thread = k.CreateRemoteThread(process, None, 0, address, memory, 0, None)
                if not thread:
                    raise AdapterError('Cannot load the fixed reviewed CPP adapter')
                finished = k.WaitForSingleObject(thread, 10000) == 0
                if not finished:
                    raise AdapterError('Reviewed CPP attachment timed out; do not retry on this lifetime')
            finally:
                if memory and (finished or not thread):
                    k.VirtualFreeEx(process, memory, 0, 0x8000)
                if thread:
                    k.CloseHandle(thread)
                k.CloseHandle(process)
            deadline = time.monotonic() + 5
            while True:
                try:
                    self.status()
                    break
                except AdapterError:
                    if time.monotonic() >= deadline:
                        raise AdapterError('Reviewed CPP adapter IPC unavailable after attachment')
                    time.sleep(.05)

    adapter = ReviewedCppAdapter(pid)
    if loaded_adapter_paths(pid) != [CPP_DLL.resolve()]:
        adapter.deactivate()
        raise Unavailable('Unexpected resident module after reviewed CPP attachment')
    fresh = native.proof()
    gate.verify(fresh, action='adapter-setup')
    if not native.same_process(proof, fresh):
        adapter.deactivate()
        raise Unavailable('Exact client lifetime changed during attachment')
    return adapter
