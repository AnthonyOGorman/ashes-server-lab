"""Small build/lifetime/weak-bound loading config read; no calls, writes or input."""
import hashlib,json,math,struct,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R.parent/'tools'))
from inspect_movement_prerequisites import MovementProbe
from inspect_character_stats import hash_entry
from dump_runtime_reflection import Reader,pointer
from protocol_proof import client_proof,EXPECTED_EXE
s=json.loads((R.parent/'CPP/data/client-inspection.json').read_bytes());proof=client_proof(s['pid'])
for k in ['pid','exe','sha256','process_created_filetime']:assert proof[k]==s['client_proof'][k]
assert proof['pid']==579760 and proof['process_created_filetime']==134358951827478205
r=Reader(proof['pid'],EXPECTED_EXE,budget=4*1024*1024)
try:
    p=MovementProbe(r)
    def identity(address,expected=None,positive=True):
        ident=p.identity(address,expected);i=ident['object_index'];assert 0<=i<p.reflection.count
        chunk=r.unpack(p.reflection.chunks+i//65536*8,'<Q')[0]
        actual,flags,cluster,serial=r.unpack(chunk+i%65536*24,'<Qiii');assert actual==address and not flags&0x10200000
        if positive:assert serial>0
        return dict(ident,serial=serial,flags=hex(flags))
    assert r.read(r.base+0x5be9527,7).hex()=='488b05222cd107'
    klass=r.unpack(r.base+0xd8fc150,'<Q')[0];assert pointer(klass)
    ki=identity(klass,'Class',False);assert ki['name']=='AoCRecordConstants',ki
    cdo=r.unpack(klass+0x150,'<Q')[0];ci=identity(cdo,'AoCRecordConstants',False)
    assert ci['name']=='Default__AoCRecordConstants'
    prop=p.property(cdo,'LoadingScreenDataId',0x610,56);assert prop['type']=='StructProperty' and prop['referenced_type']=='LoadingScreenDataId'
    record_id=r.unpack(cdo+0x610,'<Q')[0];assert record_id
    index,serial=r.unpack(r.base+0xd932ba0,'<ii');assert 0<=index<p.reflection.count and serial>0
    chunk=r.unpack(p.reflection.chunks+index//65536*8,'<Q')[0]
    manager,flags,cluster,actual_serial=r.unpack(chunk+index%65536*24,'<Qiii');assert actual_serial==serial and not flags&0x10200000
    mi=identity(manager,'DesignDataManagerBase');assert mi['serial']==serial
    type_entry=hash_entry(r,manager+0x1f0,0xb0,0x1fe2a2ecef1be39);assert type_entry
    entry=hash_entry(r,type_entry+8,24,record_id);assert entry
    record=r.unpack(entry+8,'<Q')[0];assert pointer(record) and r.unpack(record+8,'<Q')[0]==record_id
    ni,nn=r.unpack(record+0x18,'<II');name=p.reflection.names.get(ni,nn)
    raw=r.read(record+0x88,16);hold,hang,heartbeat,*flags_=struct.unpack('<3f4B',raw)
    assert all(math.isfinite(x) and 0<=x<=3600 for x in [hold,hang,heartbeat])
    def entries(base):
        data,n,cap=r.unpack(base,'<Qii');free=r.unpack(base+0x34,'<i')[0];bn=r.unpack(base+0x48,'<i')[0]
        assert pointer(data) and 0<=free<=n<=cap<=64 and 0<bn<=128 and not bn&(bn-1)
        buckets=r.unpack(base+0x40,'<Q')[0] or base+0x38;seen=set();result=[]
        for at in r.unpack(buckets,'<'+'i'*bn):
            while at!=-1:
                assert 0<=at<n and at not in seen;seen.add(at);a=data+at*24;result.append(a);at=r.unpack(a+16,'<i')[0]
        assert len(seen)==n-free;return result
    alternatives=[]
    for at in entries(type_entry+8):
        rid,addr=r.unpack(at,'<QQ');assert pointer(addr) and r.unpack(addr+8,'<Q')[0]==rid
        ni,nn=r.unpack(addr+0x18,'<II');seconds=r.unpack(addr+0x88,'<f')[0]
        assert math.isfinite(seconds) and 0<=seconds<=3600
        alternatives.append(dict(record_id=hex(rid),name=p.reflection.names.get(ni,nn),hold_seconds=seconds))
    end=client_proof(proof['pid'])
    for k in ['pid','exe','sha256','process_created_filetime']:assert end[k]==proof[k]
    assert identity(manager)['serial']==mi['serial'] and r.unpack(klass+0x150,'<Q')[0]==cdo
    assert r.unpack(cdo+0x610,'<Q')[0]==record_id and r.read(record+0x88,16)==raw
    out=dict(proof=end,access='VM_READ/query only; no calls/input/writes/packets/CPPchanges',manager=mi,
        settings_class=ki,settings_cdo=ci,settings_property=prop,selected_loading_record=dict(type_id='0x1fe2a2ecef1be39',record_id=hex(record_id),address=hex(record),name=name,
            hold_seconds=hold,hang_seconds=hang,heartbeat_seconds=heartbeat,force_flags=flags_,raw88_98=raw.hex()),
        loaded_alternatives=alternatives,bytes_read=r.bytes_read,
        limits=['Definition readback only; timer start/actual overlay hide/streaming prerequisites require independent observation.',
          'CDO/class may have zero native serial; exact class global/name/CDO ownership validated; design manager positive weak serial required.',
          'LoadingScreenHoldSeconds is an Edit-only design-data record field, not a direct Config property.'])
    dest=R/f'proofs/loading-hold-live-{proof["pid"]}-{proof["process_created_filetime"]}-{time.time_ns()}.json'
    dest.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(dict(path=str(dest),record=out['selected_loading_record'],alternatives=alternatives,bytes_read=r.bytes_read),indent=2))
finally:r.close()
