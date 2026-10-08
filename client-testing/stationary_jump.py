"""One separately released Space pulse and five seconds of read-only trajectory."""
import argparse
import hashlib
import json
import math
import sys
import threading
import time
from pathlib import Path

from ashes_testing.bridge import Bridge, displacement
from ashes_testing.input import resident_adapter
from ashes_testing.telemetry import Unavailable, WORKSPACE
from coordinated_traversal import native_guard
from observe_loading_trial import counter_sample

BACKEND_SHA = '48f210f907f739ff27eb1d0f8a46d6d993d18da76b4de563655ff80257faa941'


def backend_proof(expected_proof):
    import ctypes
    from ctypes import wintypes
    expected = WORKSPACE / 'CPP/build/msvc/Release/ashes_lab.exe'
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    handle = kernel.OpenProcess(0x1000, False, expected_proof['pid'])
    if not handle:
        raise Unavailable('Pinned baseline backend is unavailable')
    try:
        path = ctypes.create_unicode_buffer(32768)
        size, code = wintypes.DWORD(32768), wintypes.DWORD()
        stamps = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:
            raise Unavailable('Pinned baseline backend exited')
        if not kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)) or Path(path.value).resolve() != expected.resolve():
            raise Unavailable('Backend executable changed')
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(s) for s in stamps)):
            raise Unavailable('Backend lifetime unavailable')
        created = (stamps[0].dwHighDateTime << 32) | stamps[0].dwLowDateTime
        if created != expected_proof['process_created_filetime']:
            raise Unavailable('Pinned baseline backend lifetime changed')
        return {'pid': expected_proof['pid'], 'process_created_filetime': created, 'exe': str(expected)}
    finally:
        kernel.CloseHandle(handle)


def jump_guard(before, sample, counter, stationary=False):
    if not 0 <= time.time() - sample['observed_at'] <= .5:
        raise Unavailable('Native sample is stale')
    if not 0 <= time.time() - counter['observed_at'] <= .5:
        raise Unavailable('Loading counter sample is stale')
    if counter['counter'] != 0 or counter['controller'] != sample['controller']:
        raise Unavailable('Exact current gameplay controller must remain unlocked')
    if sample['pawn_state']['Role'] != 2 or sample['movement']['MovementMode'] not in (1, 3):
        raise Unavailable('Autonomous Walking or Falling required during jump')
    for key in ('controller', 'player_state'):
        if sample[key] != before[key]:
            raise Unavailable('Controller, PlayerState or world changed')
    if any(sample['world'][key] != before['world'][key] for key in ('identity', 'level')):
        raise Unavailable('Gameplay world identity changed')
    if sample['player_state']['address'] != sample['pawn_player_state']['address']:
        raise Unavailable('PlayerState possession link changed')
    delta = displacement(before, sample)
    values = [*sample['position_cm'], *sample['movement']['Velocity'], *sample['movement']['Acceleration']]
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
        raise Unavailable('Trajectory must remain finite')
    if delta['horizontal_cm'] > 5 or not -50 <= delta['vertical_cm'] <= 600:
        raise Unavailable('Stationary jump exceeded horizontal or vertical bounds')
    floor = sample.get('floor', {})
    if floor.get('status') == 'read' and floor['hit']['bStartPenetrating']:
        raise Unavailable('Native contact starts penetrating')
    if stationary:
        native_guard(sample, stationary=True)
    return delta


def fixed_profile_guard(player):
    profile = player.get('movement_comparison', {}).get('falling_profile', {})
    expected = {'effective_gravity': -1225.0, 'jump_velocity': 900.0,
                'world_gravity': -980.0, 'movement_gravity_scale': 2.5, 'character_gravity_scale': .5}
    if any(profile.get(k) != v for k, v in expected.items()):
        raise Unavailable('Released verified native gravity/jump profile changed')
    if (profile.get('slow_falling') is not False or profile.get('animation_modifiers') != 0 or
            profile.get('source') != 'current native getter bindings, reflected settings and accepted stat cache'):
        raise Unavailable('Verified native falling profile provenance/guards required')
    return profile


def ready_connection(bridge, proof, connection, epoch, fixed_gravity=False):
    state = bridge.server.get('state')
    if not bridge.native.same_process(proof, state['data'].get('client', {})):
        raise Unavailable('Server client binding changed')
    launch = state['data'].get('client_launch', {})
    if (launch.get('pid') != proof['pid'] or not launch.get('running') or
            not launch.get('world_loaded') or not launch.get('gameplay_visible') or
            not epoch <= launch.get('world_loaded_at', 0) <= launch.get('gameplay_visible_at', 0)):
        raise Unavailable('Current world and presentation epoch must be ready')
    matches = [c for c in bridge.server.get('connections')['data'] if c['id'] == connection]
    if len(matches) != 1:
        raise Unavailable('Unique current connection required')
    c = matches[0]
    required = {'NativeMovementReady', 'GameplayPresentationReady', 'LoadingInputRelease',
                'WorldReady', 'WinsteadCollisionAdmitted', 'NodeLayoutWinsteadFloor'}
    if (c.get('phase') != 'joined' or not c.get('possession') or
            c.get('initialization_failed') or c.get('initialization_error') or
            c.get('selected_character_name') != 'LabExplorer' or len(c.get('stages', [])) != 31 or
            not required <= set(c['stages'])):
        raise Unavailable('Current joined connection must have all readiness stages')
    players = [p for p in bridge.server.get('world')['data']['players'] if p['id'] == connection]
    if len(players) != 1 or players[0].get('tiles') != 2925 or players[0].get('mode') not in (1, 3):
        raise Unavailable('Current world player or expected terrain changed')
    if fixed_gravity:
        fixed_profile_guard(players[0])
    return {'state': state, 'connection': c, 'player': players[0], 'observed_at': time.time()}


