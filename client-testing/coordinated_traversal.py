"""One forward-only pulse, with idle/contact guards and monitored cancellation."""
import argparse
import json
import math
import sys
import threading
import time

from ashes_testing.bridge import Bridge, HOME, InputGate, bounded_duration, displacement
from ashes_testing.input import resident_adapter
from ashes_testing.telemetry import Unavailable, WORKSPACE


def native_guard(sample, stationary=False):
    if sample['movement']['MovementMode'] != 1 or sample['pawn_state']['Role'] != 2:
        raise Unavailable('Native autonomous grounded walking required')
    if sample['player_state']['address'] != sample['pawn_player_state']['address']:
        raise Unavailable('Controller and pawn must share PlayerState')
    floor = sample.get('floor', {})
    if stationary and (floor.get('status') != 'read' or not floor['fields']['bBlockingHit'] or
                       not floor['fields']['bWalkableFloor'] or not floor.get('component')):
        raise Unavailable('Native cached walkable blocking floor/component required before/after pulse')
    if floor.get('status') == 'read' and floor['hit']['bStartPenetrating']:
        raise Unavailable('Native floor hit starts penetrating')
    if stationary and any(abs(value) > .1 for name in ('Velocity', 'Acceleration')
                          for value in sample['movement'][name]):
        raise Unavailable('Stationary native player required')


class ComparisonGate(InputGate):
    def __init__(self, keys):
        super().__init__(True)
        self.keys = list(keys)

    def verify(self, proof, action=None, key=None, duration=None):
        lease = super().verify(proof, action=action)
        if (lease.get('test_phase') != 'sprint-comparison' or lease.get('allowed_keys') != self.keys or
                lease.get('connection') is None):
            raise Unavailable('Separately released exact sprint-comparison scope required')
        if key is not None and (key != 'w' or lease.get('remaining_pulses') != 1 or
                                duration is None or not .05 <= duration <= min(1, lease.get('max_key_seconds', 0))):
            raise Unavailable('One bounded reserved comparison pulse required')
        return lease


