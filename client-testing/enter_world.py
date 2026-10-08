"""Replay the verified local login/Play UI at its calibrated client size."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from ashes_testing.bridge import Bridge, HOME
from ashes_testing.telemetry import Unavailable, WORKSPACE
from ui_action import action


def load_calibration(name='ui-calibration.json'):
    if name not in ('ui-calibration.json', 'ui-calibration-1280.json'):
        raise Unavailable('Only reviewed UI calibration profiles are allowed')
    value = json.loads((HOME / name).read_text())
    from PIL import Image
    for step in value['steps']:
        path = (HOME / 'runs' / step['source_png']).resolve()
        if path.parent != (HOME / 'runs').resolve() or path.suffix != '.png':
            raise Unavailable('Calibration image must remain in client-testing/runs')
        if hashlib.sha256(path.read_bytes()).hexdigest() != step['sha256']:
            raise Unavailable('Reviewed calibration pixels changed')
        with Image.open(path) as image:
            if list(image.size) != value['client_size']:
                raise Unavailable('Calibration dimensions changed')
            step['template'] = image.crop(step['bbox']).convert('RGB')
    return value


def enter(pid, created, calibration_name='ui-calibration.json', start_at=0):
    bridge = Bridge(pid, enable_input=True)
    proof = bridge.native.proof()
    if proof['process_created_filetime'] != created:
        raise Unavailable('Requested process lifetime changed')
    bridge.gate.verify(proof, action='ui-entry')
    calibration = load_calibration(calibration_name)
    if not isinstance(start_at, int) or not 0 <= start_at < len(calibration['steps']):
        raise ValueError('Start index is outside reviewed UI stages')
    sys.path.insert(0, str(WORKSPACE))
    from lab.automation import BackgroundWindowsDriver, CaptureNotReady, compare_crop
    from PIL import Image
    driver = BackgroundWindowsDriver(pid)
    result = {'status': 'blocked', 'client_proof': proof, 'steps': [], 'started_at': time.time(),
              'scope': 'Existing reviewed DLL local UI entry; no movement or server mutation'}
    try:
        for step in calibration['steps'][start_at:]:
            deadline = time.monotonic() + 90
            while True:
                bridge.gate.verify(bridge.native.proof(), action='ui-entry')
                if time.monotonic() >= deadline:
                    raise Unavailable('Expected UI checkpoint not observed: ' + step['name'])
                try:
                    capture = bridge.capture_screen()
                except CaptureNotReady:
                    time.sleep(2)
                    continue
                with Image.open(capture['path']) as image:
                    if list(image.size) != calibration['client_size']:
                        raise Unavailable('Client size changed; fresh UI calibration required')
                    matched = compare_crop(image, step['template'], step['bbox'], 8)
                if not matched['matched']:
                    time.sleep(2)
                    continue
                command = step['action']
                r = action(pid, created, capture['evidence_path'], step['bbox'],
                           command.get('key'), command.get('x'), command.get('y'))
                result['steps'].append({'name': step['name'], 'checkpoint': matched,
                                        'action_evidence': r['evidence_path'], 'status': r['status']})
                print(json.dumps(result['steps'][-1]), flush=True)
                if r['status'] != 'completed':
                    if 'requested_at' in r:
                        raise Unavailable('UI action failed after input; replay stopped')
                    time.sleep(1)
                    continue
                break
        result['status'] = 'ui_entry_dispatched'
        result['next_required_check'] = 'Native world possession and server initialization/grounded gates'
    except Exception as exc:
        result['error'] = str(exc)
    finally:
        # Movement is never sent by this runner; each UI action owns key cleanup.
        driver.release_all()
        result['finished_at'] = time.time()
        result = bridge.record('entry', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--created-filetime', type=int, required=True)
    parser.add_argument('--calibration', choices=('ui-calibration.json', 'ui-calibration-1280.json'), default='ui-calibration.json')
    parser.add_argument('--start-at', type=int, default=0, help='Resume at an already observed, reviewed stage index')
    args = parser.parse_args()
    print(json.dumps(enter(args.pid, args.created_filetime, args.calibration, args.start_at), indent=2))
