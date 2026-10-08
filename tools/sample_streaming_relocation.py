"""Read native streaming getter fields and selected cell states during relocation."""
import argparse
import json
from pathlib import Path
import time

from dump_runtime_reflection import Reader, ReadError
from export_static_collision import CollisionProbe
from protocol_proof import EXPECTED_EXE, client_proof


def sample(pid, pawn, controller, cells_path, duration):
    reader = Reader(pid, EXPECTED_EXE)
    try:
        probe = CollisionProbe(reader)
        pawn_identity = probe.p.identity(pawn, 'PlayerPawn_C')
        controller_identity = probe.p.identity(controller, 'PlayerController')
        report = json.loads(cells_path.read_text())
        cells = [row for row in report['matches']['tested_brazier']
                 if not row['hlod'] and (row['grid'] == 'Landscape' or
                    row['grid'] == 'MainGrid' and row['hierarchy'] == 0)]
        if len(cells) != 2:
            raise ReadError('Expected detailed landscape and main-grid test cells')
        for row in cells:
            if probe.p.identity(int(row['streaming']['address'], 16)) != row['streaming']:
                raise ReadError('Streaming identity changed')
        root_field = probe.p.fields(pawn, ['RootComponent'])['RootComponent']
        eye = probe.p.fields(pawn, ['BaseEyeHeight'])['BaseEyeHeight']
        camera_field = probe.p.fields(controller, ['PlayerCameraManager'])['PlayerCameraManager']
        if (root_field['metadata']['offset_in_object'] != 0x248 or
                eye['metadata']['offset_in_object'] != 0x374 or
                camera_field['metadata']['offset_in_object'] != 0x458):
            raise ReadError('Pinned getter fields required')
        root = int(root_field['value']['address'], 16)
        camera = int(camera_field['value']['address'], 16)
        roots = probe.p.fields(root, ['AttachParent'])
        if roots['AttachParent']['value'] is not None:
            raise ReadError('Unattached native root required')
        view_props = probe.p.properties_for(camera)
        targets = {}
        for name, offset in (('ViewTarget', 0x400), ('PendingViewTarget', 0xce0)):
            prop = view_props[name]
            target = probe.struct_fields(prop)['Target']
            if prop['offset_in_object'] != offset or target['offset_in_object'] != 0:
                raise ReadError('Pinned view-target getter layout required')
            targets[name] = (camera+offset, target)
        expected = ((controller, 0xd38, 0x44215a0), (controller, 0x898, 0x4422ac0),
                    (pawn, 0x7d8, 0x4332800), (pawn, 0x8f8, 0x4336dd0))
        for address, slot, rva in expected:
            if reader.unpack(reader.unpack(address, '<Q')[0]+slot, '<Q')[0] != reader.base+rva:
                raise ReadError('Unreviewed native streaming getter override')
        rows = []
        start = time.monotonic()
        print('streaming_sampling_started', flush=True)
        while time.monotonic()-start < duration:
            if (probe.p.identity(pawn, 'PlayerPawn_C') != pawn_identity or
                    probe.p.identity(controller, 'PlayerController') != controller_identity):
                raise ReadError('Possessed actor identity changed')
            native = list(reader.unpack(root+0x250, '<ddd'))
            relative = probe.p.fields(root, ['RelativeLocation'])['RelativeLocation']['value']
            view = {name: probe.field(base, prop) for name, (base, prop) in targets.items()}
            selector = reader.unpack(reader.base+0xd855ec0, '<i')[0]
            follows_pawn = selector == 0 and view['ViewTarget'] and view['ViewTarget']['address'] == hex(pawn) and view['PendingViewTarget'] is None
            states = []
            for cell in cells:
                address = int(cell['streaming']['address'], 16)
                fields = probe.p.fields(address, ['LoadedLevel', 'bShouldBeLoaded', 'bShouldBeVisible'])
                level = fields['LoadedLevel'].get('value')
                states.append({'grid': cell['grid'], 'loaded_level': level,
                    'wanted_loaded': fields['bShouldBeLoaded'].get('value'),
                    'wanted_visible': fields['bShouldBeVisible'].get('value')})
            rows.append({'seconds': time.monotonic()-start, 'world_translation': native,
                'relative_location': relative, 'selector': selector, 'view_targets': view,
                'derived_streaming_location': [native[0], native[1], native[2]+eye['value']] if follows_pawn else None,
                'cells': states})
            time.sleep(.5)
        return {'client_proof': client_proof(pid), 'pawn': pawn_identity,
                'controller': controller_identity, 'selected_cells': cells, 'samples': rows,
                'functions_invoked': False, 'memory_written': False,
                'scope': 'Native getter inputs and reflected cell state; subsystem cached streaming source not read.'}
    finally:
        reader.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--pawn', type=lambda value: int(value, 0), required=True)
    parser.add_argument('--controller', type=lambda value: int(value, 0), required=True)
    parser.add_argument('--cells', type=Path, required=True)
    parser.add_argument('--duration', type=float, default=55)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.duration <= 60:
        parser.error('Bounded 1..60 second sample required')
    result = sample(args.pid, args.pawn, args.controller, args.cells, args.duration)
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps({'samples': len(result['samples']), 'first': result['samples'][0], 'last': result['samples'][-1]}))
