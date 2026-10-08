"""World-space convex collision from reflected native mesh exports."""
import math
import hashlib
import json
import threading
from collections import OrderedDict
from collections import Counter

from .capsule_sweep import cross, dot, sub

GEOMETRY_VERSION=8

if '_local_shapes_lock' not in globals():
    _local_shapes_lock=threading.RLock()
    _local_shapes_cache=OrderedDict()


def collision_face_count(meshes):
    from .shared_collision import resident_faces
    return resident_faces(meshes)


def local_shapes(report,component):
    asset=report['assets'][component['asset']]
    # Native allocation addresses can change when an asset streams out and in.
    # Sharing is keyed by actual decoded collision data, while process/world
    # ownership remains checked by the normal admission path.
    geometry={'collision_trace_flag':asset['collision_trace_flag'],'shapes':asset.get('shapes',[]),
        'triangles':[{k:g[k] for k in ('layout','vertices','triangles','bounds')}
                     for g in asset.get('CookedTriangles',[])]}
    key=(GEOMETRY_VERSION,hashlib.sha256(json.dumps(geometry,sort_keys=True,separators=(',',':')).encode()).hexdigest())
    with _local_shapes_lock:
        if key in _local_shapes_cache:
            _local_shapes_cache.move_to_end(key)
            return _local_shapes_cache[key],[]
    local=dict(component,instances=[],native_component_transform={
        'rotation':[0,0,0,1],'translation':[0,0,0],'scale':[1,1,1]})
    shapes,errors=from_export(dict(report,components=[local]),_share_assets=False)
    if errors:return shapes,errors
    with _local_shapes_lock:
        # Concurrent preparation must converge on the same immutable shapes.
        shapes=_local_shapes_cache.setdefault(key,shapes)
        _local_shapes_cache.move_to_end(key)
        while len(_local_shapes_cache)>64 or sum(collision_face_count(v) for v in _local_shapes_cache.values())>500000:
            _local_shapes_cache.popitem(last=False)
    return shapes,[]


def placement_matrix(transform,instance=None):
    """Compose native positive uniform component/instance transforms exactly."""
    zero=transform_point(transform,[0,0,0])
    rotation=dict(transform,translation=[0,0,0])
    axes=[transform_point(rotation,[int(i==j) for i in range(3)]) for j in range(3)]
    if instance is not None:
        instance_point(instance,[0,0,0])
        zero=transform_point(transform,instance[12:15])
        axes=[[sum(instance[j*4+k]*axes[k][i] for k in range(3)) for i in range(3)] for j in range(3)]
    return [v for axis in axes for v in (*axis,0.)]+[*zero,1.]


def transform_point(transform, point):
    q=transform['rotation'];translation=transform['translation'];scale=transform['scale']
    if len(q)!=4 or len(translation)!=3 or len(scale)!=3 or len(point)!=3:
        raise ValueError('exact native transform dimensions required')
    if not all(math.isfinite(v) for v in (*q,*translation,*scale,*point)):
        raise ValueError('finite native transform required')
    if abs(sum(v*v for v in q)-1)>1e-5 or min(map(abs,scale))<1e-8:
        raise ValueError('unit quaternion and nonzero scale required')
    vector=[point[i]*scale[i] for i in range(3)]
    uv=cross(q[:3],vector);uuv=cross(q[:3],uv)
    return [vector[i]+2*(q[3]*uv[i]+uuv[i])+translation[i] for i in range(3)]


