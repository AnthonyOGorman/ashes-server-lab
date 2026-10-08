"""Offline review of the completed Play-only resume; no live reads or input."""
import hashlib
import json
import time
from pathlib import Path

from ashes_testing.bridge import Bridge, HOME


def review(trial_path, connection, visual_confirmed):
    if not visual_confirmed:
        raise ValueError('Inspect the saved final game image before certifying visual readiness')
    trial = json.loads(trial_path.read_text())
    timeline = Path(trial['timeline'])
    rows = [json.loads(line) for line in timeline.read_text().splitlines()]
    final = rows[-1]
    native = final['native']
    play = Path(trial['entry']['steps'][-1]['action_evidence'])
    action = json.loads(play.read_text())
    ready = [r for r in rows if r['native'].get('pawn_state', {}).get('Role') == 2
             and r['counter'].get('counter') == 0
             and r['counter']['controller'] == r['native']['controller']
             and r['native']['world']['identity']['name'] == 'Verra_World_Master'
             and r['native']['observed_at'] > action['requested_at']]
    c = next(c for c in final['connections']['data'] if c['id'] == connection)
    server = next(p for p in final['world']['data']['players'] if p['id'] == connection)
    assert c['phase'] == 'joined' and len(c['stages']) == 31
    assert not c['initialization_failed'] and not c['initialization_error']
    assert native['movement']['MovementMode'] == 1
    assert all(v == 0 for k in ('Velocity', 'Acceleration') for v in native['movement'][k])
    assert native['floor']['fields']['bWalkableFloor'] and native['floor']['fields']['bBlockingHit']
    assert not native['floor']['hit']['bStartPenetrating']
    assert trial['controls_released']['held'] == trial['controls_released']['active'] == 0
    assert not trial['movement_sent'] and not trial['server_mutations']
    capture = next(r['capture'] for r in reversed(rows) if r.get('capture', {}).get('path'))
    images = [Path(capture['path'])]
    artifacts = [trial_path, timeline, play, *images]
    report = {'status': 'play_resume_native_and_visual_readiness_accepted',
              'observed_at': time.time(), 'client_proof': trial['client_proof'],
              'connection': connection, 'play_requested_at': action['requested_at'],
              'gameplay_visible_at': final['server_state']['data']['client_launch']['gameplay_visible_at'],
              'first_same_gameplay_controller_counter_zero_at': ready[0]['counter']['observed_at'],
              'stable_observation_seconds': native['observed_at'] - ready[0]['native']['observed_at'],
              'native_final': native, 'server_final': server, 'stages': c['stages'],
              'visual_review': {'image': str(images[0]), 'character': 'LabExplorer standing on grass',
                                'hud_resources': [100, 100, 100], 'loading_overlay': False},
              'movement_sent': False, 'controls_released': trial['controls_released'],
              'desktop_preservation': {'certified': False, 'play_focus_proof': action['focus_proof'],
                                       'cause_of_cursor_change': 'undetermined'},
              'artifacts': [{'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                            for p in artifacts]}
    return Bridge().record('resume-readiness', report)


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trial', required=True, type=Path)
    p.add_argument('--connection', required=True)
    p.add_argument('--visual-confirmed', action='store_true')
    a = p.parse_args()
    result = review(a.trial, a.connection, a.visual_confirmed)
    print(json.dumps({k: result[k] for k in ('status', 'connection', 'stable_observation_seconds', 'evidence_path')}, indent=2))
