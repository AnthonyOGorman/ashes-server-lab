"""Verify weak-object GUID acceptance and the current empty gravity rep array."""
import argparse
import json
import struct
from pathlib import Path
from dump_runtime_reflection import Reader, ReadError
from inspect_movement_prerequisites import MovementProbe
from protocol_proof import EXPECTED_EXE, client_proof, validate_current_client_proofs
from inspect_character_stats import hash_entry


def inspect(pid, actor_path, receiver_path):
    actors, receiver = [json.loads(Path(p).read_text()) for p in (actor_path, receiver_path)]
    validate_current_client_proofs(pid, actors, receiver)
    reader = Reader(pid, EXPECTED_EXE)
    try:
        probe = MovementProbe(reader)
        identity = receiver['component']
        address = int(identity['address'], 16)
        if probe.identity(address) != identity:
            raise ReadError('StatsComponent identity changed')
        index = identity['object_index']
        chunk = reader.unpack(probe.reflection.chunks+index//65536*8, '<Q')[0]
        slot = reader.read(chunk+index%65536*24, 24)
        ptr, flags = struct.unpack_from('<QI', slot)
        serial = struct.unpack_from('<i', slot, 16)[0]
        if ptr != address or serial <= 0 or flags & 0x10200000:
            raise ReadError('Component weak identity invalid')
        pawn = next(m for m in actors['network_guid_actor_matches'] if m['actor']['address'] == identity['outer_address'])
        cache = int(pawn['guid_cache'], 16)
        data, count, capacity = reader.unpack(cache+0x10, '<Qii')
        if not 0 <= count <= capacity <= 100000:
            raise ReadError('GUID map bounds invalid')
        raw = reader.read(data, count*80)
        matches = []
        for i in range(count):
            oid, server, randomizer, idx, ser = struct.unpack_from('<QIIii', raw, i*80)
            if idx == index and ser == serial and oid > 1:
                matches.append({'object_id': f'0x{oid:016x}', 'server_id': server, 'randomizer': randomizer})
        prop = probe.properties_for(address)['StatRepInt32EveryoneProxy']
        if prop['offset_in_object'] != 0xbf0 or prop.get('referenced_type') != 'StatInt32Rep':
            raise ReadError('Exact gravity wrapper property required')
        items, item_count, item_capacity = reader.unpack(address+0xbf0+0x108, '<Qii')
        if not 0 <= item_count <= item_capacity <= 2048:
            raise ReadError('Stat replication item bounds invalid')
        rows = []
        for i in range(item_count):
            raw_item = reader.read(items+i*40, 40)
            rows.append({'replication_id':struct.unpack_from('<i',raw_item)[0],
                         'record':hex(struct.unpack_from('<Q',raw_item,16)[0]),
                         'value_bits':hex(struct.unpack_from('<I',raw_item,24)[0])})
        speed_entry = hash_entry(reader, address+probe.properties_for(address)['StatsInt32']['offset_in_object'], 56, 0x6357c09a5679)
        speed_bits = reader.unpack(speed_entry+12, '<I')[0] if speed_entry else None
        gravity_entry = hash_entry(reader, address+probe.properties_for(address)['StatsInt32']['offset_in_object'], 56, 0x5429e5e8643f0018)
        gravity_bits = reader.unpack(gravity_entry+12, '<I')[0] if gravity_entry else None
        return {'pid': pid, 'client_proof': client_proof(pid), 'component': identity,
                'accepted_component_guids': matches, 'property': prop,
                'array_item_count': item_count, 'array_flags': reader.unpack(address+0xbf0+0x100, '<B')[0],
                'replicated_items': rows, 'movement_speed_value_bits':speed_bits,
                'gravity_value_bits':gravity_bits,
                'delegate_wrapper': hex(reader.unpack(address+0xbf0+0x118, '<Q')[0]),
                'functions_invoked': False}
    finally:
        reader.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid', type=int, required=True)
    p.add_argument('--actors', type=Path, required=True)
    p.add_argument('--receiver', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    d = inspect(a.pid, a.actors, a.receiver)
    a.output.write_text(json.dumps(d, indent=2), encoding='utf-8')
    print(json.dumps(d))
