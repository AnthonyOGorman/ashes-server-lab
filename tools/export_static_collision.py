"""Read nearby native mesh collision shapes and component/instance transforms.

Raw instance matrices are retained. World positions used for inventory culling
are not a claim that collision response or sweeps have been implemented.
"""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import struct
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from dump_runtime_reflection import Reader, ReadError, pointer
from inspect_movement_prerequisites import MovementProbe
from protocol_proof import EXPECTED_EXE, client_proof

ACCESSOR=bytes.fromhex('0f288130020000488bc20f2889400200000f29020f2881500200000f294a100f2889600200000f2942200f2881700200000f294a300f2889800200000f2942400f294a50c3')
COLLISION_ACCESSOR=bytes.fromhex('488b81c80000004885c0740cf680dd00000004750333c0c30fb681df030000c3')
RESPONSE_ACCESSOR=bytes.fromhex('4863c20fb6840830040000c3')


def instance_transform_proof(reader,prop):
    # Reflected GetInstanceTransform exec RVA3ae6ca0 calls RVA408de90.
    # It bounds the index by +688, uses +680 with128-byte stride, and builds
    # an FTransform from the double matrix. Translation comes from +60/+70.
    if prop['offset_in_object']!=0x680:
        raise ReadError('exact native instance array offset required')
    for rva,code in ((0x408ded6,'4863d248c1e20748039180060000'),
                     (0x408dee8,'e8536e3bfd'),
                     (0x1445106,'660f104760f20f104f70'),
                     (0x408dfda,'440f109730020000'),
                     (0x408e169,'0f109750020000')):
        raw=bytes.fromhex(code)
        if reader.read(reader.base+rva,len(raw))!=raw:
            raise ReadError('exact native instance transform conversion required')
    return 'native-uniform-instance-transform-v1'


def transform_values(raw):
    values=struct.unpack('<12d',raw)
    q=values[:4];position=values[4:7];scale=values[8:11]
    if not all(math.isfinite(v) for v in (*q,*position,*scale)):
        raise ReadError('finite native transform required')
    if abs(sum(v*v for v in q)-1)>1e-5 or min(map(abs,scale))<1e-8:
        raise ReadError('unit quaternion and nonzero scale required')
    return {'rotation':list(q),'translation':list(position),'scale':list(scale)}


def transform_point(transform, point):
    q=transform['rotation'];v=[point[i]*transform['scale'][i] for i in range(3)]
    x,y,z,w=q
    uv=[y*v[2]-z*v[1],z*v[0]-x*v[2],x*v[1]-y*v[0]]
    uuv=[y*uv[2]-z*uv[1],z*uv[0]-x*uv[2],x*uv[1]-y*uv[0]]
    return [v[i]+2*(w*uv[i]+uuv[i])+transform['translation'][i] for i in range(3)]


