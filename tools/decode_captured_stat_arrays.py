"""Decode offline captured stat arrays using exact live definition IDs; no replay.

Field maximum and the one-bit custom-delta prefix remain capture hypotheses
until the current network cache and native field serializer are verified.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dump_runtime_reflection import Reader, Reflection, ReadError
from protocol_proof import EXPECTED_EXE, client_proof
from inspect_character_stats import hash_entry
from lab.unreal import BitReader


def decode(pid, source):
    capture = json.loads(Path(source).read_text())
    block = next(b for b in capture['blocks'] if b['content_bits'] == 68597)
    bits = BitReader(bytes.fromhex(block['content_hex']), block['content_bits'])
    reader = Reader(pid, EXPECTED_EXE)
    try:
        reflection = Reflection(reader, 500000)
        index, serial = reader.unpack(reader.base + 0xd932ba0, '<ii')
        if not 0 <= index < reflection.count or serial <= 0:
            raise ReadError('Current manager weak identity required')
        chunk = reader.unpack(reflection.chunks + index // 65536 * 8, '<Q')[0]
        slot = chunk + index % 65536 * 24
        manager, flags = reader.unpack(slot, '<QI')
        if reader.unpack(slot + 16, '<i')[0] != serial or flags & 0x10200000:
            raise ReadError('Manager weak identity changed')
        stat_type = hash_entry(reader, manager + 0x1f0, 0xb0, 0x4a74ae5ed850dc97)
        if not stat_type:
            raise ReadError('Exact integer stat definition type required')
        fields = []
        while bits.remaining:
            start = bits.pos
            field = bits.uint(23)
            length = bits.packed()
            end = bits.pos + length
            if length < 129 or end > bits.limit:
                return {'fields': fields, 'unreviewed_suffix_start': start,
                        'remaining_bits': bits.limit - start, 'complete': False}
            prefix = bits.read(1)
            key, base_key, deleted, changed = [bits.read(32) for _ in range(4)]
            if deleted > 2048 or changed > 2048:
                raise ReadError('Capture array counts exceed bounded scope')
            deleted_ids = [bits.read(32) for _ in range(deleted)]
            rows = []
            for i in range(changed):
                item_start = bits.pos
                replication_id, guid, value = bits.read(32), bits.read(64), bits.read(32)
                entry = hash_entry(reader, stat_type + 8, 24, guid)
                if not entry:
                    raise ReadError(f'No exact stat record {guid:#x} at {item_start}, item {i}')
                record = reader.unpack(entry + 8, '<Q')[0]
                if reader.unpack(record + 8, '<Q')[0] != guid:
                    raise ReadError('Record identity mismatch')
                extra = reader.unpack(record + 0x247, '<B')[0]
                ni, nn = reader.unpack(record + 0x18, '<II')
                row = {'start_bit': item_start, 'replication_id': replication_id,
                       'record': hex(guid), 'name': reflection.names.get(ni, nn),
                       'value_bits': hex(value), 'conditional_base_equipment': bool(extra)}
                if extra:
                    row.update(base_bits=hex(bits.read(32)), equipment_bits=hex(bits.read(32)))
                rows.append(row)
            if bits.pos != end:
                raise ReadError(f'Field payload boundary differs: {bits.pos} != {end}')
            fields.append({'start': start, 'field_index_candidate': field,
                           'payload_bits': length, 'prefix_bit': prefix,
                           'array_key': key, 'base_key': base_key,
                           'deleted_ids': deleted_ids, 'items': rows, 'end': end})
        return {'source': str(source), 'client_proof': client_proof(pid),
                'fields': fields, 'complete': True, 'replayed': False,
                'field_maximum_and_prefix_meaning': 'unverified capture hypotheses'}
    finally:
        reader.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = decode(args.pid, args.source)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'complete': report['complete'], 'fields':
        [{k: v for k, v in f.items() if k != 'items'} | {'item_count': len(f['items']),
          'gravity': [r for r in f['items'] if r['record'] == '0x5429e5e8643f0018']}
         for f in report['fields']]}))
