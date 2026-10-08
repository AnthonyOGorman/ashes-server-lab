"""Read native notification metadata for current accepted scene actors only."""
import argparse
import json
import re
from pathlib import Path

from inspect_character_appearance import AppearanceProbe
from dump_runtime_reflection import Reader, ReadError
from protocol_proof import EXPECTED_EXE, client_proof, validate_current_client_proofs


def inspect(pid, source):
    source = json.loads(Path(source).read_text())
    validate_current_client_proofs(pid, source, source)
    reader = Reader(pid, EXPECTED_EXE)
    try:
        probe = AppearanceProbe(reader)
        result = {'client_proof': client_proof(pid), 'functions_invoked': False, 'actors': []}
        for match in source['network_guid_actor_matches']:
            if match['actor']['class'] not in ('AoCPlayerControllerBP_C', 'PlayerPawn_C'):
                continue
            address = int(match['actor']['address'], 16)
            obj = probe.reflection.obj(address)
            if obj['index'] != match['actor']['object_index']:
                raise ReadError('Accepted actor identity changed')
            functions = []
            for cls, owner in probe.chain(obj['class_address']):
                current = reader.unpack(cls+0x68, '<Q')[0]
                seen = set()
                while current:
                    if current in seen or len(seen) >= 4096:
                        raise ReadError('Invalid bounded class function list')
                    seen.add(current)
                    member = probe.reflection.obj(current)
                    if member['name'] in ('OnRep_PlayerState', 'OnRep_Controller', 'ClientInitializeCharacter') or re.search(r'ClientLoad|CharacterLoad|CharacterInit|InitializeCharacter', member['name']):
                        native = reader.unpack(current+0xf8, '<Q')[0]
                        if not reader.base <= native < reader.base+reader.image_size:
                            raise ReadError('Native function target outside exact image')
                        functions.append({'name': member['name'], 'owner': owner,
                            'function_address': hex(current), 'native_rva': hex(native-reader.base)})
                    current = reader.unpack(current+0x48, '<Q')[0]
            vt = reader.unpack(address, '<Q')[0]
            entry = {'identity': probe.identity(address), 'guid': match['guid'],
                'functions': functions, 'vtable_rva': hex(vt-reader.base)}
            if match['actor']['class'] == 'AoCPlayerControllerBP_C':
                entry['virtual_c10_rva'] = hex(reader.unpack(vt+0xc10, '<Q')[0]-reader.base)
                entry['client_load_virtuals'] = {hex(offset):hex(reader.unpack(vt+offset,'<Q')[0]-reader.base)
                    for offset in (0x21c0,0x21c8,0x21d0)}
                entry['character_load_tracker'] = probe.fields(address, ['CharacterLoadTracker'])
            else:
                entry['virtual_830_rva'] = hex(reader.unpack(vt+0x830, '<Q')[0]-reader.base)
                entry['virtual_870_rva'] = hex(reader.unpack(vt+0x870, '<Q')[0]-reader.base)
            result['actors'].append(entry)
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
    print(json.dumps(result['actors']))
