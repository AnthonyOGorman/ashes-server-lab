"""Resolve native partition cells and audit content bounds at test locations."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import struct

from dump_runtime_reflection import Reader, ReadError, pointer
from export_static_collision import CollisionProbe
from protocol_proof import EXPECTED_EXE, client_proof


def inspect(pid, pawn, source):
    report = json.loads(source.read_text())
    proof = client_proof(pid)
    for key in ('pid', 'exe', 'sha256', 'process_created_filetime'):
        if proof[key] != report['client_proof'][key]:
            raise ReadError('Exact source process identity required')
    reader = Reader(pid, EXPECTED_EXE, budget=256*1024*1024)
    try:
        probe = CollisionProbe(reader)
        identity = probe.p.identity(pawn, 'PlayerPawn_C')
        world = probe.world(pawn)
        root = probe.p.fields(pawn, ['RootComponent'])['RootComponent']['value']
        position = probe.p.fields(int(root['address'], 16), ['RelativeLocation'])['RelativeLocation']['value']
        points = {'pawn': position, 'tested_brazier': [-1229974.426361084, -341128.5583343506, 25718.778021274524]}
        counts = Counter()
        matches = {name: [] for name in points}
        errors = []
        for row in report['levels']:
            address = int(row['identity']['address'], 16)
            try:
                if probe.p.identity(address) != row['identity'] or probe.world(address) != world:
                    raise ReadError('Current-world streaming identity changed')
                prop = probe.p.properties_for(address)['StreamingCell']
                if (prop['type'], prop['element_size']) != ('WeakObjectProperty', 8):
                    raise ReadError('Reflected cell weak reference required')
                index, serial = reader.unpack(address+prop['offset_in_object'], '<ii')
                if not 0 <= index < probe.p.reflection.count or serial <= 0:
                    raise ReadError('Bounded live weak reference required')
                chunk = reader.unpack(probe.p.reflection.chunks+index//65536*8, '<Q')[0]
                if not pointer(chunk):
                    raise ReadError('Object chunk required')
                entry = reader.read(chunk+index%65536*24, 24)
                cell, flags = struct.unpack_from('<QI', entry)
                if not pointer(cell) or serial != struct.unpack_from('<i', entry, 16)[0] or flags & 0x10200000:
                    raise ReadError('Cell weak serial/liveness mismatch')
                cell_identity = probe.p.identity(cell, 'WorldPartitionRuntimeCell')
                if cell_identity['object_index'] != index:
                    raise ReadError('Cell object index mismatch')
                fields = probe.p.fields(cell, ['LevelStreaming', 'bIsHLOD', 'bIsSpatiallyLoaded', 'RuntimeCellData'])
                if fields['LevelStreaming']['value']['address'] != row['identity']['address']:
                    raise ReadError('Reciprocal cell streaming link required')
                data = int(fields['RuntimeCellData']['value']['address'], 16)
                metadata = probe.p.fields(data, ['GridName', 'HierarchicalLevel'])
                bounds_prop = probe.p.properties_for(data)['ContentBounds']
                if bounds_prop['referenced_type'] != 'Box':
                    raise ReadError('Reflected Box content bounds required')
                bounds = {name: probe.field(data+bounds_prop['offset_in_object'], prop)
                          for name, prop in probe.struct_fields(bounds_prop).items()}
                if not bounds['IsValid'] or any(not math.isfinite(v) for v in (*bounds['Min'], *bounds['Max'])):
                    raise ReadError('Valid finite native content bounds required')
                loaded = bool(probe.p.fields(address, ['LoadedLevel'])['LoadedLevel'].get('value'))
                hlod = fields['bIsHLOD']['value']
                grid = metadata['GridName']['value']
                hierarchy = metadata['HierarchicalLevel']['value']
                counts[f'{"loaded" if loaded else "unloaded"}:hlod={hlod}:grid={grid}:hierarchy={hierarchy}'] += 1
                for name, point in points.items():
                    if all(bounds['Min'][i] <= point[i] <= bounds['Max'][i] for i in (0, 1)):
                        matches[name].append({'cell': cell_identity, 'streaming': row['identity'],
                            'loaded': loaded, 'hlod': hlod, 'grid': grid, 'hierarchy': hierarchy,
                            'spatially_loaded': fields['bIsSpatiallyLoaded']['value'], 'content_bounds': bounds})
            except (ReadError, KeyError, TypeError) as exc:
                if len(errors) < 32:
                    errors.append({'streaming': row['identity'], 'reason': str(exc)})
                counts['errors'] += 1
        if probe.p.identity(pawn, 'PlayerPawn_C') != identity:
            raise ReadError('Pawn changed during audit')
        return {'client_proof': proof, 'pawn': identity, 'counts': dict(counts), 'points': points,
                'matches': matches, 'errors': errors, 'functions_invoked': False, 'memory_written': False,
                'scope': 'Native content-bound XY overlap and loaded links; streaming source range, cell bounds and collision-bearing actor contents are not inferred.'}
    finally:
        reader.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--pawn', type=lambda value: int(value, 0), required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.pid, args.pawn, args.source)
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps({'counts': result['counts'], 'matches': {name: Counter(f"loaded={row['loaded']}:hlod={row['hlod']}:grid={row['grid']}:hierarchy={row['hierarchy']}" for row in rows) for name, rows in result['matches'].items()}, 'errors': result['errors'][:2]}))
