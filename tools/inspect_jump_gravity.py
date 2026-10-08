"""Read jump/gravity reflection and virtual targets; never calls or writes game code."""
import argparse
import json
import struct
from pathlib import Path
from inspect_movement_prerequisites import MovementProbe
from dump_runtime_reflection import Reader, ReadError
from protocol_proof import EXPECTED_EXE, client_proof
from inspect_movement_serializers import PE


def inspect(pid, pawn):
    proof = client_proof(pid)
    reader = Reader(pid, EXPECTED_EXE)
    try:
        probe = MovementProbe(reader)
        identity = probe.identity(pawn, 'Character')
        owner = probe.fields(pawn, ['Controller', 'CharacterMovement'])
        controller = owner['Controller'].get('value')
        if not controller:
            raise ReadError('Possessed character required')
        possession = probe.controller(int(controller['address'], 16))
        if not possession['acknowledges_same_pawn'] or not possession['pawn_points_back_to_controller']:
            raise ReadError('Mutual acknowledged possession required')
        movement = owner['CharacterMovement']['value']
        address = int(movement['address'], 16)
        props = probe.properties_for(address)
        names = [name for name in props if any(term in name.lower() for term in
                 ('gravity', 'jump', 'fall', 'overridevelocity', 'simulation', 'predict'))]
        functions = []
        for cls, name in probe.chain(probe.reflection.obj(address)['class_address']):
            head = reader.unpack(cls+0x68, '<Q')[0]
            seen = set()
            while head:
                if head in seen or len(seen) >= 2048:
                    raise ReadError('Unbounded function list')
                seen.add(head)
                obj = probe.reflection.obj(head)
                if obj['name'] in ('GetGravityZ', 'GetOverrideVelocity', 'HasOverrideVelocity'):
                    functions.append({'name': obj['name'], 'owner': name,
                        'exec_rva': hex(reader.unpack(head+0xf8, '<Q')[0]-reader.base)})
                head = reader.unpack(head+0x48, '<Q')[0]
        pe = PE(Path(EXPECTED_EXE).read_bytes())
        vt = reader.unpack(address, '<Q')[0]
        targets = []
        for offset in range(0x500, 0xe00, 8):
            target = reader.unpack(vt+offset, '<Q')[0]-reader.base
            targets.append({'offset': hex(offset), 'rva': hex(target), 'boundary': pe.boundary(target)})
        base_owner = probe.fields(address, ['BaseCharacterOwner'])['BaseCharacterOwner'].get('value')
        owner_targets = []
        owner_fields = {}
        if base_owner:
            owner_address = int(base_owner['address'], 16)
            owner_props = probe.properties_for(owner_address)
            owner_names = [n for n in owner_props if any(t in n.lower() for t in ('gravity', 'fall', 'jump'))]
            owner_fields = probe.fields(owner_address, owner_names)
            owner_vt = reader.unpack(owner_address, '<Q')[0]
            for offset in (0xcf0, 0xcf8):
                target = reader.unpack(owner_vt+offset, '<Q')[0]-reader.base
                owner_targets.append({'offset': hex(offset), 'rva': hex(target), 'boundary': pe.boundary(target)})
        root = probe.fields(pawn, ['RootComponent'])['RootComponent']['value']
        root_address = int(root['address'], 16)
        volume_prop = probe.properties_for(root_address).get('PhysicsVolume')
        volume = None
        if volume_prop and volume_prop['type'] == 'WeakObjectProperty' and volume_prop['element_size'] == 8:
            index, serial = reader.unpack(root_address+volume_prop['offset_in_object'], '<ii')
            if 0 <= index < probe.reflection.count and serial > 0:
                chunk = reader.unpack(probe.reflection.chunks+(index//65536)*8, '<Q')[0]
                entry = reader.read(chunk+(index%65536)*24, 24)
                pointer, flags = struct.unpack_from('<QI', entry)
                actual_serial = struct.unpack_from('<i', entry, 16)[0]
                if pointer and serial == actual_serial and not flags & 0x10200000:
                    volume = probe.identity(pointer, 'PhysicsVolume')
        level = int(identity['outer_address'], 16)
        world = probe.fields(level, ['OwningWorld'])['OwningWorld']['value']
        world_fields = probe.fields(int(world['address'], 16), ['DefaultPhysicsVolume', 'PersistentLevel'])
        volume = volume or world_fields['DefaultPhysicsVolume'].get('value')
        volume_target = None
        if volume:
            vt = reader.unpack(int(volume['address'], 16), '<Q')[0]
            target = reader.unpack(vt+0x840, '<Q')[0]-reader.base
            volume_target = {'rva': hex(target), 'boundary': pe.boundary(target)}
        persistent = world_fields['PersistentLevel'].get('value')
        settings = probe.fields(int(persistent['address'], 16), ['WorldSettings'])['WorldSettings'].get('value') if persistent else None
        settings_fields = probe.fields(int(settings['address'], 16), ['WorldGravityZ', 'GlobalGravityZ', 'bGlobalGravitySet']) if settings else {}
        settings_target = None
        if settings:
            settings_vt = reader.unpack(int(settings['address'], 16), '<Q')[0]
            target = reader.unpack(settings_vt+0x840, '<Q')[0]-reader.base
            settings_target = {'rva': hex(target), 'boundary': pe.boundary(target)}
        physics_defaults = []
        for obj_address, obj in probe.reflection.objects():
            if obj['name'] == 'Default__PhysicsSettings':
                physics_defaults.append({'identity': probe.identity(obj_address),
                    'fields': probe.fields(obj_address, ['DefaultGravityZ'])})
        stats = probe.fields(pawn, ['StatsComponent'])['StatsComponent'].get('value')
        stats_fields = {}
        if stats:
            stats_address = int(stats['address'], 16)
            stats_props = probe.properties_for(stats_address)
            stats_fields = probe.fields(stats_address, [n for n in stats_props if 'stat' in n.lower()])
        after = client_proof(pid)
        if any(proof[k] != after[k] for k in ('pid', 'exe', 'sha256', 'process_created_filetime')):
            raise ReadError('Process identity changed')
        return {'client_proof': proof, 'pawn': identity, 'movement': movement,
            'fields': probe.fields(address, names), 'functions': functions,
            'vtable_rva': hex(vt-reader.base), 'virtual_targets': targets,
            'base_owner': base_owner, 'owner_gravity_fields': owner_fields, 'owner_virtual_targets': owner_targets,
            'physics_volume': volume, 'volume_gravity_target': volume_target, 'world': world,
            'world_fields': world_fields, 'world_gravity': settings_fields,
            'persistent_world_settings': settings,
            'world_settings_gravity_target': settings_target,
            'physics_defaults': physics_defaults, 'stats': stats, 'stats_fields': stats_fields,
            'functions_invoked': False, 'completed_client_proof': after}
    finally:
        reader.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--pawn', type=lambda value: int(value, 0), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.pid, args.pawn)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'physics_defaults': result['physics_defaults'], 'stats': result['stats'], 'settings_target': result['world_settings_gravity_target'], 'volume': result['physics_volume'], 'volume_target': result['volume_gravity_target'],
        'world_gravity': {n:r.get('value',r['status']) for n,r in result['world_gravity'].items()},
        'functions': result['functions'], 'owner_targets': result['owner_virtual_targets'], 'owner_fields':
        {name: row.get('value', row['status']) for name, row in result['owner_gravity_fields'].items()}, 'fields':
        {name: row.get('value', row['status']) for name, row in result['fields'].items()}}))
