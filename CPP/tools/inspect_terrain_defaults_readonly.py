"""Verify inherited landscape collision defaults for the exact installed client.

Reads native class default objects only; no game functions or writes, and no
terrain traversal. Archive instances can omit values equal to these defaults.
"""
import sys,pathlib,json
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'tools'))
from dump_runtime_reflection import Reader,Reflection,ReadError,pointer,validate_sdk,SDK,OFFSETS
from protocol_proof import EXPECTED_EXE,client_proof

pid=int(sys.argv[1]);proof=client_proof(pid);validate_sdk(SDK)
r=Reader(pid,EXPECTED_EXE)
try:
    f=Reflection(r,1_000_000);classes={}
    for addr,obj in f.objects():
        if f.class_name(obj['class_address']) in ('Class','ScriptStruct'):
            classes[obj['name']]=addr
    def property_named(owner,name):
        visited=set()
        for _ in range(32):
            if not pointer(owner) or owner in visited:break
            visited.add(owner);head=r.unpack(owner+0x70,'<Q')[0];size=r.unpack(owner+0x78,'<i')[0]
            for p in f.properties(head,size):
                if p['name']==name:return p
            owner=r.unpack(owner+0x60,'<Q')[0]
        raise ReadError('Missing reflected field '+name)
    records=[]
    for name in ('Landscape','LandscapeStreamingProxy'):
        cls=classes[name];default=r.unpack(cls+OFFSETS['UClass']['default_object'],'<Q')[0];obj=f.obj(default)
        if obj['class_address']!=cls or not int(obj['flags'],16)&0x10:raise ReadError('Landscape class default identity')
        actor=property_named(cls,'bActorEnableCollision');layout=actor['bool_layout'];actor_enabled=bool(r.read(default+actor['offset_in_object']+layout['byte_offset'],1)[0]&layout['field_mask'])
        body=property_named(cls,'BodyInstance');body_addr=default+body['offset_in_object']
        enabled=property_named(classes['BodyInstance'],'CollisionEnabled');enabled_value=r.read(body_addr+enabled['offset_in_object'],1)[0]
        profile=property_named(classes['BodyInstance'],'CollisionProfileName');profile_name=f.names.get(*r.unpack(body_addr+profile['offset_in_object'],'<II'))
        records.append({'class':name,'default_identity':obj,'actor_enabled':actor_enabled,'collision_enabled_value':enabled_value,'collision_profile':profile_name,'body_offset':body['offset_in_object'],'enabled_offset':enabled['offset_in_object'],'profile_offset':profile['offset_in_object']})
    out=pathlib.Path(__file__).resolve().parents[1]/'data/terrain-offline/collision-defaults.json'
    result={'proof':proof,'records':records,'bytes_read':r.bytes_read,'scope':'read-only native landscape class defaults; no terrain actor visits'}
    out.write_text(json.dumps(result,indent=2));print(json.dumps({'records':records,'bytes_read':r.bytes_read}))
finally:r.close()
