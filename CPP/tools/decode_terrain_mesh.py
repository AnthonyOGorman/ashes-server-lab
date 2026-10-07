"""Decode the cooked warped landscape's Chaos triangle collision, offline."""
import json,pathlib,hashlib,struct,numpy as np
from decode_terrain_collision import Cursor,transform
root=pathlib.Path(__file__).resolve().parents[1];source=root/'data/terrain-offline/cooked-mesh';output=root/'data/terrain-offline/decoded-mesh';output.mkdir(parents=True,exist_ok=True)
entries=[]
for tile in json.loads((source/'manifest.json').read_text())['tiles']:
    data=(source/tile['cooked']).read_bytes()
    if hashlib.sha256(data).hexdigest()!=tile['sha256']:raise ValueError('Cooked terrain mesh hash mismatch')
    c=Cursor(data)
    if c.read('ii')!=(1,0) or c.read('B')!=11:raise ValueError('Expected unique Chaos triangle mesh')
    convex,collide=c.read('ii');collision_type=c.read('B')
    if convex!=0 or collide not in (0,1) or collision_type!=11:raise ValueError('Triangle mesh flags differ')
    if c.read('i')!=1:raise ValueError('Expected float vertex particles')
    vertices,vertex_count=c.array(12)
    if c.read('i')!=1:raise ValueError('Expected 32-bit triangle indices')
    triangles,triangle_count=c.array(12)
    bounds=np.array(c.read('ffffff')).reshape(2,3)
    v=np.frombuffer(vertices,dtype='<f4').reshape(-1,3);indices=np.frombuffer(triangles,dtype='<i4').reshape(-1,3)
    if not np.isfinite(v).all() or indices.min()<0 or indices.max()>=vertex_count:raise ValueError('Invalid terrain vertices or face indices')
    if not np.allclose(v.min(0),bounds[0],atol=.001) or not np.allclose(v.max(0),bounds[1],atol=.001):raise ValueError('Terrain mesh bounds differ')
    nodes,node_count=c.array(64);face_bounds,face_bound_count=c.array(24)
    if face_bound_count!=triangle_count or not np.isfinite(np.frombuffer(face_bounds,dtype='<f4')).all():raise ValueError('Terrain BVH face bounds mismatch')
    materials,material_count=c.array(2);face_remap,face_remap_count=c.array(4);vertex_remap,vertex_remap_count=c.array(4)
    if material_count not in (0,1,triangle_count) or face_remap_count not in (0,triangle_count) or vertex_remap_count not in (0,vertex_count):raise ValueError('Terrain mesh material/remap dimensions differ')
    if c.pos!=len(data):raise ValueError('Terrain mesh archive not fully consumed')
    files={}
    for name,blob in dict(vertices=vertices,triangles=triangles,materials=materials,face_remap=face_remap,vertex_remap=vertex_remap).items():
        filename=tile['sha256']+'.'+name;(output/filename).write_bytes(blob);files[name]={'file':filename,'sha256':hashlib.sha256(blob).hexdigest(),'bytes':len(blob)}
    entries.append({**tile,'vertex_count':vertex_count,'triangle_count':triangle_count,'material_count':material_count,'source_bvh_nodes':node_count,'matrix':transform(tile['transform_chain']).flatten().tolist(),'local_bounds':bounds.tolist(),'buffers':files,'validation':'complete archive consumption, finite vertices, face-index bounds, local bounds and material/remap counts'})
report={'schema':'ashes-offline-landscape-mesh-v1','status':'decoded','scope':'warped landscape collision only; no static mesh props','meshes':entries}
(output/'manifest.json').write_text(json.dumps(report,indent=2));print(json.dumps({'status':'decoded','meshes':len(entries),'vertices':sum(t['vertex_count'] for t in entries),'triangles':sum(t['triangle_count'] for t in entries)}))
