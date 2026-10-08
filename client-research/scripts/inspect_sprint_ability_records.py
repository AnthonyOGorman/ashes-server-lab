"""Read hash-bound sprint ability record metadata; no process writes or game calls."""
import argparse, json, struct, sys
from pathlib import Path
R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R.parent / 'tools'))
from inspect_movement_prerequisites import MovementProbe
from inspect_character_stats import hash_entry
from dump_runtime_reflection import Reader
from protocol_proof import client_proof, EXPECTED_EXE

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('pid', type=int)
args = parser.parse_args()
proof = client_proof(args.pid)
assert proof['sha256'] == json.loads((R/'index/summary.json').read_text())['native']['sha256']
r = Reader(args.pid, EXPECTED_EXE)
try:
    p = MovementProbe(r)
    wanted = {'AbilityCost': 0xc8, 'AbilityStatCost': 0x88, 'AoCExpression': 0x50,
        'AoCAbilityRecordBase': 0x1230}
    layouts = {}
    for address, obj in p.reflection.objects():
        if obj['name'] not in wanted or p.reflection.class_name(obj['class_address']) != 'ScriptStruct':
            continue
        size = r.unpack(address+0x78, '<i')[0]
        assert size == wanted[obj['name']]
        layouts[obj['name']] = {'identity': p.identity(address), 'size': size,
            'properties': p.reflection.properties(r.unpack(address+0x70, '<Q')[0], size)}
        if len(layouts) == len(wanted):
            break
    assert set(layouts) == set(wanted)
    def field_layout(owner, name, offset, size, kind):
        field = next(x for x in layouts[owner]['properties'] if x['name'] == name)
        assert (field['offset_in_object'], field['element_size'], field['type']) == (offset, size, kind)
        return field
    field_layout('AbilityCost', 'Enabled', 0, 0x50, 'StructProperty')
    field_layout('AbilityCost', 'StatCosts', 0x50, 0x10, 'ArrayProperty')
    field_layout('AbilityStatCost', 'Stat', 0, 0x38, 'StructProperty')
    field_layout('AbilityStatCost', 'Value', 0x38, 0x50, 'StructProperty')
    field_layout('AoCExpression', 'Expression', 0, 0x10, 'StrProperty')
    costs_property = field_layout('AoCAbilityRecordBase', 'Costs', 0x450, 0x10, 'ArrayProperty')
    def struct_target(prop):
        target = r.unpack(int(prop['address'], 16)+0x70, '<Q')[0]
        assert p.reflection.class_name(p.reflection.obj(target)['class_address']) == 'ScriptStruct'
        return p.identity(target)
    def array_struct_target(prop):
        inner = r.unpack(int(prop['address'], 16)+0x78, '<Q')[0]
        fields = p.reflection.properties(inner)
        assert fields and fields[0]['type'] == 'StructProperty'
        return struct_target(fields[0])
    assert array_struct_target(costs_property)['name'] == 'AbilityCost'
    assert array_struct_target(field_layout('AbilityCost', 'StatCosts', 0x50, 0x10, 'ArrayProperty'))['name'] == 'AbilityStatCost'
    assert struct_target(field_layout('AbilityStatCost', 'Stat', 0, 0x38, 'StructProperty'))['name'] == 'StatTypeDefId'
    assert struct_target(field_layout('AbilityStatCost', 'Value', 0x38, 0x50, 'StructProperty'))['name'] == 'AoCExpression'
    def candidate_string(address):
        data, count, cap = r.unpack(address, '<Qii')
        if not 0 < count <= cap <= 8192 or not data:
            return None
        raw = r.read(data, count*2)
        if raw[-2:] != b'\x00\x00':
            return None
        return raw[:-2].decode('utf-16-le')
    index, serial = r.unpack(r.base+0xd932ba0, '<ii')
    assert 0 <= index < p.reflection.count and serial > 0
    chunk = r.unpack(p.reflection.chunks+(index//65536)*8, '<Q')[0]
    manager, flags, cluster, actual_serial = r.unpack(chunk+(index%65536)*24, '<Qiii')
    assert serial == actual_serial and not flags & 0x10200000
    identity = p.identity(manager, 'DesignDataManagerBase')
    type_id = 0x198cb7f1dd552cb7
    entry = hash_entry(r, manager+0x1f0, 0xb0, type_id)
    assert entry
    base = entry+8
    slots, size, capacity = r.unpack(base, '<Qii')
    bucket_count = r.unpack(base+0x48, '<i')[0]
    assert 0 < size <= capacity <= 100000 and 0 < bucket_count <= 131072
    assert bucket_count & (bucket_count-1) == 0
    buckets = r.unpack(base+0x40, '<Q')[0] or base+0x38
    indices = struct.unpack('<'+'i'*bucket_count, r.read(buckets, bucket_count*4))
    seen, matches = set(), []
    for first in indices:
        current = first
        chain = set()
        while current != -1:
            assert 0 <= current < size and current not in chain
            chain.add(current)
            assert current not in seen
            seen.add(current)
            record_id, record, following = r.unpack(slots+current*24, '<QQi')
            current = following
            assert record and r.unpack(record+8, '<Q')[0] == record_id
            ni, nn = r.unpack(record+0x18, '<II')
            name = p.reflection.names.get(ni, nn)
            if 'sprint' not in name.casefold():
                continue
            combos, count, cap = r.unpack(record+0x7d0, '<Qii')
            assert 0 <= count <= cap <= 64
            costs, nc, cc = r.unpack(record+0x450, '<Qii')
            assert 0 <= nc <= cc <= 128
            cost_candidates = []
            if nc:
                # Only the first element; reflected runtime layouts and links checked above.
                statdata, statcount, statcap = r.unpack(costs+0x50, '<Qii')
                assert 0 <= statcount <= statcap <= 128
                candidate = {'raw_first_cost_prefix': r.read(costs, 0xc8).hex(),
                    'enabled_fstring_candidate': candidate_string(costs),
                    'stat_cost_count_candidate': statcount,
                    'limitations': 'Definition strings/layout verified; native evaluator context and payment cadence unresolved.'}
                if statcount:
                    candidate['raw_first_stat_cost'] = r.read(statdata, 0x88).hex()
                    candidate['value_expression_at_0x20_candidate'] = candidate_string(statdata+0x20)
                    candidate['value_expression_at_0x38_candidate'] = candidate_string(statdata+0x38)
                    candidate['first_three_reference_words'] = [hex(x) for x in r.unpack(statdata, '<QQQ')]
                    guid, typ = r.unpack(statdata, '<QQ')
                    stat_type_entry = hash_entry(r, manager+0x1f0, 0xb0, typ)
                    assert stat_type_entry
                    stat_entry = hash_entry(r, stat_type_entry+8, 24, guid)
                    assert stat_entry
                    stat_record = r.unpack(stat_entry+8, '<Q')[0]
                    assert r.unpack(stat_record+8, '<Q')[0] == guid
                    ni, nn = r.unpack(stat_record+0x18, '<II')
                    candidate['resolved_stat'] = {'record_id': hex(guid), 'type_id': hex(typ),
                        'name': p.reflection.names.get(ni, nn)}
                    candidate['verified_enabled_expression'] = candidate['enabled_fstring_candidate']
                    candidate['verified_value_expression'] = candidate['value_expression_at_0x38_candidate']
                cost_candidates.append(candidate)
            matches.append({'record_id': hex(record_id), 'address': hex(record), 'name': name,
                'combo_inputs': list(r.read(combos, count)) if count else [],
                'exact_input': r.unpack(record+0x7e0, '<B')[0],
                'buffer_priority': r.unpack(record+0x7e4, '<i')[0],
                'cost_count': nc, 'cost_array_address': hex(costs), 'cost_candidates': cost_candidates,
                'record_prefix_hex': r.read(record, 0x40).hex()})
    end = client_proof(args.pid)
    for key in ('pid', 'exe', 'sha256', 'process_created_filetime'):
        assert proof[key] == end[key]
    result = {'proof': end, 'manager': identity, 'ability_type_id': hex(type_id), 'reflected_cost_layouts': layouts,
        'access': 'read-only; no process writes or game calls', 'occupied_records': len(seen),
        'matches': matches, 'limitations': ['Name-matched definitions, not proof of granted/triggered abilities or effects.']}
    encoded = json.dumps(result, indent=2)
    (R/f'proofs/sprint-ability-records-live-{args.pid}-{proof["process_created_filetime"]}.json').write_text(encoded)
    (R/'proofs/sprint-ability-records-live.json').write_text(encoded)
    print(json.dumps({k:v for k,v in result.items() if k != 'reflected_cost_layouts'}, indent=2))
finally:
    r.close()
