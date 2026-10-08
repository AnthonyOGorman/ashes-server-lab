"""Decode exact native cooked triangle buffers read-only; never activate collision."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import struct

try:
    from .dump_runtime_reflection import Reader,ReadError,pointer
    from .export_static_collision import CollisionProbe
    from .protocol_proof import EXPECTED_EXE,client_proof
except ImportError:
    from dump_runtime_reflection import Reader,ReadError,pointer
    from export_static_collision import CollisionProbe
    from protocol_proof import EXPECTED_EXE,client_proof


def validate_buffers(vertices,triangles,bounds):
    if not 3<=len(vertices)<=500000 or not 1<=len(triangles)<=500000:
        raise ValueError('bounded native triangle buffers required')
    if any(len(v)!=3 or not all(math.isfinite(x) for x in v) for v in vertices):
        raise ValueError('finite native triangle vertices required')
    if len(bounds)!=6 or not all(math.isfinite(v) for v in bounds):
        raise ValueError('finite native triangle bounds required')
    actual=[min(v[i] for v in vertices) for i in range(3)]+[max(v[i] for v in vertices) for i in range(3)]
    if any(abs(a-b)>.01 for a,b in zip(actual,bounds)):
        raise ValueError('native bounds disagree with decoded vertices')
    edges=Counter();directed=Counter();degenerate=0
    for triangle in triangles:
        if len(triangle)!=3 or any(type(i) is not int or not 0<=i<len(vertices) for i in triangle):
            raise ValueError('native triangle index outside vertex buffer')
        a,b,c=[vertices[i] for i in triangle]
        u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
        cross=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        if sum(x*x for x in cross)<1e-18:degenerate+=1
        for i in range(3):
            edge=(triangle[i],triangle[(i+1)%3]);directed[edge]+=1;edges[tuple(sorted(edge))]+=1
    return {'vertices':len(vertices),'triangles':len(triangles),'degenerate_triangles':degenerate,
        'boundary_edges':sum(n==1 for n in edges.values()),
        'nonmanifold_edges':sum(n>2 for n in edges.values()),
        'oppositely_oriented_edges':sum(directed[(a,b)]==directed[(b,a)]==1 for a,b in edges),
        'closed_oriented_surface':not degenerate and all(n==2 for n in edges.values()) and
                                all(directed[(a,b)]==directed[(b,a)]==1 for a,b in edges)}


def read_geometry(reader,body):
    # BodySetup destructor releases the owned intrusive-pointer array at+138.
    # The native16-bit query builds a visitor with particles at geometry+20;
    # its leaf reads float vertices at particles+28, with12-byte xyz stride.
    checks=((0x43616e5,'8b9740010000488b8f38010000'),
            (0x22b98a8,'488d5160807a2000'),
            (0x22b98fa,'4883c210e8cdbbfeff'),
            (0x22a551a,'488d41204889442440'),
            (0x22c3a82,'4c8b4828488b4908'),
            (0x22c3a8a,'4c8d045b488b11420fb70442'),
            (0x22c3a96,'488d0c40f3450f105c8908'),
            (0x22c3acc,'420fb7444202'),
            (0x2155980,'0f108188000000'))
    for rva,code in checks:
        raw=bytes.fromhex(code)
        if reader.read(reader.base+rva,len(raw))!=raw:
            raise ReadError('exact native cooked triangle query layout required')
    data,count,capacity=reader.unpack(body+0x138,'<Qii')
    if not pointer(data) or not 1<=count<=capacity<=64:
        raise ReadError('bounded owned triangle geometry array required')
    owned=reader.read(data,count*8);results=[]
    for geometry, in struct.iter_unpack('<Q',owned):
        if not pointer(geometry) or reader.unpack(geometry,'<Q')[0]-reader.base!=0x9fb0ae8:
            raise ReadError('verified native triangle geometry vtable required')
        if reader.read(geometry+0x80,1)!=b'\0':
            raise ReadError('32-bit native triangle index path not yet verified')
        vp,vn,vc=reader.unpack(geometry+0x48,'<Qii')
        ip,tn,tc=reader.unpack(geometry+0x70,'<Qii')
        if (not pointer(vp) or not pointer(ip) or not 3<=vn<=vc<=500000 or
                not 1<=tn<=tc<=500000 or vn>65536):
            raise ReadError('bounded native16-bit triangle buffers required')
        vertices=[list(v) for v in struct.iter_unpack('<3f',reader.read(vp,vn*12))]
        triangles=[list(t) for t in struct.iter_unpack('<3H',reader.read(ip,tn*6))]
        bounds=list(reader.unpack(geometry+0x88,'<6d'))
        topology=validate_buffers(vertices,triangles,bounds)
        if (reader.unpack(geometry+0x48,'<Qii')!=(vp,vn,vc) or
                reader.unpack(geometry+0x70,'<Qii')!=(ip,tn,tc)):
            raise ReadError('native triangle buffers changed during export')
        results.append({'layout':'native-chaos-triangles16-v1','geometry':hex(geometry),
                        'vertices':vertices,'triangles':triangles,'bounds':bounds,'topology':topology})
    if reader.unpack(body+0x138,'<Qii')!=(data,count,capacity) or reader.read(data,count*8)!=owned:
        raise ReadError('native triangle ownership changed during export')
    return results


def export(pid,body):
    reader=Reader(pid,EXPECTED_EXE)
    try:
        probe=CollisionProbe(reader);identity=probe.p.identity(body,'BodySetup')
        mesh=int(identity['outer_address'],16);mesh_identity=probe.p.identity(mesh,'StaticMesh')
        if probe.p.fields(mesh,['BodySetup'])['BodySetup']['value']!=identity:
            raise ReadError('native mesh/body backpointer required')
        proof=client_proof(pid);geometry=read_geometry(reader,body)
        if probe.p.identity(body)!=identity or probe.p.identity(mesh)!=mesh_identity:
            raise ReadError('native mesh/body identity changed during export')
        return {'pid':pid,'client_proof':proof,'body':identity,'mesh':mesh_identity,'geometry':geometry,
                'completed_client_proof':client_proof(pid),'functions_invoked':False,
                'collision_activated':False,'scope':'Verified native local triangle buffers; world transform and live capsule contact remain unverified'}
    finally:reader.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid',type=int,required=True);p.add_argument('--body',type=lambda v:int(v,0),required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=export(a.pid,a.body);a.output.write_text(json.dumps(result,indent=2))
    print(json.dumps({'mesh':result['mesh']['name'],'geometry':[g['topology'] for g in result['geometry']],
                      'collision_activated':False}))
