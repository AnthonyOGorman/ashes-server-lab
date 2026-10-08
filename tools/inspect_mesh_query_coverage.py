"""Inventory current-world mesh query exclusions without changing game state."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path

from dump_runtime_reflection import Reader, ReadError
from export_static_collision import CollisionProbe, transform_values
from protocol_proof import EXPECTED_EXE, client_proof
from inspect_world_readiness import object_array


def inspect(pid, pawn):
    reader = Reader(pid, EXPECTED_EXE, budget=256*1024*1024)
    try:
        probe = CollisionProbe(reader)
        identity = probe.p.identity(pawn, 'PlayerPawn_C')
        world = probe.world(pawn)
        root = probe.p.fields(pawn, ['RootComponent'])['RootComponent']['value']
        centre = probe.p.fields(int(root['address'], 16), ['RelativeLocation'])['RelativeLocation']['value']
        counts = Counter()
        owner_classes = Counter()
        level_membership = Counter()
        representatives = {}
        loaded_levels = object_array(probe.p, world, 'Levels', 20000)
        if loaded_levels['status'] != 'read':
            raise ReadError('Current world level array required')
        loaded = {row['address'] for row in loaded_levels['objects'] if row}
        nearest = []
        errors = []
        for address, obj in probe.p.reflection.objects():
            ancestors = [name for _, name in probe.p.chain(obj['class_address'])]
            if ('StaticMeshComponent' not in ancestors or
                    obj['name'].startswith(('Default__', 'GEN_VARIABLE')) or
                    probe.world(address) != world):
                continue
            counts['current_world_mesh_components'] += 1
            try:
                response = probe.response(address)
                enabled = response['collision_enabled']
                reason = ('owner_collision_disabled' if not response['owner_collision_enabled'] else
                          'component_query_disabled' if enabled not in (1, 3, 5) else
                          'pawn_channel_nonblocking' if response['pawn_response'] != 2 else 'blocking')
                counts[reason] += 1
                counts[f"component_enabled_{response['component_collision_enabled']}"] += 1
                counts[f"pawn_response_{response['pawn_response']}"] += 1
                owner = response['owner']
                owner_class = owner['class'] if owner else 'NoOwner'
                owner_classes[f'{reason}:{owner_class}'] += 1
                level = probe.p.identity(int(owner['outer_address'], 16)) if owner else None
                membership = 'loaded_level' if level and level['address'] in loaded else 'other_outer'
                level_membership[f'{reason}:{membership}'] += 1
                key = f'{reason}:{owner_class}'
                if key not in representatives and len(representatives) < 64:
                    mesh = probe.p.fields(address, ['StaticMesh'])['StaticMesh'].get('value')
                    representatives[key] = {'component': probe.p.identity(address), 'owner': owner,
                        'level': level, 'level_membership': membership, 'mesh': mesh,
                        'owner_fields': probe.p.fields(int(owner['address'], 16),
                            ['bActorEnableCollision', 'bActorInitialized', 'bActorHasBegunPlay',
                             'bHidden', 'DataLayerAssets']) if owner else {},
                        'component_fields': probe.p.fields(address,
                            ['bHiddenInGame', 'bVisible', 'bAutoActivate', 'bIsActive'])}
                props = probe.p.properties_for(address)
                if not probe.field(address, props['bComponentToWorldUpdated']):
                    counts['transform_not_updated'] += 1
                    continue
                position = transform_values(reader.read(address+0x230, 96))['translation']
                distance = math.dist(position[:2], centre[:2])
                if len(nearest) < 24 or distance < nearest[-1]['distance_cm']:
                    mesh = probe.p.fields(address, ['StaticMesh'])['StaticMesh'].get('value')
                    nearest.append({'component': probe.p.identity(address), 'mesh': mesh,
                        'position': position, 'distance_cm': distance, 'reason': reason,
                        'component_collision_enabled': response['component_collision_enabled'],
                        'pawn_response': response['pawn_response'],
                        'owner_collision_enabled': response['owner_collision_enabled']})
                    nearest.sort(key=lambda row: row['distance_cm'])
                    del nearest[24:]
            except (ReadError, KeyError) as exc:
                counts['read_errors'] += 1
                if len(errors) < 24:
                    errors.append({'component': hex(address), 'reason': str(exc)})
        if probe.p.identity(pawn, 'PlayerPawn_C') != identity:
            raise ReadError('Pawn changed during coverage inspection')
        return {'client_proof': client_proof(pid), 'pawn': identity, 'world': probe.p.identity(world),
                'centre': centre, 'counts': dict(counts), 'nearest': nearest, 'errors': errors,
                'owner_classes': dict(owner_classes), 'level_membership': dict(level_membership),
                'representatives': representatives, 'loaded_level_count': len(loaded),
                'functions_invoked': False, 'memory_written': False,
                'scope': 'Current-world resident components and native query flags; visibility and scene registration are not inferred.'}
    finally:
        reader.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--pawn', type=lambda value: int(value, 0), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.pid, args.pawn)
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps({'counts': result['counts'], 'errors': result['errors'][:3],
                      'owner_classes': result['owner_classes'], 'level_membership': result['level_membership'],
                      'nearest': [{k: row[k] for k in ('mesh', 'reason', 'distance_cm')} for row in result['nearest'][:5]]}))
