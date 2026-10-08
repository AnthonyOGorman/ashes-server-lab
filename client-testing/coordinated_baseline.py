"""One explicitly coordinated three-second W baseline, with recorded key edges."""
import argparse
import json
import sys
import threading
import time

from ashes_testing.bridge import Bridge, displacement
from ashes_testing.input import resident_adapter
from ashes_testing.telemetry import WORKSPACE, Unavailable


def baseline(pid, created):
    bridge = Bridge(pid, enable_input=True)
    proof = bridge.native.proof()
    if proof['process_created_filetime'] != created:
        raise Unavailable('Requested process lifetime changed')
    bridge.gate.verify(proof, action='movement', key='w', duration=3.0)
    server_state = bridge.server.get('state')
    if not bridge.native.same_process(proof, server_state['data'].get('client', {})):
        raise Unavailable('Server is attached to another client lifetime')
    connections = bridge.server.get('connections')
    ready = [c for c in connections['data'] if c.get('phase') == 'joined'
             and c.get('possession') and not c.get('initialization_failed')
             and not c.get('initialization_error') and 'ActivateMovement' in c.get('stages', [])
             and c.get('speed_synced') == 600 and c.get('selected_character_name') == 'LabExplorer']
    if len(ready) != 1:
        raise Unavailable('Unique initialized LabExplorer with ActivateMovement and speed 600 required')
    world = bridge.server.get('world')
    players = [p for p in world['data']['players'] if p['id'] == ready[0]['id']]
    if (len(players) != 1 or not players[0].get('grounded') or players[0].get('mode') != 1
            or players[0].get('tiles', 0) <= 0 or players[0].get('colliders', 0) <= 0):
        raise Unavailable('Current grounded server player with available terrain required')
    sys.path.insert(0, str(WORKSPACE))
    from lab.automation import AttachedWindowsDriver
    adapter = resident_adapter(pid)
    initial_status = adapter.status()
    if initial_status['active'] or initial_status['held']:
        raise Unavailable('Adapter already active; input ownership is uncertain')
    edges = []

    class RecordedAdapter:
        def __getattr__(self, name):
            return getattr(adapter, name)

        def set_key(self, vk, down):
            start = time.time()
            result = adapter.set_key(vk, down)
            edges.append({'vk': vk, 'down': bool(down), 'request_at': start,
                          'acknowledged_at': time.time(), 'held': result['held']})
            return result

    driver = AttachedWindowsDriver(pid, adapter=RecordedAdapter())
    result = {'status': 'blocked', 'client_proof': proof, 'key': 'w', 'duration': 3.0,
              'key_edges': edges, 'started_at': time.time(),
              'server_ready': ready[0], 'server_world_before': players[0]}
    try:
        result['before'] = bridge.native.sample()
        if result['before']['movement']['MovementMode'] != 1:
            raise Unavailable('Grounded walking mode required for this baseline')
        bridge.gate.verify(result['before']['client_proof'], action='movement', key='w', duration=3.0)
        driver.key('w', 3.0, threading.Event())
        result['after'] = bridge.native.sample()
        result['comparison'] = displacement(result['before'], result['after'])
        result['grounded_after'] = result['after']['movement']['MovementMode'] == 1
        result['focus_proof'] = driver.last_input_proof
        result['status'] = 'completed'
    except Exception as exc:
        result['error'] = str(exc)
    finally:
        driver.release_all()
        result['released'] = adapter.status()
        result['finished_at'] = time.time()
        if result['released']['held'] or result['released']['active']:
            result['status'] = 'blocked'
            result['release_error'] = 'Adapter failed to release/deactivate'
        if driver.last_input_proof and driver.last_input_proof['foreground_changed_to_game']:
            result['status'] = 'blocked'
            result['focus_error'] = 'Desktop foreground changed to game'
        result['evidence_scope'] = 'One coordinated W pulse; movement correctness requires server trace correlation'
        recorded = bridge.record('baseline', result)
    return recorded


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--created-filetime', type=int, required=True)
    args = parser.parse_args()
    try:
        r = baseline(args.pid, args.created_filetime)
    except Exception as exc:
        r = Bridge(args.pid).record('baseline', {'status': 'blocked', 'error': str(exc),
            'movement_sent': False, 'requested_pid': args.pid,
            'requested_created_filetime': args.created_filetime, 'observed_at': time.time()})
    print(json.dumps({k: r.get(k) for k in ('status', 'error', 'started_at', 'finished_at',
          'key_edges', 'comparison', 'focus_proof', 'released', 'evidence_path')}, indent=2))
