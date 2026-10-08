"""Read-only exact receiver and serializer proof for Controller.PlayerState."""
import argparse
import json
from pathlib import Path

from inspect_character_appearance import AppearanceProbe
from dump_runtime_reflection import Reader, ReadError
from protocol_proof import EXPECTED_EXE, client_proof, validate_current_client_proofs


def inspect(pid, actors_path):
    actors = json.loads(Path(actors_path).read_text())
    validate_current_client_proofs(pid, actors, actors)
    matches = actors['network_guid_actor_matches']
    pc = next(m for m in matches if m['actor']['class'] == 'AoCPlayerControllerBP_C')
    ps = next(m for m in matches if m['actor']['class'] == 'AoCPlayerStateBP_C')
    reader = Reader(pid, EXPECTED_EXE, budget=96*1024*1024)
    try:
        probe = AppearanceProbe(reader)
        addresses = [int(m['actor']['address'], 16) for m in (pc, ps)]
        for address, match in zip(addresses, (pc, ps)):
            if probe.identity(address)['object_index'] != match['actor']['object_index']:
                raise ReadError('Accepted actor index changed')
        pc_vt, ps_vt = [reader.unpack(address, '<Q')[0] for address in addresses]
        prop = probe.properties_for(addresses[0])['PlayerState']
        prop_vt = reader.unpack(int(prop['address'], 16), '<Q')[0]
        result = {'pid': pid, 'client_proof': client_proof(pid), 'functions_invoked': False,
            'actor_address': pc['actor']['address'], 'player_state_address': ps['actor']['address'],
            'controller_guid': pc['guid'], 'player_state_guid': ps['guid'], 'property': prop,
            'controller_notify_rva': hex(reader.unpack(pc_vt+0x888, '<Q')[0]-reader.base),
            'player_state_initialize_rva': hex(reader.unpack(ps_vt+0x840, '<Q')[0]-reader.base),
            'player_state_set_owner_rva': hex(reader.unpack(ps_vt+0x5e0, '<Q')[0]-reader.base),
            'controller_notify_bytes': reader.read(reader.base+0x3eebc80, 26).hex(),
            'player_state_initialize_bytes': reader.read(reader.base+0x44119c0, 10).hex(),
            'net_serialize_virtual_offset': '0xc8',
            'net_serialize_rva': hex(reader.unpack(prop_vt+0xc8, '<Q')[0]-reader.base),
            'internal_load_object_rva': '0x42740f0', 'guid_reader_rva': '0x141e960'}
        maps = []
        for address, obj in probe.reflection.objects():
            if obj['name'] != 'Default__PackageMapClient':
                continue
            vt = reader.unpack(address, '<Q')[0]
            maps.append({'identity': probe.identity(address), 'serialize_object_virtual_offset': '0x340',
                'serialize_object_rva': hex(reader.unpack(vt+0x340, '<Q')[0]-reader.base)})
        if len(maps) != 1:
            raise ReadError('One actual PackageMapClient CDO required')
        result.update({k: maps[0][k] for k in ('serialize_object_virtual_offset', 'serialize_object_rva')})
        result['package_map'] = maps[0]['identity']
        result['completed_client_proof'] = client_proof(pid)
        return result
    finally:
        reader.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--actors', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.pid, args.actors)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k.endswith('_rva')}))