class ConvexCollision:
    def __init__(self, vertices, indices):
        if not 4<=len(vertices)<=65536 or not 12<=len(indices)<=196608 or len(indices)%3:
            raise ValueError('bounded indexed convex geometry required')
        if any(len(v)!=3 or not all(math.isfinite(x) for x in v) for v in vertices):
            raise ValueError('finite convex vertices required')
        if any(type(i) is not int or not 0<=i<len(vertices) for i in indices):
            raise ValueError('convex index outside vertex array')
        self.minimum=[min(v[i] for v in vertices) for i in range(3)]
        self.maximum=[max(v[i] for v in vertices) for i in range(3)]
        centre=[sum(v[i] for v in vertices)/len(vertices) for i in range(3)]
        self.faces=[];edges=Counter()
        for offset in range(0,len(indices),3):
            a,b,c=[list(vertices[i]) for i in indices[offset:offset+3]]
            normal=cross(sub(b,a),sub(c,a));length=math.sqrt(dot(normal,normal))
            if length<1e-9:
                continue
            normal=[x/length for x in normal]
            # Orient around the interior centroid, including mirrored scales.
            if dot(normal,sub(centre,a))>0:
                b,c=c,b;normal=[-x for x in normal]
            if any(dot(normal,sub(v,a))>.05 for v in vertices):
                raise ValueError('exported face is not a convex supporting plane')
            self.faces.append(((a,b,c),normal))
            face=indices[offset:offset+3]
            edges.update(tuple(sorted((face[i],face[(i+1)%3]))) for i in range(3))
        if len(self.faces)<4:
            raise ValueError('nondegenerate convex surface required')
        if any(count!=2 for count in edges.values()):
            raise ValueError('closed convex surface required')

    def triangles(self, minimum, maximum):
        if any(self.maximum[i]<minimum[i] or self.minimum[i]>maximum[i] for i in range(3)):
            return
        for triangle,_ in self.faces:
            if all(max(v[i] for v in triangle)>=minimum[i] and
                   min(v[i] for v in triangle)<=maximum[i] for i in range(3)):
                yield triangle

    def contains_point(self, point, tolerance=1e-7):
        """Closed convex hulls represent solid volumes, including their interior."""
        if any(point[i]<self.minimum[i]-tolerance or
               point[i]>self.maximum[i]+tolerance for i in range(3)):
            return False
        return all(dot(normal,sub(point,triangle[0]))<=tolerance
                   for triangle,normal in self.faces)

    def ground(self, x, y, maximum_height, floor_z):
        if not self.minimum[0]<=x<=self.maximum[0] or not self.minimum[1]<=y<=self.maximum[1]:
            return None
        hits=[]
        for (a,b,c),normal in self.faces:
            if normal[2]<floor_z:
                continue
            denominator=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
            if abs(denominator)<1e-12:
                continue
            u=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/denominator
            v=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/denominator
            if min(u,v,1-u-v)<-1e-8:
                continue
            height=u*a[2]+v*b[2]+(1-u-v)*c[2]
            if height<=maximum_height+.001:
                hits.append({'height':height,'normal':normal,'source':'native convex mesh'})
        return max(hits,key=lambda hit:hit['height']) if hits else None


def box_geometry(shape, component_transform):
    """Exact box surface for uniform component scale; lengths are full sizes.

    Native FKBoxElem drawing at RVA43c7f90 halves X/Y/Z. Rotator is
    degrees in Pitch/Yaw/Roll order, with intrinsic yaw, pitch, then roll.
    Nonuniform component scaling requires the native box scaling rules.
    """
    sizes=[shape[key] for key in ('X','Y','Z')]
    centre=shape['Center'];rotation=shape['Rotation']
    if len(centre)!=3 or len(rotation)!=3 or not all(
            math.isfinite(v) for v in (*sizes,*centre,*rotation)) or min(sizes)<=0:
        raise ValueError('finite positive native box dimensions required')
    scale=component_transform['scale']
    if len(scale)!=3 or max(scale)-min(scale)>1e-8 or min(scale)<=0:
        raise ValueError('native box requires positive uniform component scale')
    pitch,yaw,roll=[math.radians(v%360) for v in rotation]
    sp,cp=math.sin(pitch),math.cos(pitch)
    sy,cy=math.sin(yaw),math.cos(yaw)
    sr,cr=math.sin(roll),math.cos(roll)
    axes=((cp*cy,cp*sy,sp),
          (sr*sp*cy-cr*sy,sr*sp*sy+cr*cy,-sr*cp),
          (-cr*sp*cy-sr*sy,sr*cy-cr*sp*sy,cr*cp))
    vertices=[]
    for z in (-sizes[2]/2,sizes[2]/2):
        for y in (-sizes[1]/2,sizes[1]/2):
            for x in (-sizes[0]/2,sizes[0]/2):
                local=[centre[i]+sum(v*axis[i] for v,axis in zip((x,y,z),axes))
                       for i in range(3)]
                vertices.append(transform_point(component_transform,local))
    indices=[0,1,3,0,3,2,4,6,7,4,7,5,0,4,5,0,5,1,
             2,3,7,2,7,6,0,2,6,0,6,4,1,5,7,1,7,3]
    return vertices,indices


