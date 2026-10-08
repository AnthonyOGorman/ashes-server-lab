"""One W pulse to test loading input suppression; never activates server movement."""
import json
import math
import sys
import threading
import time

from ashes_testing.bridge import HOME, bounded_duration, displacement
from ashes_testing.input import resident_adapter
from ashes_testing.telemetry import NativeTelemetry, Unavailable, WORKSPACE


def locked_idle(sample, counter):
    if sample.get('pawn_state', {}).get('Role') != 1:
        raise Unavailable('Fresh simulated-role loading pawn required')
    if counter.get('counter') != 1 or counter.get('controller') != sample.get('controller'):
        raise Unavailable('Same current controller loading counter one required')
    if not 0 <= time.time() - counter.get('observed_at', 0) <= .5:
        raise Unavailable('Loading counter observation is stale')
    if not 0 <= time.time() - sample.get('observed_at', 0) <= .5:
        raise Unavailable('Loading pawn observation is stale')
    if sample.get('movement', {}).get('MovementMode') not in (1, 3):
        raise Unavailable('Reviewed loading walking/falling mode required')
    for name in ('Velocity', 'Acceleration'):
        value = sample['movement'].get(name)
        if (not isinstance(value, list) or len(value) != 3 or
                any(not isinstance(v, (int, float)) or not math.isfinite(v) or abs(v) > .1 for v in value)):
            raise Unavailable('Zero native loading velocity/acceleration required')


def loading_connection(bridge, expected=None):
    connections = bridge.server.get('connections')
    matches = [c for c in connections['data'] if c.get('phase') == 'joined'
               and c.get('possession') and c.get('selected_character_name') == 'LabExplorer'
               and 'LoadingInputRelocked' in c.get('stages', [])
               and not {'PawnAutonomous', 'WorldReady'} & set(c.get('stages', []))
               and not c.get('initialization_failed') and (expected is None or c['id'] == expected)]
    if len(matches) != 1:
        raise Unavailable('Unique post-possession locked, pre-autonomous connection required')
    return matches[0]


