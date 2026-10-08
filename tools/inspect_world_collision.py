"""Read reflected landscape, capsule and gravity metadata; no game calls/writes."""
import argparse
import json
from pathlib import Path

from inspect_movement_prerequisites import MovementProbe
from dump_runtime_reflection import Reader, ReadError
from protocol_proof import EXPECTED_EXE, client_proof


def inspect(pid):
    proof = client_proof(pid)
    reader = Reader(pid, EXPECTED_EXE)
    result = {'client_proof': proof, 'access': 'read-only', 'objects': [], 'errors': [],
              'ground_height_verified': False}
    try:
        probe = MovementProbe(reader)
        for address, obj in probe.reflection.objects():
            ancestors = [n for _, n in probe.chain(obj['class_address'])]
            target = next((n for n in ('LandscapeHeightfieldCollisionComponent',
                'LandscapeComponent', 'LandscapeProxy', 'WorldSettings', 'PlayerCharacter')
                if n in ancestors), None)
            if not target or obj['name'].startswith(('Default__', 'GEN_VARIABLE')):
                continue
            try:
                entry = {'identity': probe.identity(address), 'kind': target}
                names = ['RelativeLocation', 'RelativeRotation', 'RelativeScale3D', 'AttachParent',
                    'SectionBaseX', 'SectionBaseY', 'ComponentSizeQuads', 'SubsectionSizeQuads',
                    'NumSubsections', 'CollisionSizeQuads', 'CollisionScale', 'SimpleCollisionSizeQuads',
                    'CollisionThickness', 'CachedLocalBox', 'HeightmapTexture', 'LandscapeSectionOffset',
                    'LandscapeComponents', 'CollisionComponents', 'RootComponent', 'WorldGravityZ',
                    'bGlobalGravitySet', 'GlobalGravityZ', 'bEnableWorldBoundsChecks', 'KillZ']
                entry['fields'] = probe.fields(address, names)
                entry['transform_chain'] = []
                component = address if 'SceneComponent' in ancestors else None
                if component is None:
                    root = entry['fields']['RootComponent'].get('value')
                    component = int(root['address'], 16) if root else None
                seen = set()
                while component:
                    if component in seen or len(seen) >= 16:
                        raise ReadError('Invalid bounded component attachment chain')
                    seen.add(component)
                    fields = probe.fields(component, ['RelativeLocation', 'RelativeRotation',
                        'RelativeScale3D', 'AttachParent', 'bAbsoluteLocation', 'bAbsoluteRotation',
                        'bAbsoluteScale'])
                    rotation = probe.properties_for(component).get('RelativeRotation')
                    if rotation and rotation['referenced_type'] == 'Rotator' and rotation['element_size'] == 24:
                        fields['RelativeRotation']['value'] = list(reader.unpack(
                            component+rotation['offset_in_object'], '<ddd'))
                    entry['transform_chain'].append({'identity':probe.identity(component), 'fields':fields})
                    parent = fields['AttachParent'].get('value')
                    component = int(parent['address'],16) if parent else None
                entry['reflected_properties'] = {k: v for k, v in probe.properties_for(address).items()
                    if any(term in k.lower() for term in ('height', 'collision', 'bound', 'gravity'))}
                # Preserve opaque structs only with their actual reflected type/size.
                for name in ('CachedLocalBox', 'RelativeRotation', 'LandscapeSectionOffset'):
                    prop = probe.properties_for(address).get(name)
                    if prop and prop['type'] == 'StructProperty' and 0 < prop['element_size'] <= 64:
                        entry['fields'][name]['raw_hex'] = reader.read(
                            address+prop['offset_in_object'], prop['element_size']).hex()
                if target == 'PlayerCharacter':
                    pawn = probe.pawn(address)
                    entry['pawn'] = pawn
                    root = pawn.get('root_component')
                    if root:
                        entry['capsule'] = probe.fields(int(root['address'],16),
                            ['CapsuleRadius', 'CapsuleHalfHeight', 'RelativeScale3D', 'BodyInstance'])
                    prop = probe.properties_for(address).get('CharacterMovement')
                    if prop:
                        movement = probe.decode(address, prop).get('value')
                        if movement:
                            entry['movement'] = probe.fields(int(movement['address'],16),
                                ['GravityScale', 'MovementMode', 'Velocity', 'MaxWalkSpeed',
                                 'MaxAcceleration', 'BrakingDecelerationWalking', 'GroundFriction',
                                 'MaxStepHeight', 'WalkableFloorAngle', 'WalkableFloorZ'])
                result['objects'].append(entry)
            except (ReadError, UnicodeError) as exc:
                result['errors'].append({'address': hex(address), 'name':obj['name'], 'error':str(exc)})
        result['completed_client_proof'] = client_proof(pid)
        result['bytes_read'] = reader.bytes_read
        return result
    finally:
        reader.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid', type=int, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    report = inspect(args.pid)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    from collections import Counter
    print(json.dumps({'counts':dict(Counter(o['kind'] for o in report['objects'])),
                      'errors':report['errors'], 'bytes_read':report['bytes_read']}))