def validate_cooked_surface(vertices, indices, planes):
    """Require a closed surface identical to all exported native planes."""
    if not 4<=len(planes)<=4096 or not 4<=len(vertices)<=4096:
        raise ValueError('bounded cooked convex geometry required')
    collider=ConvexCollision(vertices,indices)
    for plane in planes:
        if len(plane)!=6 or not all(math.isfinite(x) for x in plane):
            raise ValueError('finite native point-normal plane required')
        normal=plane[3:]
        if abs(dot(normal,normal)-1)>.0001:
            raise ValueError('unit native plane normal required')
        if max(dot(normal,sub(v,plane[:3])) for v in vertices)>.002:
            raise ValueError('cooked vertex outside native supporting plane')
    matched=set()
    for (a,b,c),normal in collider.faces:
        matches=[i for i,p in enumerate(planes) if dot(normal,p[3:])>.99999
                 and max(abs(dot(p[3:],sub(v,p[:3]))) for v in (a,b,c))<.002]
        if not matches:
            raise ValueError('triangulated face lacks a matching native plane')
        matched.update(matches)
    if len(matched)!=len(planes):
        raise ValueError('native plane missing from reconstructed surface')


def validate_support_surface(vertices, indices):
    """Prove the closed surface equals the hull of all native support vertices."""
    if not 4<=len(vertices)<=4096:
        raise ValueError('bounded native support vertices required')
    collider=ConvexCollision(vertices,indices)
    extent=max(collider.maximum[i]-collider.minimum[i] for i in range(3))
    tolerance=max(1e-7,extent*1e-10)
    if len(collider.faces)!=len(indices)//3:
        raise ValueError('degenerate support face rejected')
    for (a,_,_),normal in collider.faces:
        if max(dot(normal,sub(v,a)) for v in vertices)>tolerance:
            raise ValueError('surface does not contain all native support vertices')
    return collider


def instance_point(matrix,point):
    """Native row-vector instance matrix, restricted to positive uniform scale."""
    if len(matrix)!=16 or not all(math.isfinite(v) for v in matrix):
        raise ValueError('finite native instance matrix required')
    if any(abs(matrix[i])>1e-10 for i in (3,7,11)) or abs(matrix[15]-1)>1e-10:
        raise ValueError('affine native instance matrix required')
    axes=[matrix[i:i+3] for i in (0,4,8)]
    lengths=[math.sqrt(dot(axis,axis)) for axis in axes]
    scale=max(lengths)
    if min(lengths)<1e-8 or scale-min(lengths)>scale*1e-8:
        raise ValueError('positive uniform instance scale required')
    if any(abs(dot(axes[i],axes[j]))>scale*scale*1e-8
           for i,j in ((0,1),(0,2),(1,2))) or dot(cross(axes[0],axes[1]),axes[2])<=0:
        raise ValueError('orthogonal right-handed instance axes required')
    return [matrix[12+i]+sum(point[j]*axes[j][i] for j in range(3)) for i in range(3)]


def instance_colliders(report,component):
    """Expand verified static instances; moving and unsupported bodies stay explicit."""
    if (component.get('mobility')!=0 or component.get('instance_transform_proof')!=
            'native-uniform-instance-transform-v1'):
        raise ValueError('verified static native instance transform required')
    transform=component['native_component_transform'];scale=transform['scale']
    if min(scale)<=0 or max(scale)-min(scale)>max(scale)*1e-8:
        raise ValueError('positive uniform instance component scale required')
    if not 0<len(component['instances'])<=4096:
        raise ValueError('bounded native instances required')
    shapes,errors=local_shapes(report,component)
    if errors:return [],errors
    meshes=[]
    for instance in component['instances']:
        matrix=instance['matrix']
        instance_point(matrix,[0,0,0])
        for shape in shapes:
            from .shared_collision import SharedCollision
            meshes.append(SharedCollision(shape,placement_matrix(transform,matrix)))
            if collision_face_count(meshes)>500000:
                raise ValueError('bounded instance collision triangle count required')
    return meshes,[]


