"""Read the exact gravity definition flags without scanning actors or invoking client code."""
import argparse,json,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R.parent/'tools'))
from inspect_movement_prerequisites import MovementProbe
from inspect_character_stats import hash_entry
from dump_runtime_reflection import Reader,pointer
from protocol_proof import client_proof,EXPECTED_EXE
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--pid',type=int,required=True);ap.add_argument('--creation',type=int,required=True);a=ap.parse_args()
before=client_proof(a.pid);assert before['process_created_filetime']==a.creation
assert before['sha256']==json.loads((R/'index/summary.json').read_bytes())['native']['sha256']
r=Reader(a.pid,EXPECTED_EXE,budget=4*1024*1024)
try:
    p=MovementProbe(r);index,serial=r.unpack(r.base+0xd932ba0,'<ii');assert 0<=index<p.reflection.count and serial>0
    chunk=r.unpack(p.reflection.chunks+index//65536*8,'<Q')[0];item=chunk+index%65536*24
    manager,flags,cluster,actual=r.unpack(item,'<Qiii');assert actual==serial and not flags&0x10200000
    mi=p.identity(manager,'DesignDataManagerBase');mi['serial']=serial
    te=hash_entry(r,manager+0x1f0,0xb0,0x4a74ae5ed850dc97);assert te
    entry=hash_entry(r,te+8,24,0x5429e5e8643f0018);assert entry
    definition=r.unpack(entry+8,'<Q')[0];assert pointer(definition) and r.unpack(definition+8,'<Q')[0]==0x5429e5e8643f0018
    ni,nn=r.unpack(definition+0x18,'<II');name=p.reflection.names.get(ni,nn);assert name=='GravityScale'
    stat_type=r.unpack(definition+0x79,'<B')[0];assert stat_type==0
    raw=r.read(definition+0x246,2);replication,buckets=raw;assert 0<=replication<=7 and buckets in (0,1)
    profiles=hash_entry(r,manager+0x1f0,0xb0,0x6a9c0102f8f941c0);assert profiles
    pe=hash_entry(r,profiles+8,24,0x636a8ad25678);assert pe
    profile=r.unpack(pe+8,'<Q')[0];assert pointer(profile) and r.unpack(profile+8,'<Q')[0]==0x636a8ad25678
    cached,guid,typ=r.unpack(profile+0x1530,'<QQQ');assert cached==definition and guid==0x5429e5e8643f0018 and typ==0x4a74ae5ed850dc97
    assert r.unpack(item,'<Qiii')[0]==manager and r.unpack(item+16,'<i')[0]==serial and r.read(definition+0x246,2)==raw
    after=client_proof(a.pid)
    for k in ['pid','exe','sha256','process_created_filetime']:assert after[k]==before[k]
    out=dict(client_proof=after,manager=mi,definition=dict(address=hex(definition),name=name,record_id=hex(guid),type_id=hex(typ),stat_type=stat_type,replication=replication,base_equipment_buckets=buckets,raw246_248=raw.hex()),profile=dict(address=hex(profile),id='0x636a8ad25678',cached_definition_offset='0x1530',cached_definition_agrees=True),bytes_read=r.bytes_read,access='VM_READ/query only; no actor scan/calls/input/writes/packets',limits=['Record definition metadata only; current actor cache/packet acceptance and native routing remain separate.','No process addresses/identity reused across client lifetimes.'])
    dest=R/f'proofs/gravity-definition-live-{a.pid}-{a.creation}-{time.time_ns()}.json';dest.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(dict(path=str(dest),definition=out['definition'],bytes_read=r.bytes_read),indent=2))
finally:r.close()
