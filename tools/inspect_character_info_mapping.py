"""Read-only exact GUID acceptance and native metadata for existing PlayerInfo."""
import argparse
import json
import struct
from pathlib import Path
from inspect_character_appearance import AppearanceProbe
from dump_runtime_reflection import Reader,ReadError
from protocol_proof import EXPECTED_EXE,client_proof,validate_current_client_proofs

def inspect(pid,source,actors):
    saved=json.loads(Path(source).read_text())
    actors=json.loads(Path(actors).read_text())
    validate_current_client_proofs(pid,saved,actors)
    reader=Reader(pid,EXPECTED_EXE)
    try:
        probe=AppearanceProbe(reader)
        info=saved['character_information']['identity']
        address=int(info['address'],16)
        if probe.identity(address)!=info:
            raise ReadError('Actual component identity changed')
        index=info['object_index']
        chunk=reader.unpack(probe.reflection.chunks+(index//65536)*8,'<Q')[0]
        item=reader.read(chunk+(index%65536)*24,24)
        ptr,flags=struct.unpack_from('<QI',item)
        serial=struct.unpack_from('<i',item,16)[0]
        if ptr!=address or serial<=0 or flags&0x10200000:
            raise ReadError('Live weak object identity failed')
        pawn=next(m for m in actors['network_guid_actor_matches'] if m['actor']['address']==info['outer_address'])
        cache=int(pawn['guid_cache'],16)
        data,count,capacity=reader.unpack(cache+0x10,'<Qii')
        if not 0<=count<=capacity<=100000:
            raise ReadError('GUID cache bound exceeded')
        entries=reader.read(data,count*80)
        matches=[]
        for i in range(count):
            oid,sid,rand,weak,weakserial=struct.unpack_from('<QIIii',entries,i*80)
            if weak==index and weakserial==serial and oid>1:
                matches.append({'guid':{'object_id':f'0x{oid:016x}','server_id':sid,'randomizer':rand},
                    'guid_cache':hex(cache),'weak_object_index':weak,'weak_object_serial':weakserial,
                    'component':info,'pawn_guid':pawn['guid']})
        functions=[]
        for cls,owner in probe.chain(probe.reflection.obj(address)['class_address']):
            current=reader.unpack(cls+0x68,'<Q')[0]
            seen=set()
            while current:
                if current in seen or len(seen)>=4096:
                    raise ReadError('Bounded function chain failed')
                seen.add(current)
                member=probe.reflection.obj(current)
                if member['name'].startswith('OnRep_'):
                    native=reader.unpack(current+0xf8,'<Q')[0]
                    if not reader.base<=native<reader.base+reader.image_size:
                        raise ReadError('Native receiver outside image')
                    functions.append({'name':member['name'],'owner':owner,'native_rva':hex(native-reader.base)})
                current=reader.unpack(current+0x48,'<Q')[0]
        props={}
        for name in ('CharacterGuid','CharacterName','Race','Gender','ServerId','Level'):
            prop=probe.properties_for(address)[name]
            pvt=reader.unpack(int(prop['address'],16),'<Q')[0]
            target=reader.unpack(pvt+0xc8,'<Q')[0]
            props[name]={'property':prop,'serializer_rva':hex(target-reader.base)}
            if name in ('CharacterName','ServerId','Level'):
                props[name]['serialize_item_rva']=hex(reader.unpack(pvt+0xc0,'<Q')[0]-reader.base)
        vt=reader.unpack(address,'<Q')[0]
        guid_fields={}
        for name in ('A','B','C','D'):
            prop=saved['character_information']['fields']['CharacterGuid']['fields'][name]['metadata']
            pvt=reader.unpack(int(prop['address'],16),'<Q')[0]
            guid_fields[name]={'property':prop,
                'serializer_rva':hex(reader.unpack(pvt+0xc8,'<Q')[0]-reader.base),
                'serialize_item_rva':hex(reader.unpack(pvt+0xc0,'<Q')[0]-reader.base)}
        virtuals={hex(offset):hex(reader.unpack(vt+offset,'<Q')[0]-reader.base)
            for offset in (0x560,0x570,0x5a8)}
        owner_address=reader.unpack(address+0xc8,'<Q')[0]
        owner=probe.identity(owner_address,'Actor') if owner_address else None
        return {'pid':pid,'client_proof':client_proof(pid),'functions_invoked':False,
            'component':info,'network_guid_component_matches':matches,'properties':props,
            'notification_functions':functions,'notification_virtuals':virtuals,'cached_actor_owner':owner,
            'guid_fields':guid_fields,
            'completed_client_proof':client_proof(pid)}
    finally:reader.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid',type=int,required=True)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--actors',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    d=inspect(a.pid,a.source,a.actors)
    a.output.write_text(json.dumps(d,indent=2))
    print(json.dumps({'matches':d['network_guid_component_matches'],'functions':d['notification_functions'],
        'serializers':{k:{a:b for a,b in v.items() if a.endswith('_rva')} for k,v in d['properties'].items()},
        'virtuals':d['notification_virtuals'],'cached_owner':d['cached_actor_owner']},indent=2))