def run(pid, created, connection, certificate, duration=.10, backend_pid=722640,
        backend_created=134358967571930830, backend_sha=BACKEND_SHA, fixed_gravity=False):
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not .10 <= duration <= .15:
        raise ValueError('Separate stationary jump release permits only 0.10 to 0.15 seconds')
    bridge = Bridge(pid, enable_input=True)
    result = {'status': 'blocked', 'key': 'space', 'duration': duration, 'connection': connection,
              'started_at': time.time(), 'samples': [], 'key_edges': [], 'movement_sent': False}
    driver = adapter = worker = None
    cancel = threading.Event()
    errors = []
    expected_backend = {'pid': backend_pid, 'process_created_filetime': backend_created, 'sha256': backend_sha}
    try:
        proof = bridge.native.proof()
        result['client_proof'] = proof
        if proof['process_created_filetime'] != created:
            raise Unavailable('Client lifetime changed')
        lease = bridge.gate.verify(proof, action='movement', key='space', duration=duration)
        if (lease.get('test_phase') != 'stationary-space-baseline' or lease.get('allowed_keys') != ['space']
                or lease.get('remaining_pulses') != 1 or lease.get('connection') != connection):
            raise Unavailable('Fresh separately released single Space lease required')
        if lease.get('backend') != expected_backend:
            raise Unavailable('Exact backend proof must match the separately released lease')
        if fixed_gravity and lease.get('falling_profile') != {'effective_gravity': -1225.0, 'jump_velocity': 900.0}:
            raise Unavailable('Fixed-gravity comparison needs its explicit profile release')
        cert = json.loads(certificate.read_text())
        if (cert.get('status') != 'play_resume_native_and_visual_readiness_accepted' or
                cert.get('connection') != connection or not bridge.native.same_process(proof, cert['client_proof'])):
            raise Unavailable('Accepted resume certificate must belong to this connection and lifetime')
        result['backend_proof'] = backend_proof(expected_backend)
        backend = WORKSPACE / 'CPP/build/msvc/Release/ashes_lab.exe'
        result['backend_sha256'] = hashlib.sha256(backend.read_bytes()).hexdigest()
        if result['backend_sha256'] != backend_sha:
            raise Unavailable('Jump comparison requires the released backend artifact')
        result['server_before'] = ready_connection(bridge, proof, connection, cert['play_requested_at'], fixed_gravity)
        before = bridge.native.sample()
        result['before'] = before
        jump_guard(before, before, counter_sample(bridge.native), stationary=True)
        if (not result['server_before']['player'].get('grounded') or
                math.dist(before['position_cm'], result['server_before']['player']['position']) > 1):
            raise Unavailable('Grounded native/server starting positions must agree')
        if before['world']['identity']['name'] != 'Verra_World_Master':
            raise Unavailable('Expected gameplay world required')
        if before['pawn'] != cert['native_final']['pawn'] or before['controller'] != cert['native_final']['controller']:
            raise Unavailable('Resume gameplay identities changed')
        result['screenshot_before'] = bridge.capture_screen()
        adapter = resident_adapter(pid)
        result['adapter_before'] = adapter.status()
        if result['adapter_before']['held'] or result['adapter_before']['active']:
            raise Unavailable('Existing input ownership is not idle')
        class RecordedAdapter:
            def __getattr__(self, name):
                return getattr(adapter, name)
            def set_key(self, vk, down):
                edge = {'vk': vk, 'down': bool(down), 'request_at': time.time()}
                result['key_edges'].append(edge)
                try:
                    response = adapter.set_key(vk, down)
                    edge.update(acknowledged_at=time.time(), held=response['held'])
                    return response
                except Exception as exc:
                    edge['error'] = str(exc)
                    raise
        sys.path.insert(0, str(WORKSPACE))
        from lab.automation import AttachedWindowsDriver
        driver = AttachedWindowsDriver(pid, adapter=RecordedAdapter())
        fresh = bridge.native.sample()
        delta = jump_guard(before, fresh, counter_sample(bridge.native), stationary=True)
        if max(abs(v) for v in delta['delta_cm']) > .1:
            raise Unavailable('Starting pose moved before Space')
        ready_connection(bridge, proof, connection, cert['play_requested_at'], fixed_gravity)
        backend_proof(expected_backend)
        bridge.gate.verify(bridge.native.proof(), action='movement', key='space', duration=duration)
        if json.loads(bridge.gate.path.read_text()) != lease:
            raise Unavailable('Lease changed before reserving Space')
        reserved = {**lease, 'remaining_pulses': 0, 'pulse_reserved_at': time.time()}
        bridge.gate.path.write_text(json.dumps(reserved, indent=2))
        def press():
            try:
                driver.key('space', duration, cancel)
            except Exception as exc:
                errors.append(str(exc))
        worker = threading.Thread(target=press, daemon=True)
        worker.start()
        deadline = time.monotonic() + 5.4  # Includes the existing activation notification delay.
        while time.monotonic() < deadline:
            row = {'started_at': time.time()}
            sample = bridge.native.sample()
            counter = counter_sample(bridge.native)
            row.update(native=sample, counter=counter, delta=jump_guard(before, sample, counter))
            current = bridge.gate.verify(sample['client_proof'], action='movement')
            if current != reserved:
                raise Unavailable('Exclusive jump lease changed')
            backend_proof(expected_backend)
            row['server'] = ready_connection(bridge, proof, connection, cert['play_requested_at'], fixed_gravity)
            row['completed_at'] = time.time()
            result['samples'].append(row)
            if errors:
                raise Unavailable(errors[0])
            time.sleep(.04)
        worker.join(timeout=1)
        if worker.is_alive() or errors:
            raise Unavailable('Space worker did not finish cleanly')
        after = bridge.native.sample()
        result['after'] = after
        result['final_counter'] = counter_sample(bridge.native)
        jump_guard(before, after, result['final_counter'], stationary=True)
        downs = [e for e in result['key_edges'] if e['down']]
        ups = [e for e in result['key_edges'] if not e['down']]
        if (len(downs) != 1 or len(ups) != 1 or downs[0]['vk'] != 32 or
                'acknowledged_at' not in downs[0] or not downs[0].get('held') or
                'acknowledged_at' not in ups[0] or ups[0].get('held') != 0):
            raise Unavailable('Exactly one acknowledged Space down and released up required')
        result['acknowledged_hold_seconds'] = ups[0]['acknowledged_at'] - downs[0]['acknowledged_at']
        result['server_after'] = ready_connection(bridge, proof, connection, cert['play_requested_at'], fixed_gravity)
        result['backend_proof_after'] = backend_proof(expected_backend)
        result['events'] = bridge.server.get('events')
        result['status'] = 'stationary_space_recorded_pending_native_and_server_trajectory_review'
    except Exception as exc:
        result['error'] = str(exc)
    finally:
        cancel.set()
        if worker is not None:
            worker.join(timeout=5)
        if driver is not None:
            try:
                driver.release_all()
                result['focus_proof'] = driver.last_input_proof
            except Exception as exc:
                result['release_error'] = str(exc)
                result['status'] = 'blocked'
        if adapter is not None:
            try:
                result['released'] = adapter.status()
                if result['released']['active'] or result['released']['held']:
                    result['status'] = 'blocked'
            except Exception as exc:
                result['release_error'] = str(exc)
                result['status'] = 'blocked'
        result['movement_sent'] = any(e['down'] for e in result['key_edges'])
        current = json.loads(bridge.gate.path.read_text())
        if current.get('pid') == pid and current.get('process_created_filetime') == created:
            current.update(mode='observation', coordinated_window=False, allowed_actions=[], allowed_keys=[],
                           remaining_pulses=0, reason='Stationary Space baseline closed; controls released.')
            current.pop('expires_at', None)
            bridge.gate.path.write_text(json.dumps(current, indent=2))
        try:
            result['screenshot_after'] = bridge.capture_screen()
        except Exception as exc:
            result['screenshot_after'] = {'unavailable': str(exc)}
        result['finished_at'] = time.time()
        result['scope'] = 'One stationary Space pulse; trajectory and correction evidence, no walking or sprint claim'
        return bridge.record('stationary-space', result)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid', required=True, type=int)
    p.add_argument('--created-filetime', required=True, type=int)
    p.add_argument('--connection', required=True)
    p.add_argument('--certificate', required=True, type=Path)
    p.add_argument('--duration', default=.10, type=float)
    p.add_argument('--backend-pid', default=722640, type=int)
    p.add_argument('--backend-created-filetime', default=134358967571930830, type=int)
    p.add_argument('--backend-sha256', default=BACKEND_SHA)
    p.add_argument('--fixed-gravity', action='store_true')
    a = p.parse_args()
    result = run(a.pid, a.created_filetime, a.connection, a.certificate, a.duration,
                 a.backend_pid, a.backend_created_filetime, a.backend_sha256, a.fixed_gravity)
    print(json.dumps({k: result.get(k) for k in ('status', 'error', 'movement_sent', 'key_edges',
                                             'released', 'evidence_path')}, indent=2))
