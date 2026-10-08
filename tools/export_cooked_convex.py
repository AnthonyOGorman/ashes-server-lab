"""Read and validate cooked convex vertices/planes without activating a profile.

The source identities must still match the running client. Output is separate
from the active collision export until its shape linkage is independently proven.
"""
import argparse
import json
import math
from pathlib import Path
import struct
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from lab.static_collision import validate_cooked_surface
from lab.capsule_sweep import dot, sub
from dump_runtime_reflection import Reader, ReadError, pointer
from export_static_collision import CollisionProbe
from protocol_proof import EXPECTED_EXE, client_proof
from reconstruct_cooked_support import support_surface


def validated_surface(vertices, planes):
    """Triangulate cooked vertices only if every face agrees with native planes."""
    from scipy.spatial import ConvexHull, QhullError
    if not 4<=len(vertices)<=4096 or not 4<=len(planes)<=4096:
        raise ValueError('bounded cooked convex geometry required')
    if any(len(v)!=3 or not all(math.isfinite(x) for x in v) for v in vertices):
        raise ValueError('finite cooked vertices required')
    for plane in planes:
        if len(plane)!=6 or not all(math.isfinite(x) for x in plane):
            raise ValueError('finite native point-normal plane required')
        normal=plane[3:]
        if abs(dot(normal,normal)-1)>.0001:
            raise ValueError('unit native plane normal required')
        if max(dot(normal,sub(v,plane[:3])) for v in vertices)>.002:
            raise ValueError('cooked vertex outside native supporting plane')
    try:
        hull=ConvexHull(vertices)
    except QhullError as exc:
        raise ValueError('nondegenerate cooked convex hull required') from exc
    indices=[int(i) for face in hull.simplices for i in face]
    validate_cooked_surface(vertices,indices,planes)
    return indices


def read_geometry(reader, element):
    # FKConvexElem destructor releases the owned intrusive pointer at +f0.
    # Pin both that ownership accessor and the cooked closest-face query.
    for rva,code in ((0x4361400+0x13,'488b89f0000000'),
                     (0x2100ba0+0xd0,'4c8b6620'),
                     (0x2100ba0+0x1b1,'488b4630'),
                     (0x2100ba0+0x2b9,'4983c718')):
        raw=bytes.fromhex(code)
        if reader.read(reader.base+rva,len(raw))!=raw:
            raise ReadError('exact native cooked convex layout required')
    geometry=reader.unpack(element+240,'<Q')[0]
    if not pointer(geometry) or reader.unpack(geometry,'<Q')[0]-reader.base!=0x9fac6e0:
        raise ReadError('matching cooked convex vtable required')
    buffers=[]
    for offset,stride in ((0x30,12),(0x20,24)):
        ptr,n,cap=reader.unpack(geometry+offset,'<Qii')
        if not pointer(ptr) or not 4<=n<=cap<=4096:
            raise ReadError('bounded cooked array required')
        buffers.append([list(v) for v in struct.iter_unpack(
            '<3f' if stride==12 else '<6f',reader.read(ptr,n*stride))])
    vertices,planes=buffers
    layout='native-chaos-convex-v1'
    try:
        indices=validated_surface(vertices,planes)
    except ValueError:
        # Rounded native query RVA20f7820 selects support over every cooked
        # float vertex. Pin its count, pointer and 12-byte loop stride.
        for rva,code in ((0x20f7820+0xf5,'49634538'),
                         (0x20f7820+0x202,'4d8b5530'),
                         (0x20f7820+0x245,'4883c10c')):
            raw=bytes.fromhex(code)
            if reader.read(reader.base+rva,len(raw))!=raw:
                raise ReadError('exact native vertex support query required')
        indices=support_surface(vertices)
        layout='native-chaos-support-v1'
    if reader.unpack(element+240,'<Q')[0]!=geometry:
        raise ReadError('cooked geometry changed during export')
    return {'layout':layout,'geometry':hex(geometry),
            'vertices':vertices,'planes':planes,'indices':indices}


def export(pid, source):
    current=client_proof(pid);snapshot=json.loads(source.read_text())
    if any(current[k]!=snapshot['client_proof'][k] for k in
           ('pid','exe','sha256','process_created_filetime')):
        raise ValueError('same running source client required')
    result={'pid':pid,'client_proof':current,'source':str(source),'shapes':[],
            'errors':[],'scope':'native cooked layout research; not activated collision'}
    reader=Reader(pid,EXPECTED_EXE)
    try:
        probe=CollisionProbe(reader)
        # Native closest-face query uses point xyz followed by normal xyz,
        # 24-byte planes at +20, and float xyz vertices at +30.
        checks=((0x2100ba0+0xd0,'4c8b6620'),
                (0x2100ba0+0x1b1,'488b4630'),
                (0x2100ba0+0x2b9,'4983c718'))
        for rva,code in checks:
            raw=bytes.fromhex(code)
            if reader.read(reader.base+rva,len(raw))!=raw:
                raise ReadError('exact native cooked convex query required')
        for asset in snapshot['assets'].values():
            mesh=asset['mesh'];address=int(mesh['address'],16)
            if probe.p.identity(address)!=mesh:
                raise ReadError('mesh identity changed since source export')
            body=int(probe.p.fields(address,['BodySetup'])['BodySetup']['value']['address'],16)
            aggregate=probe.p.properties_for(body)['AggGeom']
            field=probe.struct_fields(aggregate)['ConvexElems']
            data,count,item=probe.array(body+aggregate['offset_in_object'],field,4096)
            if item['element_size']!=256:
                raise ReadError('exact native convex element size required')
            for index in range(count):
                try:
                    element=data+256*index
                    geometry=reader.unpack(element+240,'<Q')[0]
                    if not pointer(geometry) or reader.unpack(geometry,'<Q')[0]-reader.base!=0x9fac6e0:
                        raise ReadError('matching cooked convex vtable required')
                    buffers=[]
                    for offset,stride,minimum in ((0x30,12,4),(0x20,24,4)):
                        ptr,n,cap=reader.unpack(geometry+offset,'<Qii')
                        if not pointer(ptr) or not minimum<=n<=cap<=4096:
                            raise ReadError('bounded cooked array required')
                        buffers.append([list(v) for v in struct.iter_unpack(
                            '<3f' if stride==12 else '<6f',reader.read(ptr,n*stride))])
                    vertices,planes=buffers
                    shape={'mesh':mesh,'index':index,'element':hex(element),
                           'geometry':hex(geometry),'vertices':vertices,'planes':planes}
                    try:
                        shape['indices']=validated_surface(vertices,planes)
                        shape['surface_verified']=True
                    except ValueError as exc:
                        shape.update(surface_verified=False,reason=str(exc))
                    result['shapes'].append(shape)
                except ReadError as exc:
                    result['errors'].append({'mesh':mesh,'index':index,'reason':str(exc)})
        result['completed_client_proof']=client_proof(pid)
        return result
    finally:
        reader.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid',type=int,required=True)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=export(args.pid,args.source)
    args.output.write_text(json.dumps(result,indent=2))
    print(json.dumps({'shapes':len(result['shapes']),
        'verified':sum(s['surface_verified'] for s in result['shapes']),
        'errors':result['errors'],'rejections':[s['reason'] for s in result['shapes']
                                              if not s['surface_verified']][:8]}))