class CollisionProbe:
    def __init__(self, reader):
        self.r=reader;self.p=MovementProbe(reader);self.struct_cache={};self.world_cache={}
        if reader.read(reader.base+0x446fec0,len(COLLISION_ACCESSOR))!=COLLISION_ACCESSOR:
            raise ReadError('exact native collision getter required')
        if reader.read(reader.base+0x446ff00,len(RESPONSE_ACCESSOR))!=RESPONSE_ACCESSOR:
            raise ReadError('exact native collision response getter required')

    def struct_fields(self, prop):
        if prop['type']!='StructProperty':raise ReadError('struct property required')
        addr=self.r.unpack(int(prop['address'],16)+0x70,'<Q')[0]
        if addr not in self.struct_cache:
            props={};seen=set();current=addr
            while current:
                if current in seen or len(seen)>16:raise ReadError('bounded struct ancestry required')
                seen.add(current)
                head=self.r.unpack(current+0x70,'<Q')[0];size=self.r.unpack(current+0x78,'<i')[0]
                for f in self.p.reflection.properties(head,size):props.setdefault(f['name'],f)
                current=self.r.unpack(current+0x60,'<Q')[0]
            self.struct_cache[addr]=props
        return self.struct_cache[addr]

    def field(self, base, prop):
        value=self.p.decode(base,prop)
        if value['status']=='read' and 'value' in value:return value['value']
        if prop['type']=='StructProperty' and prop.get('referenced_type')=='Rotator' and prop['element_size']==24:
            return list(self.r.unpack(base+prop['offset_in_object'],'<ddd'))
        if prop['type']=='StructProperty' and prop.get('referenced_type')=='Transform' and prop['element_size']==96:
            return transform_values(self.r.read(base+prop['offset_in_object'],96))
        raise ReadError('unsupported shape field '+prop['name'])

    def array(self, base, prop, maximum):
        if prop['type']!='ArrayProperty' or prop['element_size']!=16:
            raise ReadError('reflected array required')
        data,count,capacity=self.r.unpack(base+prop['offset_in_object'],'<Qii')
        if not 0<=count<=capacity<=maximum or count and not pointer(data):
            raise ReadError('bounded array required for '+prop['name'])
        inner=self.r.unpack(int(prop['address'],16)+0x78,'<Q')[0]
        if not pointer(inner):raise ReadError('array inner property required')
        fields=self.p.reflection.properties(inner)
        if not fields:raise ReadError('array item metadata required')
        return data,count,fields[0]

    def world(self, addr):
        if addr in self.world_cache:return self.world_cache[addr]
        seen=[];current=addr;world=None
        while current:
            if current in self.world_cache:
                world=self.world_cache[current];break
            if current in seen or len(seen)>16:raise ReadError('bounded outer chain required')
            seen.append(current);obj=self.p.reflection.obj(current)
            class_name=self.p.reflection.class_name(obj['class_address'])
            if class_name=='Level':
                # A streamed level's package has its own World outer. Runtime
                # ownership is the reflected Level.OwningWorld, which points
                # back to the gameplay world after the level is attached.
                owning=self.p.fields(current,['OwningWorld'])['OwningWorld']
                if owning['status']!='read':
                    raise ReadError('reflected level runtime ownership required')
                value=owning.get('value')
                if value:
                    world=int(value['address'],16)
                    self.p.identity(world,'World')
                break
            if class_name=='World':
                world=current;break
            current=obj['outer_address']
        for item in seen:self.world_cache[item]=world
        return world

    def response(self, component):
        table=self.r.unpack(component,'<Q')[0]
        if (self.r.unpack(table+0x648,'<Q')[0]!=self.r.base+0x446fec0 or
                self.r.unpack(table+0x650,'<Q')[0]!=self.r.base+0x446ff00):
            raise ReadError('unreviewed collision getter override')
        prop=self.p.properties_for(component)['BodyInstance']
        body=component+prop['offset_in_object'];fields=self.struct_fields(prop)
        enabled=self.field(body,fields['CollisionEnabled'])
        if body+fields['CollisionEnabled']['offset_in_object']!=component+0x3df:
            raise ReadError('native collision getter must match reflected body field')
        owner_address=self.r.unpack(component+0xc8,'<Q')[0]
        owner=self.p.identity(owner_address,'Actor') if owner_address else None
        owner_enabled=True
        if owner:
            flag=self.p.properties_for(owner_address)['bActorEnableCollision']
            if flag['offset_in_object']!=0xdd or flag['bool_layout']['field_mask']!=4:
                raise ReadError('native owner collision predicate must match reflection')
            owner_enabled=self.field(owner_address,flag)
        responses=fields['CollisionResponses'];response_base=body+responses['offset_in_object']
        channel=self.struct_fields(responses)['ResponseToChannels']
        channels=self.struct_fields(channel)
        pawn=self.field(response_base+channel['offset_in_object'],channels['Pawn'])
        if response_base+channel['offset_in_object']+channels['Pawn']['offset_in_object']!=component+0x432:
            raise ReadError('native Pawn-channel getter must match reflection')
        return {'collision_enabled':enabled if owner_enabled else 0,'pawn_response':pawn,
                'component_collision_enabled':enabled,'owner':owner,'owner_collision_enabled':owner_enabled,
                'body_property':prop,'enabled_property':fields['CollisionEnabled'],
                'pawn_response_property':channels['Pawn']}

    def asset(self, mesh):
        body=self.p.fields(mesh,['BodySetup'])['BodySetup'].get('value')
        if not body:return None
        address=int(body['address'],16);prop=self.p.properties_for(address)['AggGeom']
        aggregate=address+prop['offset_in_object'];out=[]
        for name,field in self.struct_fields(prop).items():
            if field['type']!='ArrayProperty':continue
            data,count,inner=self.array(aggregate,field,4096)
            if not count:continue
            if inner['type']!='StructProperty':raise ReadError('shape struct required')
            fields=self.struct_fields(inner)
            for index in range(count):
                base=data+index*inner['element_size']
                shape={'type':inner.get('referenced_type'),'index':index,
                       'array':name,'item_size':inner['element_size']}
                for key in ('Center','Rotation','Radius','Length','X','Y','Z','CollisionEnabled','Transform'):
                    if key in fields:shape[key]=self.field(base,fields[key])
                for key in ('VertexData','IndexData'):
                    if key not in fields:continue
                    ptr,n,item=self.array(base,fields[key],65536)
                    expected=('StructProperty',24) if key=='VertexData' else ('IntProperty',4)
                    if (item['type'],item['element_size'])!=expected:
                        raise ReadError('exact convex item layout required')
                    raw=self.r.read(ptr,n*item['element_size']) if n else b''
                    shape[key]=[list(v) if key=='VertexData' else v[0]
                        for v in struct.iter_unpack('<ddd' if key=='VertexData' else '<i',raw)]
                if shape['type']=='KConvexElem':
                    from lab.static_collision import ConvexCollision
                    try:
                        ConvexCollision(shape['VertexData'],shape['IndexData'])
                    except ValueError:
                        from export_cooked_convex import read_geometry
                        try:
                            if inner['element_size']!=256:
                                raise ReadError('exact native convex element size required')
                            shape['CookedGeometry']=read_geometry(self.r,base)
                        except (ReadError,ValueError) as exc:
                            shape['CookedGeometryError']=str(exc)
                out.append(shape)
        result={'mesh':self.p.identity(mesh),'body':body,'shapes':out,
                'collision_trace_flag':self.p.fields(address,['CollisionTraceFlag'])['CollisionTraceFlag'].get('value')}
        if result['collision_trace_flag']==3:
            from export_cooked_triangles import read_geometry
            try:result['CookedTriangles']=read_geometry(self.r,address)
            except (ReadError,ValueError) as exc:result['CookedTrianglesError']=str(exc)
        return result


