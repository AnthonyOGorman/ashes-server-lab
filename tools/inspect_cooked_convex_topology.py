"""Read native convex connectivity and compare it with native supporting planes."""
import argparse
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dump_runtime_reflection import Reader, ReadError, pointer
from protocol_proof import EXPECTED_EXE, client_proof
from lab.capsule_sweep import dot, sub


def inspect(pid, source):
    snapshot = json.loads(source.read_text())
    proof = client_proof(pid)
    for key in ('pid', 'exe', 'sha256', 'process_created_filetime'):
        if proof[key] != snapshot['client_proof'][key]:
            raise ValueError('same source process required')
    reader = Reader(pid, EXPECTED_EXE)
    result = {'client_proof': proof, 'source': str(source), 'shapes': [],
              'scope': 'read-only connectivity research; no collision activation'}
    try:
        # Native debug traversal reads first/count and half-edge vertex fields.
        for offset, expected in ((0x231, '440fb67c4801'),
                                 (0x29f, '0fb60448'),
                                 (0x2af, '440fb6440101')):
            code = bytes.fromhex(expected)
            if reader.read(reader.base + 0x2107740 + offset, len(code)) != code:
                raise ReadError('exact native face traversal required')
        for shape in snapshot['shapes']:
            row = {'geometry': shape['geometry'], 'mesh': shape['mesh'], 'index': shape['index']}
            result['shapes'].append(row)
            try:
                geometry = int(shape['geometry'], 16)
                element = int(shape['element'], 16)
                if reader.unpack(element + 240, '<Q')[0] != geometry:
                    raise ReadError('source ownership changed')
                if reader.unpack(geometry, '<Q')[0] - reader.base != 0x9fac6e0:
                    raise ReadError('native convex vtable required')
                buffers = []
                for offset, fmt in ((0x30, '<3f'), (0x20, '<6f')):
                    ptr, count, capacity = reader.unpack(geometry + offset, '<Qii')
                    if not pointer(ptr) or not 4 <= count <= capacity <= 4096:
                        raise ReadError('bounded native geometry required')
                    buffers.append([list(v) for v in struct.iter_unpack(fmt, reader.read(ptr, count * struct.calcsize(fmt)))])
                vertices, planes = buffers
                structure = reader.unpack(geometry + 0x58, '<Q')[0]
                kind = reader.unpack(geometry + 0x60, '<b')[0]
                if not pointer(structure) or kind not in (1, 2, 3):
                    raise ReadError('native connectivity type required')
                fmt = {1: '<B', 2: '<h', 3: '<i'}[kind]
                width = struct.calcsize(fmt)
                arrays = []
                headers = reader.read(structure, 64)
                for offset, fields in ((0, 2), (16, 3), (32, 1), (48, 1)):
                    ptr, count, capacity = struct.unpack_from('<Qii', headers, offset)
                    if not pointer(ptr) or not 1 <= count <= capacity <= 65536:
                        raise ReadError('bounded connectivity array required')
                    arrays.append([list(v) for v in struct.iter_unpack('<' + fmt[1:] * fields, reader.read(ptr, count * width * fields))])
                faces, edges, vertex_edges, unique_edges = arrays
                row.update(data_type=kind, vertices=vertices, planes=planes,
                           faces=faces, half_edges=edges, vertex_edges=vertex_edges,
                           unique_edges=unique_edges)
                if len(faces) != len(planes) or len(vertex_edges) != len(vertices):
                    raise ReadError('topology counts differ from geometry')
                polygons = []
                errors = []
                residuals = []
                for face, (first, count) in enumerate(faces):
                    if count < 3 or first < 0 or first + count > len(edges):
                        raise ReadError('invalid face edge interval')
                    polygon = []
                    for edge_index in range(first, first + count):
                        owner, vertex, twin = edges[edge_index]
                        if owner != face or not 0 <= vertex < len(vertices) or not 0 <= twin < len(edges):
                            raise ReadError(f'invalid half-edge reference face={face} edge={edge_index} owner={owner} vertex={vertex} twin={twin} edges={len(edges)} vertices={len(vertices)}')
                        if edges[twin][2] != edge_index:
                            errors.append({'edge': edge_index, 'reason': 'non-reciprocal twin'})
                        polygon.append(vertex)
                    polygons.append(polygon)
                    residuals.append(max(abs(dot(planes[face][3:], sub(vertices[v], planes[face][:3]))) for v in polygon))
                if reader.read(structure, 64) != headers or reader.unpack(element + 240, '<Q')[0] != geometry:
                    raise ReadError('native geometry changed during capture')
                row.update(data_type=kind, vertices=vertices, planes=planes, polygons=polygons,
                           half_edges=edges, vertex_edges=vertex_edges, unique_edges=unique_edges,
                           topology_errors=errors, face_plane_residual_cm=residuals,
                           maximum_face_plane_residual_cm=max(residuals))
            except (ReadError, ValueError) as exc:
                row['error'] = str(exc)
        return result
    finally:
        reader.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.pid, args.source)
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps({'shapes': len(result['shapes']),
                      'read_errors': sum('error' in row for row in result['shapes']),
                      'consistent_shapes': sum(not row.get('topology_errors') and row.get('maximum_face_plane_residual_cm', float('inf')) <= .002 for row in result['shapes'])}))
