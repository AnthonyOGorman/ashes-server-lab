"""Read reflected stat identities and bounded native stat hash entries; no writes/calls."""
import argparse
import json
import struct
from pathlib import Path
from inspect_movement_prerequisites import MovementProbe
from dump_runtime_reflection import Reader, ReadError, pointer
from protocol_proof import EXPECTED_EXE, client_proof
from inspect_movement_serializers import PE


def hash_entry(reader, base, stride, key):
    slots, size, cap = reader.unpack(base, '<Qii')
    free_count = reader.unpack(base+0x34, '<i')[0]
    bucket_count = reader.unpack(base+0x48, '<i')[0]
    if size == 0:
        return None
    if not pointer(slots) or not 0 <= free_count <= size <= cap <= 1000000 or not 0 < bucket_count <= 1048576 or bucket_count & (bucket_count-1):
        raise ReadError('Invalid bounded native record map')
    buckets = reader.unpack(base+0x40, '<Q')[0] or base+0x38
    idx = reader.unpack(buckets+(((key >> 32)*23+key)&(bucket_count-1))*4, '<i')[0]
    seen = set()
    while idx != -1:
        if not 0 <= idx < size or idx in seen or len(seen) >= 4096:
            raise ReadError('Invalid bounded record hash chain')
        seen.add(idx)
        entry_address = slots+idx*stride
        raw = reader.read(entry_address, stride)
        if struct.unpack_from('<Q', raw)[0] == key:
            return entry_address
        idx = struct.unpack_from('<i', raw, stride-8)[0]
    return None


