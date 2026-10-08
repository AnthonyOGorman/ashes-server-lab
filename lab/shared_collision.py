"""Exact collision instances sharing immutable local-space faces and BVHs."""
import math
from collections.abc import Sequence
from .capsule_sweep import dot, sub, cross


class WorldFaces(Sequence):
    def __init__(self, instance):self.instance=instance
    def __len__(self):return len(self.instance.source.faces)
    def __getitem__(self,index):
        if isinstance(index,slice):return [self[i] for i in range(*index.indices(len(self)))]
        face,normal=self.instance.source.faces[index]
        return tuple(self.instance.point(p) for p in face),self.instance.normal(normal)


class SharedCollision:
    _shared_collision=True
    def __init__(self,source,matrix):
        from .static_collision import instance_point
        instance_point(matrix,[0,0,0])  # Retain native positive similarity guards.
        self.source=source;self.matrix=tuple(matrix)
        self.axes=[matrix[i:i+3] for i in (0,4,8)]
        self.scale_squared=dot(self.axes[0],self.axes[0]);self.scale=math.sqrt(self.scale_squared)
        self._geometry_kind=getattr(source,'_geometry_kind','convex')
        self.faces=WorldFaces(self)
        corners=[self.point([source.maximum[i] if n&(1<<i) else source.minimum[i]
                            for i in range(3)]) for n in range(8)]
        self.minimum=[min(p[i] for p in corners) for i in range(3)]
        self.maximum=[max(p[i] for p in corners) for i in range(3)]

    def point(self,p):
        return [self.matrix[12+i]+sum(p[j]*self.axes[j][i] for j in range(3)) for i in range(3)]

    def inverse(self,p):
        delta=sub(p,self.matrix[12:15])
        return [dot(delta,axis)/self.scale_squared for axis in self.axes]

    def normal(self,n):
        return [sum(n[j]*self.axes[j][i] for j in range(3))/self.scale for i in range(3)]

    def triangles(self,minimum,maximum):
        if any(self.maximum[i]<minimum[i] or self.minimum[i]>maximum[i] for i in range(3)):return
        corners=[self.inverse([maximum[i] if n&(1<<i) else minimum[i] for i in range(3)]) for n in range(8)]
        low=[min(p[i] for p in corners) for i in range(3)]
        high=[max(p[i] for p in corners) for i in range(3)]
        for face in self.source.triangles(low,high):
            result=tuple(self.point(p) for p in face)
            if all(max(p[i] for p in result)>=minimum[i] and min(p[i] for p in result)<=maximum[i] for i in range(3)):
                yield result

    def contains_point(self,point,tolerance=1e-7):
        return self.source.contains_point(self.inverse(point),tolerance/self.scale)

    def ground(self,x,y,maximum_height,floor_z):
        hits=[]
        for a,b,c in self.triangles([x,y,self.minimum[2]],[x,y,maximum_height+.001]):
            normal=cross(sub(b,a),sub(c,a));length=math.sqrt(dot(normal,normal))
            if length<1e-9 or normal[2]/length<floor_z:continue
            normal=[v/length for v in normal]
            denominator=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
            if abs(denominator)<1e-12:continue
            u=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/denominator
            v=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/denominator
            if min(u,v,1-u-v)<-1e-8:continue
            height=u*a[2]+v*b[2]+(1-u-v)*c[2]
            if height<=maximum_height+.001:
                hits.append({'height':height,'normal':normal,'source':
                             'native triangle mesh' if self._geometry_kind=='triangle' else 'native convex mesh'})
        return max(hits,key=lambda hit:hit['height']) if hits else None


def resident_faces(meshes):
    """Count actual stored geometry once, while preserving every world instance."""
    sources={}
    for mesh in meshes:
        source=getattr(mesh,'source',mesh)
        sources[id(source)]=source
    return sum(len(source.faces) for source in sources.values())
