"""UI-only coordinated loading recording, using existing guarded entry and readers."""
import argparse
import json
import sys
import threading
import time
import uuid
from pathlib import Path

from ashes_testing.bridge import Bridge, HOME
from ashes_testing.telemetry import NativeTelemetry, Unavailable, WORKSPACE
from enter_world import enter


def counter_sample(native):
    from dump_runtime_reflection import Reader
    from inspect_movement_prerequisites import MovementProbe
    from protocol_proof import EXPECTED_EXE
    proof = native.proof()
    seed = json.loads(native.seed_path.read_text())
    if not native.same_process(proof, seed['client_proof']):
        raise Unavailable('Counter seed lifetime changed')
    local = seed['local_players']
    if len(local) != 1:
        raise Unavailable('Unique LocalPlayer required')
    reader = Reader(native.pid, EXPECTED_EXE, budget=1024 * 1024)
    try:
        probe = MovementProbe(reader)
        address = int(local[0]['address'], 16)
        local_id = native.identity(probe, address, 'LocalPlayer')
        for key in ('object_index', 'name', 'class', 'serial'):
            if local_id[key] != local[0][key]:
                raise Unavailable('LocalPlayer identity changed')
        links = probe.fields(address, ['PlayerController'])
        controller = native.address(links['PlayerController'])
        identity = native.identity(probe, controller, 'PlayerController')
        vtable = reader.unpack(controller, '<Q')[0]
        targets = [(0xb70, 0x44119b0), (0x910, 0x3ef5810),
                   (0x918, 0x3ef23f0), (0x920, 0x3eea250)]
        for slot, rva in targets:
            if reader.unpack(vtable + slot, '<Q')[0] != reader.base + rva:
                raise Unavailable('Reviewed controller virtual target changed')
        leaves = {
            0x44119b0: '488b0148ffa010090000',
            0x3ef5810: '0fb681f90300000fb6d2448d0455ffffffff33d24403c04585c0410fb6c00f4fd08891f9030000c3',
            0x3ef23f0: 'c681f903000000c3',
            0x3eea250: '80b9f9030000000f97c0c3'}
        for rva, expected in leaves.items():
            raw = bytes.fromhex(expected)
            if reader.read(reader.base + rva, len(raw)) != raw:
                raise Unavailable('Reviewed controller code bytes changed')
        counter = reader.unpack(controller + 0x3f9, '<B')[0]
        if (native.identity(probe, controller, 'PlayerController') != identity or
                probe.fields(address, ['PlayerController']) != links or
                not native.same_process(proof, native.proof())):
            raise Unavailable('Counter binding changed during read')
        return {'counter': counter, 'controller': identity, 'observed_at': time.time(),
                'source': 'native_unreflected_u8_code_guarded_read_only', 'offset': '0x3f9'}
    finally:
        reader.close()


def gameplay_ready(row, proof, epoch):
    native, counter = row['native'], row['counter']
    launch = row['server_state'].get('data', {}).get('client_launch', {})
    joined = [c for c in row['connections'].get('data', []) if c.get('phase') == 'joined']
    floor = native.get('floor', {})
    return bool(native.get('pawn_state', {}).get('Role') == 2 and counter.get('counter') == 0
                and counter.get('controller') == native.get('controller')
                and native.get('world', {}).get('identity', {}).get('name') == 'Verra_World_Master'
                and native.get('movement', {}).get('MovementMode') == 1
                and floor.get('status') == 'read' and floor['fields']['bBlockingHit']
                and floor['fields']['bWalkableFloor'] and not floor['hit']['bStartPenetrating']
                and launch.get('running') and launch.get('world_loaded') and launch.get('gameplay_visible')
                and epoch <= launch.get('world_loaded_at', 0) <= launch.get('gameplay_visible_at', 0)
                and NativeTelemetry.same_process(proof, row['server_state'].get('data', {}).get('client', {}))
                and len(joined) == 1 and not joined[0].get('initialization_error')
                and not joined[0].get('initialization_failed') and len(joined[0].get('stages', [])) == 31
                and {'WorldReady', 'NativeMovementReady', 'GameplayPresentationReady', 'LoadingInputRelease'}
                <= set(joined[0]['stages']))


