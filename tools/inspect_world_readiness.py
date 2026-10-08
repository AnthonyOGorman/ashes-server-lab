"""Read-only reflected world streaming, HUD and character readiness snapshot."""
import argparse
import json
from pathlib import Path
import re

from inspect_character_appearance import AppearanceProbe
from dump_runtime_reflection import Reader, ReadError, pointer
from protocol_proof import client_proof, EXPECTED_EXE


def object_array(probe, address, name, bound=4096):
    prop = probe.properties_for(address).get(name)
    if prop is None:
        return {'status': 'not_reflected'}
    if (prop['type'], prop['element_size'], prop['array_dim']) != ('ArrayProperty', 16, 1):
        return {'status': 'unsupported_array_type', 'metadata': prop}
    # Exact SDK Basic.hpp FArrayProperty: InnerProperty at0x78, not padding0x70.
    inner = probe.reader.unpack(int(prop['address'], 16)+0x78, '<Q')[0]
    members = probe.reflection.properties(inner)
    if not members or (members[0]['type'], members[0]['element_size']) != ('ObjectProperty', 8):
        return {'status': 'unsupported_array_inner', 'metadata': prop}
    data, count, capacity = probe.reader.unpack(address+prop['offset_in_object'], '<Qii')
    if not 0 <= count <= capacity <= bound or (count and not pointer(data)):
        raise ReadError('Object array exceeds validated bounds')
    return {'status': 'read', 'count': count, 'capacity': capacity,
            'objects': [probe.identity(probe.reader.unpack(data+i*8, '<Q')[0],
                members[0].get('referenced_type')) for i in range(count)]}


def inspect(pid, controller, pawn):
    proof = client_proof(pid)
    reader = Reader(pid, EXPECTED_EXE, budget=64*1024*1024)
    try:
        probe = AppearanceProbe(reader)
        pc = probe.controller(controller)
        if not pc['acknowledges_same_pawn'] or not pc['pawn_points_back_to_controller'] or int(pc['pawn']['address'], 16) != pawn:
            raise ReadError('Current mutually possessed pawn required')
        level = probe.identity(int(pc['outer_address'], 16), 'Level')
        world = probe.fields(int(level['address'], 16), ['OwningWorld'])['OwningWorld']['value']
        if not world or world['name'] != 'Verra_World_Master':
            raise ReadError('Expected live Verra world')
        world_address = int(world['address'], 16)
        result = {'pid': pid, 'client_proof': proof, 'functions_invoked': False,
            'possession': pc, 'world': {'identity': world, 'fields': probe.fields(world_address,
                ['PersistentLevel', 'WorldPartition', 'GameState', 'Levels', 'StreamingLevels',
                 'StreamingLevelsToConsider', 'bAreConstraintsDirty', 'bIsLevelStreamingFrozen',
                 'bIsWorldInitialized', 'bActorsInitialized', 'bBegunPlay'])}, 'streaming_levels': []}
        streamed = object_array(probe, world_address, 'StreamingLevels')
        result['world']['streaming_array'] = streamed
        for identity in streamed.get('objects', []):
            if identity is None:
                continue
            address = int(identity['address'], 16)
            props = probe.properties_for(address)
            names = [name for name in props if re.search(r'loaded|visible|load|block|pending|package|state|level|distance', name, re.I)][:48]
            entry = {'identity': identity, 'fields': probe.fields(address, names)}
            loaded = entry['fields'].get('LoadedLevel', {}).get('value')
            if loaded:
                entry['loaded_level_fields'] = probe.fields(int(loaded['address'], 16), ['bIsVisible'])
            result['streaming_levels'].append(entry)
        result['controller_streaming'] = probe.fields(controller, [name for name in probe.properties_for(controller)
            if re.search(r'stream|camera|viewtarget|ready|init', name, re.I)][:96])
        camera = result['controller_streaming'].get('PlayerCameraManager', {}).get('value')
        if camera:
            address = int(camera['address'], 16)
            names = [name for name in probe.properties_for(address)
                if re.search(r'cache|viewtarget|transform|camera|rootcomponent|owner|location', name, re.I)][:96]
            result['camera'] = {'identity': camera, 'fields': probe.fields(address, names)}
        persistent = result['world']['fields'].get('PersistentLevel', {}).get('value')
        settings = None
        if persistent:
            settings = probe.fields(int(persistent['address'], 16), ['WorldSettings'])['WorldSettings'].get('value')
        if settings:
            address = int(settings['address'], 16)
            names = [name for name in probe.properties_for(address)
                if re.search(r'partition|stream|runtime|world|enable|hlod', name, re.I)][:96]
            result['world_settings'] = {'identity': settings, 'fields': probe.fields(address, names)}
        partition = result['world']['fields'].get('WorldPartition', {}).get('value')
        if not partition and settings:
            partition = result['world_settings']['fields'].get('WorldPartition', {}).get('value')
        if partition:
            address = int(partition['address'], 16)
            names = [name for name in probe.properties_for(address) if re.search(r'stream|init|runtime|cell|source|world|enable', name, re.I)][:64]
            result['world_partition'] = {'identity': partition, 'fields': probe.fields(address, names)}
            for name in ('RuntimeHash', 'StreamingPolicy'):
                child = result['world_partition']['fields'].get(name, {}).get('value')
                if isinstance(child, dict) and child.get('address'):
                    address = int(child['address'], 16)
                    names = [key for key in probe.properties_for(address)
                        if re.search(r'stream|init|runtime|cell|source|world|enable|hlod|grid', key, re.I)][:96]
                    result['world_partition'][name] = {'identity': child, 'fields': probe.fields(address, names)}
        hud = pc.get('hud')
        if hud:
            address = int(hud['address'], 16)
            names = [name for name in probe.properties_for(address) if re.search(r'widget|ready|init|player|pawn|state|hidden|draw|owner|load', name, re.I)][:96]
            result['hud'] = {'identity': hud, 'fields': probe.fields(address, names)}
        gs = result['world']['fields']['GameState'].get('value')
        if gs:
            result['game_state'] = {'identity': gs, 'fields': probe.fields(int(gs['address'], 16),
                ['bReplicatedHasBegunPlay', 'GameModeClass', 'PlayerArray', 'ReplicatedWorldTimeSecondsDouble'])}
        result['summary'] = {'streaming_objects': len(result['streaming_levels']),
            'streaming_array_status': streamed['status'],
            'loaded_level_references': sum(bool(entry['fields'].get('LoadedLevel', {}).get('value')) for entry in result['streaming_levels']),
            'loaded_levels_visible': sum(entry.get('loaded_level_fields', {}).get('bIsVisible', {}).get('value') is True for entry in result['streaming_levels']),
            'hud_instance_present': hud is not None,
            'controller_player_state_present': pc.get('player_state') is not None,
            'movement_proved': False}
        after = client_proof(pid)
        if any(proof[key] != after[key] for key in ('pid', 'sha256', 'process_created_filetime', 'exe')):
            raise ReadError('Client identity changed during readiness snapshot')
        result.update(completed_client_proof=after, bytes_read=reader.bytes_read)
        return result
    finally:
        reader.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--controller', type=lambda x: int(x, 0), required=True)
    parser.add_argument('--pawn', type=lambda x: int(x, 0), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = inspect(args.pid, args.controller, args.pawn)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report['summary']))