def from_export(report,*,_share_assets=True):
    """Reject malformed supported geometry and report unimplemented shapes."""
    if len(report['components'])>100000:
        raise ValueError('bounded mesh component inventory required')
    colliders=[];unsupported=[]
    for component in report['components']:
        response=component['response']
        if response['collision_enabled'] not in (1,3,5) or response['pawn_response']!=2:
            continue
        asset=report['assets'][component['asset']]
        scale=component['native_component_transform']['scale']
        if (_share_assets and not component['instances'] and min(scale)>0 and
                max(scale)-min(scale)<=max(scale)*1e-8):
            try:
                from .shared_collision import SharedCollision
                shapes,errors=local_shapes(report,component)
                colliders.extend(SharedCollision(shape,placement_matrix(component['native_component_transform'])) for shape in shapes)
                unsupported.extend(errors)
            except ValueError as exc:
                unsupported.append({'component':component['identity']['address'],'reason':str(exc)})
            if collision_face_count(colliders)>500000:
                raise ValueError('bounded world collision triangle count required')
            continue
        if asset['collision_trace_flag']==3 and not component['instances'] and asset.get('CookedTriangles'):
            try:
                from .triangle_collision import triangle_surfaces
                transform=component['native_component_transform']
                if min(transform['scale'])<=0:
                    raise ValueError('positive native triangle component scale required')
                meshes=[]
                for geometry in asset['CookedTriangles']:
                    if geometry.get('layout')!='native-chaos-triangles16-v1':
                        raise ValueError('verified native cooked triangle layout required')
                    local_bounds=[min(v[i] for v in geometry['vertices']) for i in range(3)]+[
                                  max(v[i] for v in geometry['vertices']) for i in range(3)]
                    if len(geometry['bounds'])!=6 or any(abs(a-b)>.01 for a,b in zip(local_bounds,geometry['bounds'])):
                        raise ValueError('native triangle bounds disagree with decoded vertices')
                    vertices=[transform_point(transform,v) for v in geometry['vertices']]
                    meshes.extend(triangle_surfaces(vertices,geometry['triangles']))
                colliders.extend(meshes)
            except ValueError as exc:
                unsupported.append({'component':component['identity']['address'],'reason':str(exc)})
            if collision_face_count(colliders)>500000:
                raise ValueError('bounded world collision triangle count required')
            continue
        if component['instances']:
            try:
                meshes,errors=instance_colliders(report,component)
                colliders.extend(meshes);unsupported.extend(errors)
            except ValueError as exc:
                unsupported.append({'component':component['identity']['address'],'reason':str(exc)})
            if collision_face_count(colliders)>500000:
                raise ValueError('bounded world collision triangle count required')
            continue
        if asset['collision_trace_flag'] not in (0,1,2):
            unsupported.append({'component':component['identity']['address'],
                                'reason':'complex collision requires verified native geometry'})
            continue
        for shape in asset['shapes']:
            if shape.get('CollisionEnabled',3) not in (1,3,5):
                continue
            if shape['type'] not in ('KConvexElem','KBoxElem'):
                unsupported.append({'component':component['identity']['address'],
                                    'shape':shape['type']})
                continue
            try:
                if shape['type']=='KBoxElem':
                    vertices,indices=box_geometry(shape,component['native_component_transform'])
                else:
                    local_vertices=shape['VertexData'];indices=shape['IndexData']
                    try:
                        ConvexCollision(local_vertices,indices)
                    except ValueError:
                        cooked=shape.get('CookedGeometry')
                        if not cooked or cooked.get('layout') not in ('native-chaos-convex-v1','native-chaos-support-v1'):
                            raise
                        local_vertices=cooked['vertices'];indices=cooked['indices']
                        if cooked['layout']=='native-chaos-support-v1':
                            validate_support_surface(local_vertices,indices)
                        else:
                            validate_cooked_surface(local_vertices,indices,cooked['planes'])
                    vertices=[transform_point(component['native_component_transform'],
                               transform_point(shape['Transform'],v)) for v in local_vertices]
                collider=ConvexCollision(vertices,indices)
            except ValueError as exc:
                unsupported.append({'component':component['identity']['address'],
                                    'shape':shape['type'],'index':shape.get('index'),
                                    'reason':str(exc)})
                continue
            colliders.append(collider)
            if collision_face_count(colliders)>500000:
                raise ValueError('bounded world collision triangle count required')
    return colliders,unsupported
