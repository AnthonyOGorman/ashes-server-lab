"""Read current ability grant list and existing replication layout without calls/writes."""
import json,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R.parent/'tools'))
from inspect_movement_prerequisites import MovementProbe
from dump_runtime_reflection import Reader
from protocol_proof import client_proof,EXPECTED_EXE
s=json.loads((R.parent/'CPP/data/client-inspection.json').read_text());proof=client_proof(s['pid'])
for key in ('pid','exe','sha256','process_created_filetime'):assert proof[key]==s['client_proof'][key]
r=Reader(s['pid'],EXPECTED_EXE)
try:
    p=MovementProbe(r)
    def weak_identity(address,expected=None):
        ident=p.identity(address,expected);idx=ident['object_index']
        assert 0<=idx<p.reflection.count
        chunk=r.unpack(p.reflection.chunks+(idx//65536)*8,'<Q')[0]
        actual,flags,cluster,serial=r.unpack(chunk+(idx%65536)*24,'<Qiii')
        permanent_class = ident['class']=='Class' and flags==0x42000000
        assert actual==address and (serial>0 or (serial==0 and permanent_class)), (ident,hex(actual),serial,hex(flags),hex(r.base),hex(r.image_size))
        # Preserve flags; native UClass objects may carry permanent-object flags.
        # Pointer/index/serial and owning references establish this snapshot identity.
        return {**ident,'serial':serial,'gobject_flags':hex(flags)}
    rows=[x for x in s['network_guid_actor_matches'] if x['actor']['class']=='PlayerPawn_C'];assert len(rows)==1
    row=rows[0];pawn=int(row['actor']['address'],16);ident=weak_identity(pawn,'PlayerCharacter')
    assert (ident['object_index'],ident['serial'])==(row['weak_object_index'],row['weak_object_serial'])
    ability=int(p.fields(pawn,['AbilityComponent'])['AbilityComponent']['value']['address'],16)
    ai=weak_identity(ability,'AoCAbilityComponent');cls=weak_identity(p.reflection.obj(ability)['class_address'])
    props=p.properties_for(ability);prop=p.property(ability,'KnownAbilities',0xa00,16);assert prop['type']=='ArrayProperty'
    inner=r.unpack(int(prop['address'],16)+0x78,'<Q')[0];fields=p.reflection.properties(inner);element=fields[0]
    assert element['type']=='Int64Property' and element['element_size']==8
    data,count,cap=r.unpack(ability+0xa00,'<Qii');assert 0<=count<=cap<=4096
    ids=[hex(x) for x in r.unpack(data,'<'+'Q'*count)] if count else []
    drivers=[x for x in s['net_drivers'] if x['guid_cache']==row['guid_cache']];assert len(drivers)==1
    driver=int(drivers[0]['address'],16);p.identity(driver,'NetDriver')
    entries,n,ncap=r.unpack(driver+0x5c0,'<Qii');assert 0<n<=ncap<=8192
    layouts=[r.unpack(entries+i*32+8,'<Q')[0] for i in range(n) if r.unpack(entries+i*32,'<ii')==(cls['object_index'],cls['serial'])]
    assert len(layouts)<=1
    out={'proof':proof,'access':'read-only; no game calls/process writes','pawn':ident,'ability':ai,
        'known_abilities':ids,'array_count':count,'array_capacity':cap,'property':prop,'element_property':element,
        'rep_layout_status':'present' if layouts else 'not initialized in current driver map','rep_layout':None}
    out['component_fields']=p.fields(ability,['bReplicates','bNetAddressable','OwningChar','OwnersStats'])
    table=r.unpack(ability,'<Q')[0]
    out['receive_callbacks']=[]
    for slot in (0x2a8,0x2b0):
        target=r.unpack(table+slot,'<Q')[0]
        assert r.base<=target<r.base+r.image_size
        out['receive_callbacks'].append({'slot':hex(slot),'vtable_rva':hex(table-r.base),
            'target_rva':hex(target-r.base),'prefix_bytes':r.read(target,48).hex(),
            'scope':'48-byte dispatch prefix; not complete function claim'})
    if layouts:
        layout=layouts[0];parents,np,cp=r.unpack(layout+0x28,'<Qii');cmds,nc,cc=r.unpack(layout+0x38,'<Qii')
        assert 0<np<=cp<=4096 and 0<nc<=cc<=32768
        info={'address':hex(layout),'header_hex':r.read(layout,0x50).hex(),'parents':[],'commands':[]}
        for i in range(np):
            raw=r.read(parents+i*48,48);addr=int.from_bytes(raw[:8],'little');metadata=next((x for x in props.values() if int(x['address'],16)==addr),None)
            info['parents'].append({'index':i,'raw':raw.hex(),'property':metadata})
        for i in range(nc):
            raw=r.read(cmds+i*32,32);addr=int.from_bytes(raw[:8],'little');metadata=next((x for x in props.values() if int(x['address'],16)==addr),None)
            if addr==inner:metadata=element
            info['commands'].append({'index':i,'raw':raw.hex(),'property':metadata,
                'offset':int.from_bytes(raw[12:16],'little'),'end_cmd_candidate':int.from_bytes(raw[16:20],'little'),
                'handle_candidate':int.from_bytes(raw[20:22],'little'),'parent_index':int.from_bytes(raw[22:24],'little'),'type':raw[28]})
        out['rep_layout']=info
    out['owner_at_838']=p.identity(r.unpack(ability+0x838,'<Q')[0])
    out['native_notify_owner_at_c8']=p.identity(r.unpack(ability+0xc8,'<Q')[0])
    controller=int(s['controllers'][0]['address'],16);combo=p.fields(controller,['ComboManager'])['ComboManager']['value']
    out['combo_manager']=combo
    if combo:
        ca=int(combo['address'],16);index,serial=r.unpack(ca+0x50,'<ii');out['combo_ability_weak']={'index':index,'serial':serial,'matches_ability':(index,serial)==(ai['object_index'],ai['serial'])}
    end=client_proof(s['pid'])
    for key in ('pid','exe','sha256','process_created_filetime'):assert proof[key]==end[key]
    out['proof']=end;encoded=json.dumps(out,indent=2)
    (R/f'proofs/known-abilities-live-{s["pid"]}-{proof["process_created_filetime"]}.json').write_text(encoded)
    (R/'proofs/known-abilities-live.json').write_text(encoded)
    print(json.dumps({k:v for k,v in out.items() if k not in ('property','element_property','rep_layout')},indent=2))
finally:r.close()
