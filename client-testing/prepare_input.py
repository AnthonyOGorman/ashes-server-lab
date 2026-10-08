"""Explicit, coordinated setup of the existing reviewed adapter; no movement."""
import argparse
import json
import sys
import time
from pathlib import Path

from ashes_testing.bridge import Bridge, HOME
from ashes_testing.input import adapter_contract, loaded_adapter_paths, resident_adapter
from ashes_testing.telemetry import NativeTelemetry, Unavailable, WORKSPACE


def prepare(pid, created, attach_legacy=False, attach_cpp=False):
    if attach_legacy and attach_cpp:
        raise Unavailable('Choose exactly one reviewed adapter attachment profile')
    native = NativeTelemetry(pid)
    proof = native.proof()
    if proof['process_created_filetime'] != created:
        raise Unavailable('Requested process lifetime changed')
    bridge = Bridge(pid, enable_input=True, native=native)
    bridge.gate.verify(proof, action='adapter-setup')
    paths = loaded_adapter_paths(pid)
    attached = False
    if not paths:
        if attach_cpp:
            from reviewed_cpp_adapter import attach
            adapter = attach(pid, created)
            attached = True
            paths = loaded_adapter_paths(pid)
        elif not attach_legacy:
            raise Unavailable('No resident adapter; explicit legacy attachment flag required')
        else:
            sys.path.insert(0, str(WORKSPACE))
            from native.input_adapter.client import NativeInputAdapter, DLL
            records = json.loads((HOME / 'vendor/input-adapters.json').read_text())
            adapter_contract(DLL, records)
            bridge.gate.verify(native.proof(), action='adapter-setup')
            adapter = NativeInputAdapter(pid)
            attached = True
            paths = loaded_adapter_paths(pid)
            if paths != [DLL.resolve()]:
                adapter.deactivate()
                raise Unavailable('Unexpected adapter module after attachment')
    else:
        if attach_cpp:
            raise Unavailable('Explicit CPP attachment refuses any resident adapter')
        adapter = resident_adapter(pid)
    before = adapter.status()
    if before['held'] or before['active']:
        raise Unavailable('Adapter was already active; concurrent input ownership is uncertain')
    driver = None
    try:
        bridge.gate.verify(native.proof(), action='adapter-setup')
        from lab.automation import AttachedWindowsDriver
        driver = AttachedWindowsDriver(pid, adapter=adapter)
        activated = driver._activate_adapter()
        driver.release_all()
        after = adapter.status()
        proof_after = native.proof()
        bridge.gate.verify(proof_after, action='adapter-setup')
        if after['held'] or after['active']:
            raise Unavailable('Adapter failed to release/deactivate')
        ready = bool(activated['hooks'] and driver.last_input_proof['unchanged'])
        return bridge.record('input-ready', {
            'ready': ready, 'readiness_issue': None if ready else 'Adapter hooks or desktop focus/cursor guard changed',
            'client_proof': proof_after, 'adapter_path': str(paths[0]),
            'attached_reviewed_legacy': attached and not attach_cpp,
            'attached_reviewed_cpp': attached and attach_cpp, 'before': before, 'activated': activated,
            'released': after, 'focus_proof': driver.last_input_proof,
            'movement_sent': False, 'observed_at': time.time()})
    finally:
        if driver is not None:
            driver.release_all()
        else:
            adapter.deactivate()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--created-filetime', type=int, required=True)
    profiles = parser.add_mutually_exclusive_group()
    profiles.add_argument('--attach-reviewed-legacy', action='store_true')
    profiles.add_argument('--attach-reviewed-cpp', action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare(args.pid, args.created_filetime, args.attach_reviewed_legacy, args.attach_reviewed_cpp), indent=2))