def inspect(pid, pawn, configuration_only=False):
    reader = Reader(pid, EXPECTED_EXE)
    try:
        probe = MovementProbe(reader)
        pe = PE(Path(EXPECTED_EXE).read_bytes())
        float_leaf = bytes.fromhex('8b0189442408f30f10442408c3')
        if reader.read(reader.base+0x6175ec0, len(float_leaf)) != float_leaf:
            raise ReadError('Reviewed packed stat float reinterpretation leaf differs')
        for start, end in ((0x6b411a0, 0x6b412e9), (0x60accf0, 0x60ace2d), (0x580ddc0, 0x580dee5)):
            if reader.read(reader.base+start, end-start) != pe.data[pe.offset(start):pe.offset(start)+end-start]:
                raise ReadError('Native gravity/record lookup differs from reviewed executable')
        index, serial = reader.unpack(reader.base+0xd932ba0, '<ii')
        if not 0 <= index < probe.reflection.count or serial <= 0:
            raise ReadError('Current design manager weak identity required')
        chunk = reader.unpack(probe.reflection.chunks+(index//65536)*8, '<Q')[0]
        item = reader.read(chunk+(index%65536)*24, 24)
        manager, flags = struct.unpack_from('<QI', item)
        if struct.unpack_from('<i', item, 16)[0] != serial or flags & 0x10200000:
            raise ReadError('Design manager serial/flags invalid')
        manager_identity = probe.identity(manager, 'DesignDataManagerBase')
        type_entry = hash_entry(reader, manager+0x1f0, 0xb0, 0x6a9c0102f8f941c0)
        if not type_entry:
            raise ReadError('Reviewed game configuration type missing')
        config_entry = hash_entry(reader, type_entry+8, 24, 0x636a8ad25678)
        if not config_entry:
            raise ReadError('Reviewed game configuration record missing')
        config = reader.unpack(config_entry+8, '<Q')[0]
        if not pointer(config) or reader.unpack(config+8, '<Q')[0] != 0x636a8ad25678:
            raise ReadError('Configuration record identity mismatch')
        gravity_record, gravity_guid, gravity_type = reader.unpack(config+0x1530, '<QQQ')
        if not pointer(gravity_record) or reader.unpack(gravity_record+8, '<Q')[0] != gravity_guid:
            raise ReadError('Cached gravity record pointer and ID disagree')
        gravity_name_index, gravity_name_number = reader.unpack(gravity_record+0x18, '<II')
        gravity_name = probe.reflection.names.get(gravity_name_index, gravity_name_number)
        config_name_index, config_name_number = reader.unpack(config+0x18, '<II')
        config_report = {'manager': manager_identity, 'record_name': probe.reflection.names.get(config_name_index, config_name_number),
                         'record_guid': '0x636a8ad25678', 'gravity_stat_guid': hex(gravity_guid), 'gravity_stat_type': hex(gravity_type),
                         'gravity_stat_name': gravity_name, 'gravity_record_type_byte': reader.unpack(gravity_record+0x79, '<B')[0]}
        if configuration_only:
            return {'client_proof': client_proof(pid), 'configuration': config_report, 'functions_invoked': False}
        stats = probe.fields(pawn, ['StatsComponent'])['StatsComponent']['value']
        address = int(stats['address'], 16)
        prop = probe.properties_for(address)['StatList']
        inner = reader.unpack(int(prop['address'], 16)+0x78, '<Q')[0]
        element = probe.reflection.properties(inner)[0]
        if element['type'] != 'StructProperty' or element['referenced_type'] != 'StatInitialization' or element['element_size'] != 72:
            raise ReadError(f'Exact reflected StatInitialization array required; observed {element}')
        data, count, capacity = reader.unpack(address+prop['offset_in_object'], '<Qii')
        if not pointer(data) or not 0 < count <= capacity <= 4096:
            raise ReadError('Bounded stat list required')
        rows = []
        for i in range(count):
            raw = reader.read(data+i*72, 56)
            guid, type_id, name, number = struct.unpack_from('<QQII', raw)
            resolved = probe.reflection.names.get(name, number)
            if guid == gravity_guid and type_id == gravity_type:
                resolved = 'Gravity multiplier (exact configuration ID)'
            if guid != gravity_guid and not any(t in resolved.lower() for t in ('gravity', 'speed', 'health')):
                continue
            row = {'name': resolved, 'guid': hex(guid), 'type_id': hex(type_id), 'raw_identity': raw.hex(), 'entries': []}
            for map_name, stride in (('StatsInt32', 56), ('StatsFloatArray', 40)):
                mp = probe.properties_for(address)[map_name]
                base = address+mp['offset_in_object']
                slots, size, cap = reader.unpack(base, '<Qii')
                free_count = reader.unpack(base+0x34, '<i')[0]
                buckets = reader.unpack(base+0x40, '<Q')[0] or base+0x38
                bucket_count = reader.unpack(base+0x48, '<i')[0]
                if size == 0:
                    continue
                if not pointer(slots) or not 0 <= free_count <= size <= cap <= 4096 or not 0 < bucket_count <= 8192 or bucket_count & (bucket_count-1):
                    raise ReadError('Invalid bounded native stat map')
                idx = reader.unpack(buckets+(((guid >> 32)*23+guid)&(bucket_count-1))*4, '<i')[0]
                seen = set()
                while idx != -1:
                    if not 0 <= idx < size or idx in seen:
                        raise ReadError('Invalid stat hash chain')
                    seen.add(idx)
                    entry = reader.read(slots+idx*stride, stride)
                    key = struct.unpack_from('<Q', entry)[0]
                    if key == guid:
                        value = {'map': map_name, 'slot': idx, 'raw_value': entry[8:stride-8].hex()}
                        if map_name == 'StatsInt32':
                            value['packed_base_value_min_max'] = list(struct.unpack_from('<4i', entry, 8))
                            value['float_base_value_min_max'] = list(struct.unpack_from('<4f', entry, 8))
                        else:
                            array, n, maximum = struct.unpack_from('<Qii', entry, 8)
                            if not 0 <= n <= maximum <= 256 or (n and not pointer(array)):
                                raise ReadError('Invalid float stat array')
                            value['float_values'] = [list(reader.unpack(array+j*112+16, '<fff')) for j in range(n)]
                        row['entries'].append(value)
                        break
                    idx = struct.unpack_from('<i', entry, stride-8)[0]
            rows.append(row)
        return {'client_proof': client_proof(pid), 'stats': stats, 'configuration': config_report, 'stat_count': count,
                'matching_stats': rows, 'functions_invoked': False,
                'packed_float_decode_proof': {'rva': '0x6175ec0', 'exact_bytes': float_leaf.hex(), 'interpretation': 'MOV integer bits through stack followed by MOVSS; float32 bit reinterpretation'},
                'values_interpretation': 'Gravity StatType0 is float32 stored as integer bits; raw zero decodes to 0.0'}
    finally:
        reader.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid', type=int, required=True)
    p.add_argument('--pawn', type=lambda v: int(v, 0), required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--configuration-only', action='store_true')
    args = p.parse_args()
    report = inspect(args.pid, args.pawn, args.configuration_only)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