def pulse(bridge, created, counter_reader, duration=2):
    bounded_duration(duration)
    result = {'status': 'blocked', 'key': 'w', 'duration': duration, 'samples': [],
              'key_edges': [], 'movement_sent': False, 'server_mutations': False,
              'started_at': time.time(), 'claim': 'Loading suppression only; no ground route or jump/sprint acceptance'}
    adapter = driver = worker = None
    cancel = threading.Event()
    try:
        proof = bridge.native.proof()
        result['client_proof'] = proof
        if proof['process_created_filetime'] != created:
            raise Unavailable('Early W client lifetime changed')
        lease = bridge.gate.verify(proof, action='movement', key='w', duration=duration)
        if (lease.get('test_phase') != 'loading-input-block' or
                lease.get('remaining_pulses') != 1 or lease.get('allowed_keys') != ['w']):
            raise Unavailable('Fresh explicit early-loading W-only one-pulse lease required')
        result['server_attachment'] = bridge.server.get('state')
        if not NativeTelemetry.same_process(proof, result['server_attachment']['data'].get('client', {})):
            raise Unavailable('Server attachment does not match exact early-W client lifetime')
        result['connection_before'] = loading_connection(bridge)
        connection = result['connection_before']['id']
        result['before'] = bridge.native.sample()
        result['counter_before'] = counter_reader(bridge.native)
        locked_idle(result['before'], result['counter_before'])
        result['server_before'] = bridge._server('world')
        sys.path.insert(0, str(WORKSPACE))
        from lab.automation import AttachedWindowsDriver
        adapter = resident_adapter(proof['pid'])
        result['adapter_before'] = adapter.status()
        if result['adapter_before']['active'] or result['adapter_before']['held']:
            raise Unavailable('Resident adapter already active; concurrent input ownership uncertain')
        class RecordedAdapter:
            def __getattr__(self, name):
                return getattr(adapter, name)
            def set_key(self, vk, down):
                start = time.time()
                edge = {'vk': vk, 'down': bool(down), 'request_at': start}
                result['key_edges'].append(edge)
                try:
                    response = adapter.set_key(vk, down)
                except Exception as exc:
                    edge['error'] = str(exc)
                    raise
                edge.update(acknowledged_at=time.time(), held=response['held'])
                return response
        driver = AttachedWindowsDriver(proof['pid'], adapter=RecordedAdapter())
        # Recheck current role/counter/connection immediately before reserving input.
        before = bridge.native.sample()
        counter = counter_reader(bridge.native)
        locked_idle(before, counter)
        delta = displacement(result['before'], before)
        if any(abs(v) > .1 for v in delta['delta_cm']):
            raise Unavailable('Loading pose was not stable before W input')
        loading_connection(bridge, connection)
        bridge.gate.verify(bridge.native.proof(), action='movement', key='w', duration=duration)
        current = json.loads(bridge.gate.path.read_text())
        if current != lease:
            raise Unavailable('Early W lease changed before reservation')
        current.update(remaining_pulses=0, pulse_reserved_at=time.time())
        bridge.gate.path.write_text(json.dumps(current, indent=2) + '\n')
        errors = []
        def run_key():
            try:
                driver.key('w', duration, cancel)
            except Exception as exc:
                errors.append(str(exc))
        worker = threading.Thread(target=run_key, daemon=True)
        worker.start()
        while worker.is_alive():
            started = time.time()
            sample = bridge.native.sample()
            counter = counter_reader(bridge.native)
            row = {'started_at': started, 'native': sample, 'counter': counter,
                   'server': bridge._server('world')}
            result['samples'].append(row)
            locked_idle(sample, counter)
            delta = displacement(result['before'], sample)
            if any(abs(v) > .1 for v in delta['delta_cm']):
                raise Unavailable('Native pose moved during loading W hold')
            bridge.gate.verify(sample['client_proof'], action='movement')
            loading_connection(bridge, connection)
            cancel.wait(.05)
        if errors:
            raise Unavailable('; '.join(errors))
        result['after'] = bridge.native.sample()
        result['counter_after'] = counter_reader(bridge.native)
        locked_idle(result['after'], result['counter_after'])
        result['connection_after'] = loading_connection(bridge, connection)
        result['displacement'] = displacement(result['before'], result['after'])
        if any(abs(v) > .1 for v in result['displacement']['delta_cm']):
            raise Unavailable('Native pose changed after loading W hold')
        downs = [e for e in result['key_edges'] if e['vk'] == 0x57 and e['down'] and e.get('acknowledged_at')]
        ups = [e for e in result['key_edges'] if e['vk'] == 0x57 and not e['down'] and e.get('acknowledged_at')]
        if len(downs) != 1 or not ups or not downs[0]['held'] or ups[-1]['held']:
            raise Unavailable('Exactly one acknowledged W hold and release required')
        result['acknowledged_hold_seconds'] = ups[0]['acknowledged_at'] - downs[0]['acknowledged_at']
        result['status'] = 'early_w_completed_pending_trace_review'
    except Exception as exc:
        result['error'] = str(exc)
    finally:
        cancel.set()
        if worker:
            worker.join(timeout=5)
            if worker.is_alive():
                result.update(status='blocked', release_error='Early W input worker did not finish')
        if driver:
            try:
                driver.release_all()
                result['focus_proof'] = driver.last_input_proof
            except Exception as exc:
                result.update(status='blocked', release_error=str(exc))
        if adapter:
            result['released'] = adapter.status()
            if result['released']['active'] or result['released']['held']:
                result.update(status='blocked', release_error='Early W adapter cleanup failed')
        result['movement_sent'] = any(e['down'] and e['vk'] == 0x57 for e in result['key_edges'])
        result['input_delivery_uncertain'] = any(e['down'] and not e.get('acknowledged_at') for e in result['key_edges'])
        result['finished_at'] = time.time()
        result = bridge.record('early-w-loading', result)
    return result
