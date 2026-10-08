"""Read same-lifetime client stat FastArray network fields; no game calls or writes."""
import json,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R.parent/'tools'))
from inspect_movement_prerequisites import MovementProbe
from dump_runtime_reflection import Reader
from protocol_proof import client_proof,EXPECTED_EXE
s=json.loads((R.parent/'CPP/data/client-inspection.json').read_text())
proof=client_proof(s['pid'])
for key in ('pid','exe','sha256','process_created_filetime'):assert proof[key]==s['client_proof'][key],key
r=Reader(s['pid'],EXPECTED_EXE)
try:
    p=MovementProbe(r)
    def weak_identity(address,expected=None):
        identity=p.identity(address,expected);idx=identity['object_index']
        assert 0<=idx<p.reflection.count
        chunk=r.unpack(p.reflection.chunks+(idx//65536)*8,'<Q')[0]
        actual,flags,cluster,serial=r.unpack(chunk+(idx%65536)*24,'<Qiii')
        assert actual==address and serial>0 and not flags&0x10200000
        return {**identity,'serial':serial}
    row=next(x for x in s['network_guid_actor_matches'] if x['actor']['class']=='PlayerPawn_C')
    pawn=int(row['actor']['address'],16)
    ident=weak_identity(pawn,'PlayerCharacter')
    assert ident['object_index']==row['weak_object_index'] and ident['serial']==row['weak_object_serial']
    stats=int(p.fields(pawn,['StatsComponent'])['StatsComponent']['value']['address'],16)
    stats_identity=p.identity(stats,'AoCStatsComponent')
    cls=p.reflection.obj(stats)['class_address'];cls_identity=weak_identity(cls)
    drivers=[d for d in s['net_drivers'] if d['guid_cache']==row['guid_cache']];assert len(drivers)==1
    driver=int(drivers[0]['address'],16);p.identity(driver,'NetDriver')
    manager=r.unpack(driver+0x210,'<Q')[0]
    entries,n,cap=r.unpack(manager+8,'<Qii');assert 0<n<=cap<=256
    caches=[]
    for i in range(n):
        idx,serial,cache=r.unpack(entries+i*24,'<iiQ')
        if (idx,serial)==(cls_identity['object_index'],cls_identity['serial']):caches.append(cache)
    assert len(caches)==1 and caches[0]
    cache=caches[0];seen=set();fields=[];maximum=None
    while cache:
        assert cache not in seen and len(seen)<32;seen.add(cache)
        idx,serial=r.unpack(cache+0x10,'<ii')
        chunk=r.unpack(p.reflection.chunks+(idx//65536)*8,'<Q')[0]
        owner=r.unpack(chunk+(idx%65536)*24,'<Q')[0];identity=weak_identity(owner)
        assert (idx,serial)==(identity['object_index'],identity['serial'])
        array,n,cap=r.unpack(cache+0x20,'<Qii');base=r.unpack(cache,'<i')[0]
        assert 0<=n<=cap<=4096 and 0<=base and base+n+1<=8193
        if maximum is None:maximum=base+n+1
        props={int(x['address'],16):x for x in p.properties_for(stats).values()}
        for i in range(n):
            tagged,index,checksum,incompatible=r.unpack(array+i*24,'<QiIB')
            assert index==base+i and incompatible<=1
            if tagged&1:continue
            prop=props.get(tagged);assert prop is not None
            propowner=r.unpack(tagged+0x10,'<Q')[0]&~1;assert propowner==owner
            if prop['name'] in ('StatRepInt32Owner','StatRepInt32EveryoneProxy'):
                assert prop['type']=='StructProperty' and prop['element_size']==0x120
                struct_ptr=r.unpack(tagged+0x70,'<Q')[0];struct_identity=p.identity(struct_ptr)
                assert struct_identity['name']=='StatInt32Rep'
                start=stats+prop['offset_in_object'];data,count,capacity=r.unpack(start+0x108,'<Qii')
                assert 0<=count<=capacity<=2048
                wrapper=r.unpack(start+0x118,'<Q')[0]
                fields.append({'name':prop['name'],'field_index':index,'maximum':maximum,'metadata':prop,'struct_identity':struct_identity,'array_count':count,'array_capacity':capacity,'delegate_wrapper':p.identity(wrapper) if wrapper else None,'delta_flags':r.unpack(start+0x100,'<B')[0]})
        cache=r.unpack(cache+8,'<Q')[0]
    assert {x['name'] for x in fields}=={'StatRepInt32Owner','StatRepInt32EveryoneProxy'}
    final_proof=client_proof(s['pid'])
    for key in ('pid','exe','sha256','process_created_filetime'):assert proof[key]==final_proof[key]
    out={'proof':final_proof,'access':'read-only; no game calls/process writes','stats_identity':stats_identity,'fields':fields,'bytes_read':r.bytes_read,'limitations':['Current-session field/layout/delegate identity; does not establish new packet acceptance.']}
    (R/'proofs/resources-network-cache-live.json').write_text(json.dumps(out,indent=2))
    print(json.dumps({'proof':final_proof,'fields':[{'name':x['name'],'field_index':x['field_index'],'maximum':x['maximum'],'count':x['array_count'],'delegate_wrapper':x['delegate_wrapper']} for x in fields]},indent=2))
finally:r.close()
