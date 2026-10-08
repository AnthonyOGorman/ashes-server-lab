"""Reconstruct native vertex support hulls for offline collision comparison.

RVA20f7820, reached from rounded raycast RVA21048c0+18e, selects the
maximum dot product over the float vertices at +30, count +38. This
representation is separate from the native zero-thickness plane raycast.
No live profile is activated by this tool.
"""
import argparse
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.static_collision import validate_support_surface


def support_surface(vertices):
    from scipy.spatial import ConvexHull, QhullError
    if not 4 <= len(vertices) <= 4096:
        raise ValueError('bounded native support vertices required')
    if any(len(v) != 3 or not all(math.isfinite(x) for x in v) for v in vertices):
        raise ValueError('finite native support vertices required')
    try:
        hull = ConvexHull(vertices)
    except QhullError as exc:
        raise ValueError('nondegenerate native support hull required') from exc
    indices = [int(i) for face in hull.simplices for i in face]
    validate_support_surface(vertices, indices)
    return indices


def reconstruct(source):
    snapshot = json.loads(source.read_text())
    output = {'source': str(source), 'client_proof': snapshot['client_proof'],
              'scope': 'offline native vertex support reconstruction; not activated',
              'native_support_function_rva': '0x20f7820', 'shapes': []}
    for shape in snapshot['shapes']:
        row = {k: shape[k] for k in ('mesh', 'index', 'geometry', 'vertices')}
        try:
            row['indices'] = support_surface(shape['vertices'])
            row['support_hull_verified'] = True
        except ValueError as exc:
            row.update(support_hull_verified=False, error=str(exc))
        output['shapes'].append(row)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = reconstruct(args.source)
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps({'shapes': len(result['shapes']), 'verified': sum(x['support_hull_verified'] for x in result['shapes'])}))
