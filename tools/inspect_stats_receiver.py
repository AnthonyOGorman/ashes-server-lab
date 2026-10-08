"""Read the existing pawn stats component and reviewed receive path; no calls."""
import argparse
import json
from pathlib import Path
from dump_runtime_reflection import Reader, ReadError
from inspect_movement_prerequisites import MovementProbe
from inspect_movement_serializers import PE
from protocol_proof import EXPECTED_EXE, client_proof, validate_current_client_proofs


def inspect(pid, actors_path):
    actors = json.loads(Path(actors_path).read_text())
    validate_current_client_proofs(pid, actors, actors)
    pawns = [m for m in actors['network_guid_actor_matches'] if m['actor']['class'] == 'PlayerPawn_C']
    if actors['errors'] or len(pawns) != 1:
        raise ReadError('One clean accepted gameplay pawn required')
    reader = Reader(pid, EXPECTED_EXE)
    try:
        probe = MovementProbe(reader)
        pawn = int(pawns[0]['actor']['address'], 16)
        component = probe.fields(pawn, ['StatsComponent'])['StatsComponent']['value']
        address = int(component['address'], 16)
        vt = reader.unpack(address, '<Q')[0]
        targets = {}
        for offset in (0x2a8, 0x2b0):
            target = reader.unpack(vt + offset, '<Q')[0]
            if not reader.base <= target < reader.base + reader.image_size:
                raise ReadError('Receive target outside image')
            targets[hex(offset)] = {'rva': hex(target-reader.base), 'bytes': reader.read(target, 24).hex()}
        pe = PE(Path(EXPECTED_EXE).read_bytes())
        start, end = 0x6132120, 0x6132151
        raw = pe.data[pe.offset(start):pe.offset(start)+end-start]
        if reader.read(reader.base + start, end-start) != raw:
            raise ReadError('Native PostNetReceive bytes differ')
        # Reviewed PostNetReceive tail processes these two pending TArrays.
        counts = []
        for offset in (0x1198, 0x11a8):
            _, count, capacity = reader.unpack(address+offset, '<Qii')
            if not 0 <= count <= capacity <= 4096:
                raise ReadError('Pending stat queue bounds invalid')
            counts.append(count)
        return {'pid': pid, 'client_proof': client_proof(pid), 'component': component,
                'fields': probe.fields(address, ['bReplicates']), 'virtual_targets': targets,
                'native_receive_bytes_match': True, 'pending_integer_count': counts[0],
                'pending_float_count': counts[1], 'functions_invoked': False}
    finally:
        reader.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--actors', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = inspect(args.pid, args.actors)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
