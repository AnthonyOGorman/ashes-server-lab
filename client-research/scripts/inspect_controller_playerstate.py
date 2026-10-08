"""Inspect current controller PlayerState dispatch/layout, read-only."""
import json,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R.parent/'tools'))
from inspect_movement_prerequisites import MovementProbe
from dump_runtime_reflection import Reader
from protocol_proof import client_proof,EXPECTED_EXE
s=json.loads((R.parent/'CPP/data/client-inspection.json').read_text())
proof=client_proof(s['pid'])
for key in ('pid','exe','sha256','process_created_filetime'):assert proof[key]==s['client_proof'][key]
r=Reader(s['pid'],EXPECTED_EXE)
try:
    p=MovementProbe(r)
    def current(cls):
        rows=[x for x in s['network_guid_actor_matches'] if x['actor']['class']==cls]
        assert len(rows)==1
        row=rows[0];address=int(row['actor']['address'],16);ident=p.identity(address)
        assert ident['object_index']==row['weak_object_index']
        chunk=r.unpack(p.reflection.chunks+(ident['object_index']//65536)*8,'<Q')[0]
        ptr,flags,cluster,serial=r.unpack(chunk+(ident['object_index']%65536)*24,'<Qiii')
        assert ptr==address and serial==row['weak_object_serial'] and not flags&0x10200000
        return address,row
    controller,cr=current('AoCPlayerControllerBP_C')
    pawn,pr=current('PlayerPawn_C')
    state,sr=current('AoCPlayerStateBP_C')
    driver=int(next(d['address'] for d in s['net_drivers'] if d['guid_cache']==cr['guid_cache']),16)
    prop=p.property(controller,'PlayerState',0x370,8)
    cls=p.reflection.obj(controller)['class_address'];cl=p.reflection.obj(cls)
    chunk=r.unpack(p.reflection.chunks+(cl['index']//65536)*8,'<Q')[0]
    serial=r.unpack(chunk+(cl['index']%65536)*24+16,'<i')[0]
    data,count,cap=r.unpack(driver+0x5c0,'<Qii');assert 0<count<=cap<=8192
    layouts=[r.unpack(data+i*32+8,'<Q')[0] for i in range(count) if r.unpack(data+i*32,'<ii')==(cl['index'],serial)]
    assert len(layouts)==1
    layout=layouts[0];commands,n,ncap=r.unpack(layout+0x38,'<Qii');assert 0<n<=ncap<=32768
    matches=[]
    for i in range(n):
        row=commands+i*32
        if r.unpack(row,'<Q')[0]==int(prop['address'],16):
            matches.append({'command_index':i,'raw':r.read(row,32).hex(),
                'handle':r.unpack(row+0x14,'<H')[0],'type':r.unpack(row+0x1c,'<B')[0]})
    def dispatch(obj,slot):
        table=r.unpack(obj,'<Q')[0];target=r.unpack(table+slot,'<Q')[0]
        return {'slot':hex(slot),'table_rva':hex(table-r.base),'target_rva':hex(target-r.base),'bytes':r.read(target,48).hex()}
    out={'proof':proof,'access':'read-only; no game calls or writes','controller':p.identity(controller),
        'controller_playerstate':p.fields(controller,['PlayerState']),
        'pawn_playerstate':p.fields(pawn,['PlayerState']),
        'state':p.identity(state),'state_fields':p.fields(state,['Owner','PawnPrivate'],True),
        'controller_onrep_playerstate':dispatch(controller,0x888),
        'playerstate_client_initialize':dispatch(state,0x840),'rep_layout_matches':matches}
    end=client_proof(s['pid'])
    for key in ('pid','exe','sha256','process_created_filetime'):assert proof[key]==end[key]
    out['proof']=end
    (R/'proofs/controller-playerstate-live.json').write_text(json.dumps(out,indent=2))
    print(json.dumps(out,indent=2))
finally:r.close()
