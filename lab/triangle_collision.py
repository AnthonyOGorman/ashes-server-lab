"""Indexed native triangle surfaces with bounded spatial and solid-volume queries."""
import math
from collections import Counter,defaultdict

from .capsule_sweep import cross,dot,sub,closest_point_triangle


def overlaps(low,high,minimum,maximum):
    return all(high[i]>=minimum[i] and low[i]<=maximum[i] for i in range(3))


class TriangleCollision:
    _geometry_kind='triangle'

    def __init__(self,vertices,triangles):
        if not 3<=len(vertices)<=500000 or not 1<=len(triangles)<=500000:
            raise ValueError('bounded indexed triangle geometry required')
        if any(len(v)!=3 or not all(math.isfinite(x) for x in v) for v in vertices):
            raise ValueError('finite triangle vertices required')
        self.minimum=[min(v[i] for v in vertices) for i in range(3)]
        self.maximum=[max(v[i] for v in vertices) for i in range(3)]
        self.faces=[];self.face_bounds=[];edges=Counter();directed=Counter()
        for indices in triangles:
            if len(indices)!=3 or any(type(i) is not int or not 0<=i<len(vertices) for i in indices):
                raise ValueError('triangle index outside vertex array')
            face=[list(vertices[i]) for i in indices]
            normal=cross(sub(face[1],face[0]),sub(face[2],face[0]));length=math.sqrt(dot(normal,normal))
            if length<1e-9:raise ValueError('nondegenerate native triangles required')
            self.faces.append((tuple(face),[v/length for v in normal]))
            self.face_bounds.append(([min(v[i] for v in face) for i in range(3)],
                                     [max(v[i] for v in face) for i in range(3)]))
            for i in range(3):
                edge=(indices[i],indices[(i+1)%3]);directed[edge]+=1;edges[tuple(sorted(edge))]+=1
        if any(n>2 for n in edges.values()):raise ValueError('nonmanifold triangle surface rejected')
        self.closed=all(n==2 for n in edges.values()) and len({i for edge in edges for i in edge})>=4
        if self.closed and any(directed[(a,b)]!=1 or directed[(b,a)]!=1 for a,b in edges):
            raise ValueError('consistently oriented closed triangle surface required')
        self.tree=self._build(list(range(len(self.faces))))

    def _build(self,indices):
        low=[min(self.face_bounds[j][0][i] for j in indices) for i in range(3)]
        high=[max(self.face_bounds[j][1][i] for j in indices) for i in range(3)]
        if len(indices)<=8:return (low,high,indices,None,None)
        axis=max(range(3),key=lambda i:high[i]-low[i])
        indices.sort(key=lambda j:self.face_bounds[j][0][axis]+self.face_bounds[j][1][axis])
        middle=len(indices)//2
        return (low,high,None,self._build(indices[:middle]),self._build(indices[middle:]))

    def _candidates(self,minimum,maximum):
        stack=[self.tree]
        while stack:
            low,high,indices,left,right=stack.pop()
            if not overlaps(low,high,minimum,maximum):continue
            if indices is None:stack.extend((left,right))
            else:
                for index in indices:
                    low,high=self.face_bounds[index]
                    if overlaps(low,high,minimum,maximum):yield index

    def triangles(self,minimum,maximum):
        for index in self._candidates(minimum,maximum):yield self.faces[index][0]

    def ground(self,x,y,maximum_height,floor_z):
        hits=[]
        for index in self._candidates([x,y,self.minimum[2]],[x,y,maximum_height+.001]):
            (a,b,c),normal=self.faces[index]
            if normal[2]<floor_z:continue
            denominator=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
            if abs(denominator)<1e-12:continue
            u=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/denominator
            v=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/denominator
            if min(u,v,1-u-v)<-1e-8:continue
            height=u*a[2]+v*b[2]+(1-u-v)*c[2]
            if height<=maximum_height+.001:
                hits.append({'height':height,'normal':normal,'source':'native triangle mesh'})
        return max(hits,key=lambda hit:hit['height']) if hits else None

    def contains_point(self,point,tolerance=1e-7):
        if not self.closed or not overlaps(point,point,self.minimum,self.maximum):return False
        # Boundary points count as solid. A capsule touching the surface still
        # needs the separate exact segment/triangle distance clearance check.
        for triangle in self.triangles([v-tolerance for v in point],[v+tolerance for v in point]):
            closest=closest_point_triangle(point,triangle)
            if math.dist(point,closest)<=tolerance:return True
        # Ray along+X. Merge shared-edge/vertex intersections so triangulation
        # does not turn a single crossing into two. Near-tangent hits use a
        # second non-axis direction rather than silently claiming clearance.
        results=[]
        for direction in ([1.,0.,0.],[1.,.137,.271],[1.,-.193,.317]):
            reach=max(self.maximum[i]-self.minimum[i] for i in range(3))*4+1
            end=[point[i]+direction[i]*reach for i in range(3)]
            low=[min(point[i],end[i]) for i in range(3)];high=[max(point[i],end[i]) for i in range(3)]
            hits=[]
            for index in self._candidates(low,high):
                (a,b,c),normal=self.faces[index];ab=sub(b,a);ac=sub(c,a)
                h=cross(direction,ac);det=dot(ab,h)
                if abs(det)<1e-12:continue
                offset=sub(point,a);u=dot(offset,h)/det
                if not -1e-9<=u<=1+1e-9:continue
                q=cross(offset,ab);v=dot(direction,q)/det
                if v<-1e-9 or u+v>1+1e-9:continue
                t=dot(ac,q)/det
                if t>tolerance:hits.append(t)
            hits.sort();distinct=[]
            for t in hits:
                if not distinct or t-distinct[-1]>tolerance:distinct.append(t)
            results.append(bool(len(distinct)%2))
        if not all(v==results[0] for v in results):
            raise ValueError('ambiguous solid triangle containment; placement rejected')
        return results[0]


def triangle_surfaces(vertices,triangles):
    """Preserve native faces while separating shells at shared nonmanifold edges.

    A pair of opposite faces is a zero-volume surface, not a solid. Components
    connected through ordinary two-face edges retain their exact indexed shape.
    """
    try:return [TriangleCollision(vertices,triangles)]
    except ValueError as exc:
        if str(exc)!='nonmanifold triangle surface rejected':raise
    edges=defaultdict(list)
    for index,face in enumerate(triangles):
        for i in range(3):edges[tuple(sorted((face[i],face[(i+1)%3])))].append(index)
    adjacent=[[] for _ in triangles]
    for faces in edges.values():
        if len(faces)==2:
            a,b=faces;adjacent[a].append(b);adjacent[b].append(a)
    seen=set();meshes=[]
    for first in range(len(triangles)):
        if first in seen:continue
        pending=[first];seen.add(first);component=[]
        while pending:
            index=pending.pop();component.append(triangles[index])
            for neighbor in adjacent[index]:
                if neighbor not in seen:seen.add(neighbor);pending.append(neighbor)
        if len(meshes)>=4096:raise ValueError('bounded native triangle surface components required')
        used=sorted({i for face in component for i in face});lookup={old:new for new,old in enumerate(used)}
        meshes.append(TriangleCollision([vertices[i] for i in used],
                      [[lookup[i] for i in face] for face in component]))
    return meshes