def run(pid, created, connection, duration=2.0, postready_loading_control=False, sprint_comparison=None):
    bounded_duration(duration)
    bridge = Bridge(pid, enable_input=True)
    combo = ('lshift', 'w') if sprint_comparison == 'shift-w' else ('w',)
    if sprint_comparison is not None:
        if sprint_comparison not in ('w', 'shift-w'):
            raise ValueError('Only W or left-Shift+W comparison is supported')
        bridge.gate = ComparisonGate(combo)
        postready_loading_control = True
    result = {'status': 'blocked', 'key': 'w', 'duration': duration, 'movement_sent': False,
              'started_at': time.time(), 'samples': [], 'key_edges': [], 'connection': connection}
    driver = None
    adapter = None
    worker = None
    cancel = threading.Event()
    try:
        proof = bridge.native.proof()
        result['client_proof'] = proof
        if proof['process_created_filetime'] != created:
            raise Unavailable('Requested client lifetime changed')
        lease = bridge.gate.verify(proof, action='movement', key='w', duration=duration)
        if lease.get('remaining_pulses') != 1 or lease.get('allowed_keys') != list(combo):
            raise Unavailable('A fresh forward-only one-pulse lease is required')
        admission = None
        if postready_loading_control:
            if not sprint_comparison and lease.get('test_phase') != 'postready-loading-control':
                raise Unavailable('An explicit post-ready positive-control lease is required')
        if sprint_comparison:
            if lease.get('connection') != connection:
                raise Unavailable('Released comparison connection changed')
            from stationary_jump import backend_proof
            import hashlib
            expected_backend = lease.get('backend', {})
            result['backend_proof'] = backend_proof(expected_backend)
            sha = hashlib.sha256((WORKSPACE / 'CPP/build/msvc/Release/ashes_lab.exe').read_bytes()).hexdigest()
            if sha != expected_backend.get('sha256'):
                raise Unavailable('Released comparison backend artifact changed')
            result.update(sprint_comparison=sprint_comparison, keys=list(combo), backend_sha256=sha)
        elif not postready_loading_control:
            admission = json.loads((WORKSPACE / 'CPP/runs/settlement-probe-20261008/collision-admission.json').read_text())
            if not admission.get('ok') or not bridge.native.same_process(proof, admission['proof']['client_proof']):
                raise Unavailable('Collision admission belongs to another lifetime')
        state = bridge.server.get('state')
        if not bridge.native.same_process(proof, state['data'].get('client', {})):
            raise Unavailable('Server attachment changed')
        if postready_loading_control:
            launch = state['data'].get('client_launch', {})
            if (launch.get('pid') != pid or not launch.get('running') or
                    not launch.get('gameplay_visible') or not launch.get('world_loaded') or
                    not 0 < launch.get('world_loaded_at', 0) <= launch.get('gameplay_visible_at', 0)):
                raise Unavailable('Current client must have completed world loading and presentation')
        connections = bridge.server.get('connections')['data']
        ready = [c for c in connections if c['id'] == connection and c.get('phase') == 'joined'
                 and c.get('possession') and not c.get('initialization_failed') and not c.get('initialization_error')
                 and c.get('speed_synced') == 600 and c.get('selected_character_name') == 'LabExplorer'
                 and {'ActivateMovement', 'NodeLayoutWinsteadFloor'} <= set(c.get('stages', []))]
        if len(ready) != 1:
            raise Unavailable('Unique initialized floor-stage connection required')
        if postready_loading_control and (len(ready[0].get('stages', [])) < 31 or
                not {'LoadingInputRelocked', 'NativeMovementReady', 'GameplayPresentationReady',
                     'LoadingInputRelease', 'WorldReady', 'WinsteadCollisionAdmitted'} <= set(ready[0]['stages'])):
            raise Unavailable('All current loading readiness stages must be completed')
        def server_player():
            players = [p for p in bridge.server.get('world')['data']['players'] if p['id'] == connection]
            if len(players) != 1 or not players[0].get('grounded') or players[0].get('mode') != 1:
                raise Unavailable('Grounded current server player required')
            if players[0].get('tiles') != 2925 or players[0].get('geometry', {}).get('tiles') != 2925:
                raise Unavailable('Expected private base2669 plus256 floor tiles required')
            return players[0]
        result['server_before'] = server_player()
        result['before'] = bridge.native.sample()
        native_guard(result['before'], stationary=True)
        def ready_counter(sample):
            if not postready_loading_control:
                return
            from observe_loading_trial import counter_sample
            value = counter_sample(bridge.native)
            if value['counter'] != 0 or value['controller'] != sample['controller']:
                raise Unavailable('Current exact controller loading input must be unlocked')
            result.setdefault('counter_samples', []).append(value)
        ready_counter(result['before'])
        if math.dist(result['before']['position_cm'], result['server_before']['position']) > 1:
            raise Unavailable('Native/server starting positions disagree')
        # Verify the admitted loaded level still has the same live weak identity.
        from dump_runtime_reflection import Reader
        from inspect_movement_prerequisites import MovementProbe
        from protocol_proof import EXPECTED_EXE
        if admission is not None:
            reader = Reader(pid, EXPECTED_EXE, budget=1024*1024)
            try:
                probe = MovementProbe(reader)
                expected = admission['proof']['placement']['loaded_level']
                actual = bridge.native.identity(probe, int(expected['address'], 16), 'Level')
                if any(actual[k] != expected[k] for k in ('address', 'object_index', 'serial', 'outer_address')):
                    raise Unavailable('Admitted loaded floor level identity changed')
                visible = probe.fields(int(actual['address'], 16), ['bIsVisible'])['bIsVisible']
                if visible.get('status') != 'read' or visible.get('value') is not True:
                    raise Unavailable('Admitted floor level is no longer visible')
            finally:
                reader.close()
        else:
            result['scope'] = 'Post-ready input positive control at live grounded spawn; no platform seam traversal claim'
        result['screenshot_before'] = bridge.capture_screen()
        sys.path.insert(0, str(WORKSPACE))
        from lab.automation import AttachedWindowsDriver
        adapter = resident_adapter(pid)
        result['adapter_before'] = adapter.status()
        if result['adapter_before']['active'] or result['adapter_before']['held']:
            raise Unavailable('Adapter already active; input ownership uncertain')
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
        if sprint_comparison:
            from sprint_driver import SprintDriver
            driver = SprintDriver(pid, adapter=RecordedAdapter())
        else:
            driver = AttachedWindowsDriver(pid, adapter=RecordedAdapter())
        if postready_loading_control:
            fresh = bridge.native.sample()
            native_guard(fresh, stationary=True)
            ready_counter(fresh)
            delta = displacement(result['before'], fresh)
            if any(abs(v) > .1 for v in delta['delta_cm']):
                raise Unavailable('Grounded starting pose changed before the positive-control pulse')
            server_player()
        bridge.gate.verify(bridge.native.proof(), action='movement', key='w', duration=duration)
        current = json.loads(bridge.gate.path.read_text())
        if current != lease:
            raise Unavailable('Lease changed before reserving the pulse')
        current.update(remaining_pulses=0, pulse_reserved_at=time.time())
        bridge.gate.path.write_text(json.dumps(current, indent=2))
        errors = []
        def input_worker():
            try:
                if sprint_comparison:
                    driver.combo(combo, duration, cancel)
                else:
                    driver.key('w', duration, cancel)
            except Exception as exc:
                errors.append(str(exc))
        worker = threading.Thread(target=input_worker, daemon=True)
        result['movement_sent'] = True
        worker.start()
        while worker.is_alive():
            sample = bridge.native.sample()
            native_guard(sample)
            ready_counter(sample)
            displacement(result['before'], sample)  # Same pawn/root/component/lifetime.
            if sprint_comparison:
                backend_proof(expected_backend)
                delta = displacement(result['before'], sample)
                if (delta['horizontal_cm'] > 900 or abs(delta['vertical_cm']) > 50 or
                        sample['controller'] != result['before']['controller'] or
                        sample['world']['identity'] != result['before']['world']['identity']):
                    raise Unavailable('Grounded comparison exceeded route bounds or changed world/controller')
            bridge.gate.verify(sample['client_proof'], action='movement')
            server_player()
            corrections = []
            for event in bridge.server.get('events')['data']:
                if event.get('kind') != 'movement' or event.get('ts', 0) < result['started_at']:
                    continue
                detail = json.loads(event['detail'])
                if detail.get('connection_id') == connection:
                    trace = detail.get('result', {})
                    if trace.get('force_correction') or trace.get('response') == 'correction':
                        corrections.append(event['id'])
            if len(corrections) >= 2:
                result['correction_events'] = corrections
                raise Unavailable('Repeated server corrections during the pulse')
            result['samples'].append(sample)
            time.sleep(.1)
        worker.join()
        if errors:
            raise Unavailable(errors[0])
        deadline = time.monotonic() + 3
        while True:
            after = bridge.native.sample()
            native_guard(after)
            if all(abs(v) <= .1 for v in after['movement']['Velocity']):
                native_guard(after, stationary=True)
                ready_counter(after)
                result['after'] = after
                break
            if time.monotonic() > deadline:
                raise Unavailable('Player failed to stop after released W')
            time.sleep(.1)
        result['server_after'] = server_player()
        result['comparison'] = displacement(result['before'], result['after'])
        result['status'] = 'pulse_completed_pending_trace_review'
    except Exception as exc:
        result['error'] = str(exc)
    finally:
        cancel.set()
        if worker is not None and worker.is_alive():
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
        result['movement_sent'] = any(edge['down'] and edge['vk'] == 87 for edge in result['key_edges'])
        result['input_requested'] = any(edge['down'] for edge in result['key_edges'])
        lease = json.loads(bridge.gate.path.read_text())
        if lease.get('pid') == pid and lease.get('process_created_filetime') == created:
            lease.update(mode='observation', coordinated_window=False, allowed_actions=[], allowed_keys=[],
                         remaining_pulses=0, reason='Single forward pulse finished/blocked; released. No second pulse until CPP trace review and fresh release.')
            lease.pop('expires_at', None)
            bridge.gate.path.write_text(json.dumps(lease, indent=2))
        for name, operation in (('final_native', bridge.get_player_state), ('final_world', bridge.get_world_state),
                                ('screenshot_after', bridge.capture_screen)):
            try:
                result[name] = operation()
            except Exception as exc:
                result[name] = {'unavailable': str(exc)}
        result['finished_at'] = time.time()
        result['evidence_scope'] = 'One forward pulse; cached contact and displacement, pending CPP movement trace review'
        return bridge.record('traversal', result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--created-filetime', type=int, required=True)
    parser.add_argument('--connection', required=True)
    parser.add_argument('--duration', type=float, default=2.0)
    parser.add_argument('--postready-loading-control', action='store_true',
                        help='Requires a separately released post-ready control lease and all loading gates')
    parser.add_argument('--sprint-comparison', choices=('w', 'shift-w'),
                        help='Requires separately released one-pulse sprint-comparison scope; at most one second')
    args = parser.parse_args()
    result = run(args.pid, args.created_filetime, args.connection, args.duration,
                 args.postready_loading_control, args.sprint_comparison)
    print(json.dumps({k: result.get(k) for k in ('status', 'error', 'movement_sent', 'key_edges', 'comparison',
                                               'focus_proof', 'released', 'evidence_path')}, indent=2))
