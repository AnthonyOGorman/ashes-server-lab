"""One guarded login/Play UI action against a fresh visual checkpoint."""
import argparse
import json
import sys
import threading
import time
from pathlib import Path

from ashes_testing.bridge import Bridge, HOME
from ashes_testing.input import resident_adapter
from ashes_testing.telemetry import NativeTelemetry, Unavailable, WORKSPACE


def referenced_capture(path, proof):
    path = Path(path).resolve()
    if path.parent != (HOME / 'runs').resolve() or not path.name.startswith('capture-') or path.suffix != '.json':
        raise Unavailable('Checkpoint must be a bridge capture record in client-testing/runs')
    capture = json.loads(path.read_text())
    if not NativeTelemetry.same_process(proof, capture.get('client_proof', {})):
        raise Unavailable('Visual checkpoint belongs to another client lifetime')
    if not 0 <= time.time() - capture.get('observed_at', 0) <= 180:
        raise Unavailable('Visual checkpoint must be at most three minutes old')
    png = Path(capture['path']).resolve()
    if png.parent != path.parent or png.suffix != '.png':
        raise Unavailable('Screenshot must be a PNG in client-testing/runs')
    return capture, png


def action(pid, created, evidence, bbox, key=None, x=None, y=None):
    bridge = Bridge(pid, enable_input=True)
    proof = bridge.native.proof()
    if proof['process_created_filetime'] != created:
        raise Unavailable('Requested process lifetime changed')
    bridge.gate.verify(proof, action='ui-entry')
    reference, png = referenced_capture(evidence, proof)
    sys.path.insert(0, str(WORKSPACE))
    from lab.automation import AttachedWindowsDriver, compare_crop
    from PIL import Image
    adapter = resident_adapter(pid)
    status = adapter.status()
    if status['held'] or status['active']:
        raise Unavailable('Adapter already active; concurrent input ownership is uncertain')
    driver = AttachedWindowsDriver(pid, adapter=adapter)
    result = {'status': 'blocked', 'client_proof': proof, 'reference': reference,
              'bbox': bbox, 'action': {'key': key} if key else {'x': x, 'y': y}}
    try:
        current = driver._image()
        with Image.open(png) as image:
            if image.size != current.size:
                raise Unavailable('Client dimensions changed; fresh visual calibration required')
            if (len(bbox) != 4 or any(isinstance(v, bool) or not isinstance(v, int) for v in bbox)
                    or not 0 <= bbox[0] < bbox[2] <= current.width
                    or not 0 <= bbox[1] < bbox[3] <= current.height):
                raise ValueError('Checkpoint rectangle is outside client bounds')
            result['checkpoint'] = compare_crop(current, image.crop(bbox), bbox, 8)
        if not result['checkpoint']['matched']:
            raise Unavailable('Visual checkpoint changed; no UI input sent')
        if key is None and not (bbox[0] <= x < bbox[2] and bbox[1] <= y < bbox[3]):
            raise Unavailable('Click must be inside the verified checkpoint')
        if key is not None and key not in ('enter', 'tab', 'escape', 'up', 'down', 'left', 'right'):
            raise ValueError('Only login/navigation keys are allowed')
        bridge.gate.verify(bridge.native.proof(), action='ui-entry')
        result['requested_at'] = time.time()
        if key:
            driver.key(key, .1, threading.Event())
        else:
            driver.click(x, y)
        result['completed_at'] = time.time()
        result['focus_proof'] = driver.last_input_proof
        result['status'] = 'completed'
    except Exception as exc:
        result['error'] = str(exc)
    finally:
        driver.release_all()
        result['released'] = adapter.status()
        if result['released']['active'] or result['released']['held']:
            result['status'] = 'blocked'
            result['release_error'] = 'Adapter failed to release/deactivate'
        result['observed_at'] = time.time()
        result = bridge.record('ui-action', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--created-filetime', type=int, required=True)
    parser.add_argument('--capture-evidence', required=True)
    parser.add_argument('--bbox', required=True, help='Client-coordinate x1,y1,x2,y2')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--key', choices=('enter', 'tab', 'escape', 'up', 'down', 'left', 'right'))
    group.add_argument('--click', help='Client-coordinate x,y inside checkpoint')
    args = parser.parse_args()
    x, y = (map(int, args.click.split(',')) if args.click else (None, None))
    print(json.dumps(action(args.pid, args.created_filetime, args.capture_evidence,
          list(map(int, args.bbox.split(','))), args.key, x, y), indent=2))