def trial(pid, created, calibration='ui-calibration-1280.json', early_w=False, start_at=0):
    bridge = Bridge(pid, enable_input=True)
    proof = bridge.native.proof()
    if proof['process_created_filetime'] != created:
        raise Unavailable('Trial lifetime changed')
    bridge.gate.verify(proof, action='ui-entry')
    if early_w:
        lease = bridge.gate.verify(proof, action='movement', key='w', duration=2)
        if lease.get('test_phase') != 'loading-input-block':
            raise Unavailable('An explicit early-loading W test window is required')
    token = uuid.uuid4().hex
    timeline = HOME / 'runs' / ('loading-timeline-' + token + '.jsonl')
    outcome = {'client_proof': proof, 'started_at': time.time(),
               'started_monotonic': time.monotonic(), 'timeline': str(timeline),
               'movement_sent': False, 'server_mutations': False}
    def entry():
        try:
            outcome['entry'] = enter(pid, created, calibration, start_at)
        except Exception as exc:
            outcome['entry_error'] = str(exc)
    worker = threading.Thread(target=entry, daemon=True)
    deadline = time.monotonic() + 150
    ready_at = None
    next_capture = 0
    early_attempted = False
    try:
        with timeline.open('w', encoding='utf-8') as stream:
            worker.start()
            while time.monotonic() < deadline:
                start = time.monotonic()
                bridge.gate.verify(bridge.native.proof(), action='ui-entry')
                row = {'started_at': time.time(), 'started_monotonic': start}
                for key, call in [('counter', lambda: counter_sample(bridge.native)),
                                  ('native', bridge.native.sample),
                                  ('server_state', lambda: bridge.server.get('state')),
                                  ('connections', lambda: bridge.server.get('connections')),
                                  ('world', lambda: bridge.server.get('world'))]:
                    try:
                        row[key] = call()
                    except Exception as exc:
                        row[key] = {'unavailable': str(exc)}
                if start >= next_capture:
                    try:
                        row['capture'] = bridge.capture_screen()
                    except Exception as exc:
                        row['capture'] = {'unavailable': str(exc)}
                    next_capture = start + 1
                row.update(completed_at=time.time(), completed_monotonic=time.monotonic())
                stream.write(json.dumps(row, allow_nan=False) + '\n')
                stream.flush()
                native = row['native']
                counter = row['counter'].get('counter')
                role = native.get('pawn_state', {}).get('Role')
                if not worker.is_alive():
                    if outcome.get('entry_error') or outcome.get('entry', {}).get('status') != 'ui_entry_dispatched':
                        outcome['status'] = 'entry_blocked'
                        break
                    if early_w and not early_attempted and role == 1 and counter == 1:
                        stages = [c for c in row['connections'].get('data', [])
                                  if c.get('phase') == 'joined' and c.get('possession')
                                  and 'LoadingInputRelocked' in c.get('stages', [])
                                  and not {'PawnAutonomous', 'WorldReady'} & set(c.get('stages', []))]
                        if len(stages) == 1:
                            early_attempted = True
                            from early_w_loading import pulse
                            outcome['early_w'] = pulse(bridge, created, counter_sample)
                            if outcome['early_w']['status'] != 'early_w_completed_pending_trace_review':
                                outcome['status'] = 'early_w_blocked'
                                break
                    if gameplay_ready(row, proof, outcome['started_at']):
                        ready_at = ready_at or time.monotonic()
                        if early_w and not early_attempted:
                            outcome['early_w_missed'] = 'No eligible locked window observed; no W input sent'
                        # Retain the later rendered-scene transition as well as native readiness.
                        if time.monotonic() - ready_at >= 45:
                            outcome['status'] = 'recorded_pending_evidence_review'
                            break
                    else:
                        ready_at = None
                time.sleep(max(0, .5 - (time.monotonic() - start)))
        if worker.is_alive():
            outcome['status'] = 'observer_timeout_entry_still_running'
        else:
            outcome.setdefault('status', 'observer_timeout')
        outcome['events'] = bridge._server('events')
        outcome['server_status'] = bridge._server('state')
    except Exception as exc:
        outcome.update(status='blocked', error=str(exc))
    finally:
        lease_path = HOME / 'session-access.json'
        lease = json.loads(lease_path.read_text())
        if lease.get('pid') == pid and lease.get('process_created_filetime') == created:
            lease.update(mode='observation', coordinated_window=False,
                         allowed_actions=[], allowed_keys=[], remaining_pulses=0,
                         reason='UI-only loading trial closed. No movement or jump input sent.')
            lease.pop('expires_at', None)
            lease_path.write_text(json.dumps(lease, indent=2) + '\n')
        worker.join(timeout=5)
        try:
            sys.path.insert(0, str(WORKSPACE))
            from ashes_testing.input import resident_adapter
            from lab.automation import AttachedWindowsDriver
            adapter = resident_adapter(pid)
            AttachedWindowsDriver(pid, adapter=adapter).release_all()
            outcome['controls_released'] = adapter.status()
        except Exception as exc:
            outcome['release_error'] = str(exc)
        outcome.update(finished_at=time.time(), finished_monotonic=time.monotonic())
        outcome = bridge.record('loading-trial', outcome)
    return outcome


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--created-filetime', type=int, required=True)
    parser.add_argument('--calibration', choices=('ui-calibration.json', 'ui-calibration-1280.json'),
                        default='ui-calibration-1280.json')
    parser.add_argument('--early-w', action='store_true', help='Requires an explicit mixed UI/early-W lease')
    parser.add_argument('--start-at', type=int, default=0, help='Resume at a visibly reviewed UI stage index')
    args = parser.parse_args()
    result = trial(args.pid, args.created_filetime, args.calibration, args.early_w, args.start_at)
    print(json.dumps({k: result.get(k) for k in ('status', 'error', 'entry_error', 'timeline',
          'evidence_path', 'controls_released', 'release_error')}, indent=2))