def export(pid, pawn, centre, radius):
    reader=Reader(pid,EXPECTED_EXE,budget=768*1024*1024)
    result={'pid':pid,'client_proof':client_proof(pid),'centre':centre,'radius':radius,
            'components':[],'assets':{},'counts':{},'errors':[],'nearest_blocking_components':[],
            'scope':'nearby simple mesh shapes and raw instance matrices; no complex triangles or sweep proof'}
    try:
        probe=CollisionProbe(reader)
        if reader.read(reader.base+0x3e9bba0,len(ACCESSOR))!=ACCESSOR:
            raise ReadError('exact native ComponentToWorld copy accessor required')
        identity=probe.p.identity(pawn,'PlayerPawn_C');world=probe.world(pawn)
        result['pawn']=identity;result['world']=probe.p.identity(world)
        counts=Counter();assets={}
        for address,obj in probe.p.reflection.objects():
            chain=[n for _,n in probe.p.chain(obj['class_address'])]
            if 'StaticMeshComponent' not in chain or obj['name'].startswith(('Default__','GEN_VARIABLE')):continue
            counts['resident_mesh_components']+=1
            if probe.world(address)!=world:continue
            counts['current_world_mesh_components']+=1
            try:
                props=probe.p.properties_for(address)
                if not probe.field(address,props['bComponentToWorldUpdated']):
                    counts['transform_not_updated']+=1;continue
                transform=transform_values(reader.read(address+0x230,96))
                response=probe.response(address)
                if response['collision_enabled'] not in (1,3,5) or response['pawn_response']!=2:
                    counts['nonblocking_components']+=1;continue
                instances=[]
                if 'InstancedStaticMeshComponent' in chain:
                    data,n,item=probe.array(address,props['PerInstanceSMData'],200000)
                    if item.get('referenced_type')!='InstancedStaticMeshInstanceData' or item['element_size']!=128:
                        raise ReadError('native128-byte instance matrix required')
                    for start in range(0,n,8192):
                        raw=reader.read(data+128*start,min(8192,n-start)*128)
                        for offset,m in enumerate(struct.iter_unpack('<16d',raw)):
                            if not all(math.isfinite(v) for v in m):raise ReadError('finite instance matrix required')
                            position=transform_point(transform,m[12:15])
                            if radius is None or math.dist(position[:2],centre[:2])<=radius:
                                instances.append({'index':start+offset,'matrix':list(m),'position_candidate':position})
                    counts['instances_scanned']+=n
                    if not instances:continue
                else:
                    distance=math.dist(transform['translation'][:2],centre[:2])
                    nearest=result['nearest_blocking_components']
                    if len(nearest)<20 or distance<nearest[-1]['distance']:
                        nearest.append({'identity':probe.p.identity(address),'position':transform['translation'],
                                        'distance':distance})
                        nearest.sort(key=lambda v:v['distance']);del nearest[20:]
                    if radius is not None and distance>radius:continue
                mesh=probe.p.fields(address,['StaticMesh'])['StaticMesh'].get('value')
                if not mesh:continue
                if mesh['address'] not in assets:assets[mesh['address']]=probe.asset(int(mesh['address'],16))
                asset=assets[mesh['address']]
                if not asset:continue
                result['assets'][mesh['address']]=asset
                result['components'].append({'identity':probe.p.identity(address),'asset':mesh['address'],
                    'mobility':probe.field(address,props['Mobility']),
                    'native_component_transform':transform,'instances':instances,'response':response})
                if instances:
                    result['components'][-1]['instance_transform_proof']=instance_transform_proof(reader,props['PerInstanceSMData'])
            except (ReadError,KeyError) as exc:
                if len(result['errors'])<256:result['errors'].append({'component':hex(address),'reason':str(exc)})
                counts['read_errors']+=1
        if probe.p.identity(pawn,'PlayerPawn_C')!=identity:raise ReadError('pawn identity changed during export')
        result['counts']=dict(counts);result['bytes_read']=reader.bytes_read
        result['completed_client_proof']=client_proof(pid)
        return result
    finally:
        reader.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid',type=int,required=True)
    parser.add_argument('--pawn',type=lambda v:int(v,0),required=True)
    parser.add_argument('--centre',type=float,nargs=3,required=True)
    parser.add_argument('--radius',type=float,default=5000.)
    parser.add_argument('--all-loaded',action='store_true',help='Export enabled collision from every resident current-world component')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not 0<args.radius<=100000:parser.error('radius must be positive and at most100000cm')
    result=export(args.pid,args.pawn,args.centre,None if args.all_loaded else args.radius)
    args.output.write_text(json.dumps(result,indent=2))
    print(json.dumps({'components':len(result['components']),'assets':len(result['assets']),
        'counts':result['counts'],'errors':result['errors'][:3]}))
