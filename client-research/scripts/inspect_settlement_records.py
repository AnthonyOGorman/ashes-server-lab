"""Read settlement design records and existing actors; no calls, inputs or writes."""
import argparse, json, math, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / 'tools'))
from inspect_movement_prerequisites import MovementProbe
from inspect_character_stats import hash_entry
from dump_runtime_reflection import Reader, pointer
from protocol_proof import client_proof, EXPECTED_EXE

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('pid', type=int)
parser.add_argument('--services-only', action='store_true', help='Read plot/building graph in a separate snapshot')
args = parser.parse_args()
proof = client_proof(args.pid)
assert proof['sha256'] == json.loads((ROOT/'index/summary.json').read_text())['native']['sha256']
r = Reader(args.pid, EXPECTED_EXE)
try:
    p = MovementProbe(r)
    def string(address):
        data, count, capacity = r.unpack(address, '<Qii')
        assert 0 <= count <= capacity <= 1048576, (hex(address),hex(data),count,capacity)
        if not count:
            return ''
        assert pointer(data)
        raw = r.read(data, count*2)
        assert raw[-2:] == b'\0\0'
        return raw[:-2].decode('utf-16-le')

    def entries(base, stride, maximum=100000):
        slots, size, capacity = r.unpack(base, '<Qii')
        free = r.unpack(base+0x34, '<i')[0]
        if not size:
            return []
        buckets_n = r.unpack(base+0x48, '<i')[0]
        assert pointer(slots) and 0 <= free <= size <= capacity <= maximum
        assert 0 < buckets_n <= 131072 and not buckets_n & (buckets_n-1)
        buckets = r.unpack(base+0x40, '<Q')[0] or base+0x38
        heads = r.unpack(buckets, '<'+'i'*buckets_n)
        seen, addresses = set(), []
        for current in heads:
            while current != -1:
                assert 0 <= current < size and current not in seen
                seen.add(current)
                address = slots+stride*current
                addresses.append(address)
                current = r.unpack(address+stride-8, '<i')[0]
        assert len(seen) == size-free
        return addresses

    index, serial = r.unpack(r.base+0xd932ba0, '<ii')
    assert 0 <= index < p.reflection.count and serial > 0
    chunk = r.unpack(p.reflection.chunks+(index//65536)*8, '<Q')[0]
    manager, flags, cluster, actual_serial = r.unpack(chunk+(index%65536)*24, '<Qiii')
    assert serial == actual_serial and not flags & 0x10200000
    manager_identity = p.identity(manager, 'DesignDataManagerBase')
    manager_prop = p.property(manager, 'DesignDataTypeMap', 0x170, 0x50)
    assert manager_prop['type'] == 'MapProperty'
    names = {}
    for address in entries(manager+0x170, 0x50, 4096):
        key, value_id = r.unpack(address, '<QQ')
        assert key == value_id
        names[string(address+16)] = key

    type_names = ('ServiceBuildingPlot','Building','BuildingNodeAssetSets') if args.services_only else (
        'CityNode', 'Layout', 'NodeAssetSet', 'NodeAssetDefinition', 'NodeModification', 'NodeLevelDetails', 'ZOI')
    selected = {name: key for name, key in names.items() if name in type_names}
    assert set(type_names) <= set(selected), sorted(names)
    wanted = {'DesignDataTypeDef', 'CityNodeRecordBase', 'LayoutRecordBase',
        'NodeAssetSetRecordBase', 'NodeAssetDefinitionRecordBase', 'NodeModificationRecordBase',
        'NodeLevelDetailsRecordBase', 'NodeAssetSetTransformTuple', 'NodeAssetTransformTuple',
        'NodeAssetDefinitionInfo', 'NodeAssetDefinitionInstanceData', 'NodeLayoutAssetSetGuids',
        'NodeAssetSetFastArrayItem', 'ZOIRecordBase', 'PlotArray', 'LocaleArray',
        'ServicePlotTransformTuple', 'LocaleOriginTransformTuple',
        'ServiceBuildingPlotRecordBase','BuildingRecordBase','BuildingNodeAssetSetsRecordBase'}
    layouts, actors = {}, []
    actor_classes = {'NodeLayoutReplicator', 'AshesNodeLevelInstance', 'NodeLayoutRegistrationComponent', 'AoCNodeTrigger'}
    for address, obj in p.reflection.objects():
        cls = p.reflection.class_name(obj['class_address'])
        if obj['name'] in wanted and cls == 'ScriptStruct':
            size = r.unpack(address+0x78, '<i')[0]
            layouts[obj['name']] = {'identity': p.identity(address), 'size': size,
                'alignment': r.unpack(address+0x7c, '<h')[0],
                'properties': p.reflection.properties(r.unpack(address+0x70, '<Q')[0], size)}
        if cls in actor_classes and not obj['name'].startswith('Default__'):
            actors.append({'identity': p.identity(address), 'fields': p.fields(address,
                ['NodeGuid', 'LayoutAssetSetGuids', 'NodeRecordGuid', 'AssetPath', 'RootComponent', 'WorldAsset'])})

    def alignment(prop):
        kind, size, ref = prop['type'], prop['element_size'], prop.get('referenced_type', '')
        if kind == 'StructProperty':
            if ref in layouts:
                return layouts[ref]['alignment']
            if ref == 'Transform':
                return 16
            return 8
        return min(size,8) if kind not in ('ArrayProperty','MapProperty','StrProperty') else 8

    def decode(base, prop, depth=0):
        assert depth <= 6
        address = base+prop['offset_in_object']
        kind, size, ref = prop['type'], prop['element_size'], prop.get('referenced_type', '')
        if kind == 'StrProperty':
            return string(address)
        if kind == 'Int64Property':
            return r.unpack(address, '<q')[0]
        if kind == 'StructProperty':
            if ref in ('Vector', 'Rotator') and size == 24:
                result = list(r.unpack(address, '<ddd'));assert all(math.isfinite(x) for x in result)
                return result
            if ref == 'Transform' and size == 96:
                values = r.unpack(address, '<12d');assert all(math.isfinite(x) for x in values)
                return {'quaternion': values[:4], 'translation': values[4:7], 'scale': values[8:11]}
            if ref.endswith('Id') and size == 56:
                record_id, type_id = r.unpack(address, '<QQ')
                return {'record_id': hex(record_id), 'type_id': hex(type_id), 'type_name': next((n for n,t in names.items() if t==type_id), None)}
            if ref == 'SoftObjectPath' and size == 32:
                a,b,c,d = r.unpack(address, '<IIII')
                return {'package': p.reflection.names.get(a,b), 'asset': p.reflection.names.get(c,d), 'sub_path': string(address+16)}
            if ref in layouts:
                assert layouts[ref]['size'] == size
                return {field['name']: decode(address,field,depth+1) for field in layouts[ref]['properties']}
        if kind == 'ArrayProperty' and (depth or prop['name'] in
                ('Props','ContainedAssetDefinitions','ValidCultures','ValidNodeTypes','ValidBiomes','ValidSeasons','LevelModificationsIds',
                 'BuildingsIds','ConstructionAssetSetIds','OperationalAssetSetIds','DisarrayAssetSetIds',
                 'DamagedAssetSetIds','RepairingAssetSetIds','DestroyedAssetSetIds','DemolitionAssetSetIds')):
            data,count,capacity = r.unpack(address,'<Qii')
            assert 0 <= count <= capacity <= 8192 and (not count or pointer(data))
            inner = r.unpack(int(prop['address'],16)+0x78,'<Q')[0]
            element = p.reflection.properties(inner)[0]
            assert 0 < element['element_size'] <= 4096 and element['offset_in_object'] == 0, (prop['name'],element)
            return {'count': count, 'element_metadata': element,
                'items': [decode(data+i*element['element_size'],element,depth+1) for i in range(count)]}
        if kind == 'MapProperty' and prop['name'] in ('ContainedAssets','PlotsPerNodeLevel','LocaleOriginsPerLevel'):
            key_address,value_address = r.unpack(int(prop['address'],16)+0x70,'<QQ')
            key,value = p.reflection.properties(key_address)[0],p.reflection.properties(value_address)[0]
            assert key['offset_in_object'] == 0
            ka,va = alignment(key),alignment(value)
            assert ka in (1,2,4,8,16) and va in (1,2,4,8,16)
            value_offset = (key['element_size']+va-1)&-va
            assert value['offset_in_object'] == value_offset, (prop['name'],key,value,value_offset)
            entry_align = max(ka,va)
            pair_size = (value_offset+value['element_size']+entry_align-1)&-entry_align
            stride = (pair_size+8+entry_align-1)&-entry_align
            assert entry_align <= 8, '16-byte map allocation layout requires separate binding'
            rows = [{'key': decode(item,key,depth+1), 'value': decode(item,value,depth+1)}
                for item in entries(address,stride,8192)]
            return {'count':len(rows),'key_metadata':key,'value_metadata':value,
                'stride':stride,'value_offset':value_offset,'items':rows}
        if kind in ('ArrayProperty', 'MapProperty'):
            return {'raw_header': r.read(address, size).hex(), 'elements_decoded': False}
        if kind == 'EnumProperty' and size == 2:
            return r.unpack(address,'<H')[0]
        result = p.decode(base, prop)
        return result.get('value', {'status': result['status'], 'raw': r.read(address,size).hex()})

    records = {}
    for name, type_id in selected.items():
        type_entry = hash_entry(r, manager+0x1f0, 0xb0, type_id)
        if not type_entry:
            records[name] = {'status': 'no loaded record map'}
            continue
        layout = layouts.get(name+'RecordBase')
        assert layout, name
        rows = []
        for address in entries(type_entry+8, 24):
            record_id, record = r.unpack(address, '<QQ')
            assert record and r.unpack(record+8, '<Q')[0] == record_id
            ni, nn = r.unpack(record+0x18, '<II')
            fields = {prop['name']: decode(record,prop) for prop in layout['properties']}
            if name == 'CityNode':
                fields['native_zoi_id_at_9b8'] = hex(r.unpack(record+0x9b8,'<Q')[0])
            rows.append({'record_id': hex(record_id), 'name': p.reflection.names.get(ni,nn),
                'address': hex(record), 'fields': fields})
        records[name] = {'type_id': hex(type_id), 'count': len(rows), 'records': rows}

    end = client_proof(args.pid)
    for key in ('pid', 'exe', 'sha256', 'process_created_filetime'):
        assert proof[key] == end[key]
    out = {'proof': end, 'access': 'read-only; no inputs, calls or process writes',
        'manager': manager_identity, 'design_type_names': {n:hex(t) for n,t in names.items()},
        'selected_types': {n:hex(t) for n,t in selected.items()}, 'layouts': layouts,
        'records': records, 'existing_node_objects': actors, 'bytes_read': r.bytes_read,
        'limits': ['Loaded definition records do not establish server state or streamed collision.',
            'Undecoded array/map headers are explicit gaps; no wire handles inferred.']}
    encoded = json.dumps(out, indent=2)
    stem = 'settlement-service-records-live' if args.services_only else 'settlement-records-live'
    (ROOT/f'proofs/{stem}-{args.pid}-{end["process_created_filetime"]}.json').write_text(encoded, encoding='utf-8')
    (ROOT/f'proofs/{stem}.json').write_text(encoded, encoding='utf-8')
    print(json.dumps({'proof': end, 'selected_types': out['selected_types'],
        'counts': {n:x.get('count',0) for n,x in records.items()}, 'existing_node_objects': len(actors),
        'bytes_read': r.bytes_read}, indent=2))
finally:
    r.close()
