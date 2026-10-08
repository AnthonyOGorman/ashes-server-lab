"""Add proof-bound native terrain without resetting active locomotion state."""
import hashlib
import json
from pathlib import Path
import time

from .terrain import Heightfield

ROOT = Path(__file__).resolve().parents[1]
REQUEST = ROOT/'data/terrain-cache-extension.json'


def slot(tile):
    return (tile.rows, tile.cols, tuple(tile.origin), tuple(tile.scale))


def content(tile):
    return (tile.minimum, tile.quantization, tile.heights, tile.materials)


def extend_tiles(state, tiles):
    """Only additions are allowed; conflicting native samples need explicit handling."""
    merged = list(state.tiles)
    existing = {slot(tile): content(tile) for tile in merged}
    for tile in tiles:
        key = slot(tile)
        if key in existing:
            if existing[key] != content(tile):
                raise ValueError('conflicting cached native terrain samples')
            continue
        existing[key] = content(tile)
        merged.append(tile)
    if len(merged) > 4096:
        raise ValueError('bounded terrain cache required')
    added = len(merged)-len(state.tiles)
    state.tiles = merged
    return added


def apply_request(connection, state, event):
    if not REQUEST.exists():
        return False
    request = json.loads(REQUEST.read_text())
    expected = {'id', 'profile_id', 'connection_id', 'pawn_guid', 'base_terrain_sha256',
                'manifest', 'manifest_sha256', 'expires_at'}
    if set(request) != expected:
        raise ValueError('exact terrain extension schema required')
    if (request['profile_id'] != getattr(connection, 'terrain_experiment_id', None) or
            request['connection_id'] != connection.connection_id or
            request['pawn_guid'] != connection.actor_guids.get('pawn') or
            connection.phase != 'joined' or not connection.possession_acknowledged):
        return False
    if request['id'] == getattr(connection, 'terrain_extension_id', None):
        return False
    if not isinstance(request['id'], str) or not request['id']:
        raise ValueError('terrain extension identity required')
    connection.terrain_extension_id = request['id']
    if not 0 < request['expires_at']-time.time() <= 120:
        raise ValueError('fresh terrain extension required')
    if request['base_terrain_sha256'] != connection.terrain_manifest_hash:
        raise ValueError('current terrain cache generation required')
    path = (ROOT/request['manifest']).resolve()
    if not path.is_relative_to((ROOT/'evidence').resolve()) or path.name != 'manifest.json':
        raise ValueError('local native terrain manifest required')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != request['manifest_sha256']:
        raise ValueError('extension manifest hash mismatch')
    report = json.loads(raw)
    config = connection.terrain_experiment_config
    from tools.protocol_proof import client_proof
    live = client_proof(config['pid'])
    proof = report.get('client_proof', {})
    if report.get('pid') != config['pid'] or any(proof.get(key) != live[key] for key in
            ('pid', 'exe', 'sha256', 'process_created_filetime')):
        raise ValueError('current native terrain process identity required')
    observed = proof.get('observed_at')
    if type(observed) not in (int, float) or not 0 <= time.time()-observed <= 180:
        raise ValueError('fresh native terrain observation required')
    geometry_raw = (ROOT/config['static_collision_snapshot']).read_bytes()
    if hashlib.sha256(geometry_raw).hexdigest() != config['static_collision_sha256']:
        raise ValueError('accepted pawn-world geometry hash required')
    geometry = json.loads(geometry_raw)
    if report.get('world') != geometry['world']:
        raise ValueError('current pawn world required for terrain extension')
    if not 0 < len(report['tiles']) <= 4096:
        raise ValueError('bounded nonempty native terrain extension required')
    tiles = []
    for metadata in report['tiles']:
        buffers = []
        for key in ('heights', 'materials'):
            target = (path.parent/metadata[key]).resolve()
            if target.parent != path.parent:
                raise ValueError('terrain buffers must be sibling files')
            buf = target.read_bytes()
            if hashlib.sha256(buf).hexdigest() != metadata[key+'_sha256']:
                raise ValueError('extension terrain buffer hash mismatch')
            buffers.append(buf)
        tiles.append(Heightfield(metadata['rows'], metadata['cols'], metadata['origin'],
            metadata['scale'], metadata['minimum'], metadata['quantization'], *buffers))
    added = extend_tiles(state, tiles)
    connection.terrain_manifest_hash = request['manifest_sha256']
    event('terrain_cache_extended', {'id': request['id'], 'connection_id': connection.connection_id,
        'profile_id': connection.terrain_experiment_id, 'added_tiles': added,
        'total_tiles': len(state.tiles), 'source_manifest': request['manifest'],
        'terrain_sha256': connection.terrain_manifest_hash,
        'physics_position': state.position.copy(), 'physics_velocity': state.velocity.copy(),
        'physics_timestamp': state.timestamp, 'physics_time_budget': state.time_budget})
    return bool(added)
