"""Read-only resource IDs, design metadata, stat initialization and cache."""
import json, sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from inspect_movement_prerequisites import MovementProbe
from inspect_character_stats import hash_entry
from dump_runtime_reflection import Reader, ReadError
from protocol_proof import client_proof, EXPECTED_EXE
root = Path(__file__).resolve().parents[1]
s = json.loads((root/'data/client-inspection.json').read_text()); proof = client_proof(s['pid'])
for key in ('pid','exe','sha256','process_created_filetime'): assert proof[key] == s['client_proof'][key]
r = Reader(s['pid'], EXPECTED_EXE)
try:
    p = MovementProbe(r)
    index, serial = r.unpack(r.base+0xd932ba0, '<ii')
    chunk = r.unpack(p.reflection.chunks+(index//65536)*8, '<Q')[0]
    item = r.read(chunk+(index%65536)*24,24)
    manager = struct.unpack_from('<Q',item)[0]
    assert struct.unpack_from('<i',item,16)[0] == serial
    p.identity(manager,'DesignDataManagerBase')
    entry = hash_entry(r,manager+0x1f0,0xb0,0x6a9c0102f8f941c0)
    config = r.unpack(hash_entry(r,entry+8,24,0x636a8ad25678)+8,'<Q')[0]
    assert r.unpack(config+8,'<Q')[0] == 0x636a8ad25678
    pawn = int(next(x['actor']['address'] for x in s['network_guid_actor_matches'] if x['actor']['class']=='PlayerPawn_C'),16)
    stats = int(p.fields(pawn,['StatsComponent'])['StatsComponent']['value']['address'],16)
    prop=p.properties_for(stats)['StatList']; inner=r.unpack(int(prop['address'],16)+0x78,'<Q')[0]
    element=p.reflection.properties(inner)[0]; struct_ptr=r.unpack(int(element['address'],16)+0x70,'<Q')[0]
    head=r.unpack(struct_ptr+0x70,'<Q')[0]; size=r.unpack(struct_ptr+0x78,'<i')[0]
    fields=p.reflection.properties(head,size)
    data,count,cap=r.unpack(stats+prop['offset_in_object'],'<Qii');assert 0<count<=cap<=4096
    resources=[]
    for name,offset in [('MaxHealth',0x1330),('Health',0x1350),('MaxMana',0x1390),('Mana',0x13b0),('MaxStamina',0x13d0),('Stamina',0x13f0)]:
        record,guid,typ=r.unpack(config+offset,'<QQQ'); assert record and r.unpack(record+8,'<Q')[0]==guid
        ni,nn=r.unpack(record+0x18,'<II')
        row={'name':name,'record_name':p.reflection.names.get(ni,nn),'record_id':hex(guid),'type_id':hex(typ),'stat_type':r.unpack(record+0x79,'<B')[0],'replication':r.unpack(record+0x246,'<B')[0],'base_and_equipment_buckets':r.unpack(record+0x247,'<B')[0]}
        mp=p.properties_for(stats)['StatsInt32']; cached=hash_entry(r,stats+mp['offset_in_object'],56,guid)
        row['cached_int32']=list(r.unpack(cached+8,'<4i')) if cached else None
        row['cached_float_bits']=list(r.unpack(cached+8,'<4f')) if cached else None
        row['initialization']=[{'slot':i,'raw':r.read(data+i*72,72).hex()} for i in range(count) if r.unpack(data+i*72,'<Q')[0]==guid]
        resources.append(row)
    driver=int(s['net_drivers'][0]['address'],16); cache_manager=r.unpack(driver+0x210,'<Q')[0]
    entries,n,cap=r.unpack(cache_manager+8,'<Qii'); assert 0<n<=cap<=256
    cls=p.reflection.obj(stats)['class_address']; class_index=p.reflection.obj(cls)['index']
    caches=[r.unpack(entries+i*24+8,'<Q')[0] for i in range(n) if r.unpack(entries+i*24,'<i')[0]==class_index]; assert len(caches)==1
    cache=caches[0]; props={int(v['address'],16):v for v in p.properties_for(stats).values()}
    field_data,field_count,field_cap=r.unpack(cache+0x20,'<Qii'); assert 0<field_count<=field_cap<=4096
    base=r.unpack(cache,'<i')[0]; net_fields=[]
    for i in range(field_count):
        tagged,index=r.unpack(field_data+i*24,'<Qi'); assert index==base+i
        address=tagged&~1
        name=p.reflection.obj(address)['name'] if tagged&1 else props[address]['name']
        if 'StatRepInt32' in name: net_fields.append({'name':name,'field_index':index,'maximum':base+field_count+1})
    result={'proof':proof,'resources':resources,'initialization_layout':fields,'stat_count':count,'net_fields':net_fields,'functions_invoked':False}
    (root/'runs/character-movement-followup-20261007/native-resources.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
finally:r.close()
