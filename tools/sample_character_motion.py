"""Sample reflected unattached-root position and movement state; read-only."""
import argparse
import json
import time
from pathlib import Path
from dump_runtime_reflection import Reader, ReadError
from inspect_movement_prerequisites import MovementProbe
from protocol_proof import EXPECTED_EXE, client_proof


def sample(pid, pawn, duration):
    reader = Reader(pid, EXPECTED_EXE)
    try:
        probe = MovementProbe(reader)
        identity = probe.identity(pawn, 'Pawn')
        links = probe.fields(pawn, ['RootComponent', 'CharacterMovement'])
        root = int(links['RootComponent']['value']['address'], 16)
        move = int(links['CharacterMovement']['value']['address'], 16)
        root_identity = probe.identity(root, 'SceneComponent')
        move_identity = probe.identity(move, 'CharacterMovementComponent')
        if probe.fields(root, ['AttachParent'])['AttachParent']['value'] is not None:
            raise ReadError('Unattached root required for world coordinates')
        props = {'location': (root, probe.properties_for(root)['RelativeLocation']),
                 'velocity': (move, probe.properties_for(move)['Velocity']),
                 'mode': (move, probe.properties_for(move)['MovementMode'])}
        rows = []
        start = time.monotonic()
        print('sampling_started', flush=True)
        while time.monotonic()-start < duration:
            if probe.identity(pawn, 'Pawn') != identity:
                raise ReadError('Pawn identity changed during motion sample')
            current_links = probe.fields(pawn, ['RootComponent', 'CharacterMovement'])
            if (current_links != links or
                    probe.identity(root, 'SceneComponent') != root_identity or
                    probe.identity(move, 'CharacterMovementComponent') != move_identity):
                raise ReadError('Pawn components changed during motion sample')
            rows.append({'seconds': time.monotonic()-start,
                         **{name: probe.decode(base, prop)['value'] for name,(base,prop) in props.items()}})
            time.sleep(.05)
        return {'pid':pid, 'client_proof':client_proof(pid), 'pawn':identity,
                'samples':rows, 'functions_invoked':False, 'input_sent':False}
    finally:
        reader.close()


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid', type=int, required=True)
    p.add_argument('--pawn', type=lambda v:int(v,0), required=True)
    p.add_argument('--duration', type=float, default=12)
    p.add_argument('--output', type=Path, required=True)
    a=p.parse_args()
    if not 1 <= a.duration <= 60: p.error('Duration must be 1..60 seconds')
    d=sample(a.pid,a.pawn,a.duration)
    a.output.write_text(json.dumps(d,indent=2),encoding='utf-8')
    rows=d['samples'];print(json.dumps({'samples':len(rows),'min_z':min(r['location'][2] for r in rows),
        'max_z':max(r['location'][2] for r in rows),'min_vz':min(r['velocity'][2] for r in rows),
        'max_vz':max(r['velocity'][2] for r in rows),'first':rows[0],'last':rows[-1]}))
