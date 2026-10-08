"""Inventory reflected simple mesh collision; no world bounds used as geometry."""
import argparse
import json
from pathlib import Path
from collections import Counter
from dump_runtime_reflection import Reader, ReadError, pointer
from inspect_movement_prerequisites import MovementProbe
from protocol_proof import EXPECTED_EXE, client_proof


def inspect(pid):
    reader=Reader(pid,EXPECTED_EXE)
    result={'client_proof':client_proof(pid),'access':'read-only',
            'mesh_components':0,'assets':[],'errors':[],
            'scope':'resident component/asset inventory; world transforms and complex triangles not exported'}
    try:
        probe=MovementProbe(reader);seen=set();counts=Counter()
        for address,obj in probe.reflection.objects():
            chain=[name for _,name in probe.chain(obj['class_address'])]
            if 'StaticMeshComponent' not in chain or obj['name'].startswith(('Default__','GEN_VARIABLE')):
                continue
            result['mesh_components']+=1
            try:
                mesh=probe.fields(address,['StaticMesh'])['StaticMesh'].get('value')
                if not mesh or mesh['address'] in seen:continue
                seen.add(mesh['address'])
                if len(result['assets'])>=256:continue
                mesh_address=int(mesh['address'],16)
                body=probe.fields(mesh_address,['BodySetup'])['BodySetup'].get('value')
                if not body:continue
                body_address=int(body['address'],16)
                prop=probe.properties_for(body_address).get('AggGeom')
                if not prop or (prop['type'],prop.get('referenced_type'))!=('StructProperty','KAggregateGeom'):
                    raise ReadError('reflected KAggregateGeom required')
                struct=reader.unpack(int(prop['address'],16)+0x70,'<Q')[0]
                head=reader.unpack(struct+0x70,'<Q')[0]
                size=reader.unpack(struct+0x78,'<i')[0]
                if size!=prop['element_size']:raise ReadError('aggregate struct size mismatch')
                shapes=[]
                for field in probe.reflection.properties(head,size):
                    if field['type']!='ArrayProperty':continue
                    if field['element_size']!=16:raise ReadError('TArray header size mismatch')
                    data,count,capacity=reader.unpack(body_address+prop['offset_in_object']+field['offset_in_object'],'<Qii')
                    if not 0<=count<=capacity<=4096 or count and not pointer(data):
                        raise ReadError('bounded shape array required')
                    # Exact SDK FArrayProperty.InnerProperty follows8 bytes
                    # of padding; offset0x70 is not the inner-property pointer.
                    inner=reader.unpack(int(field['address'],16)+0x78,'<Q')[0]
                    if not pointer(inner):raise ReadError('valid reflected inner property required')
                    item=probe.reflection.properties(inner)[0]
                    if item['type']!='StructProperty':raise ReadError('shape struct item required')
                    counts[field['name']]+=count
                    shapes.append({'name':field['name'],'count':count,'capacity':capacity,
                        'data_address':hex(data),'item_type':item.get('referenced_type'),
                        'item_size':item['element_size'],'field':field})
                result['assets'].append({'mesh':mesh,'body':body,
                    'component_example':probe.identity(address),'aggregate_property':prop,
                    'body_fields':probe.fields(body_address,['CollisionTraceFlag','bMeshCollideAll']),
                    'shapes':shapes})
            except (ReadError,KeyError,IndexError) as exc:
                result['errors'].append({'component':hex(address),'reason':str(exc)})
        result['shape_counts']=dict(counts);result['distinct_mesh_references']=len(seen)
        return result
    finally:
        reader.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid',type=int,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=inspect(args.pid)
    args.output.write_text(json.dumps(result,indent=2))
    print(json.dumps({key:result[key] for key in ('mesh_components','distinct_mesh_references','shape_counts')}))
    print(json.dumps({'assets':len(result['assets']),'errors':len(result['errors'])}))
