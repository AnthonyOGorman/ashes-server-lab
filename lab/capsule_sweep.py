"""Continuous upright capsule sweeps against actual triangle surfaces."""
import math


def add(a,b):return [a[i]+b[i] for i in range(3)]
def sub(a,b):return [a[i]-b[i] for i in range(3)]
def mul(a,s):return [v*s for v in a]
def dot(a,b):return sum(a[i]*b[i] for i in range(3))
def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def clamp(v):return max(0.,min(1.,v))


def closest_point_triangle(p, triangle):
    a,b,c=triangle;ab=sub(b,a);ac=sub(c,a);ap=sub(p,a)
    d1,d2=dot(ab,ap),dot(ac,ap)
    if d1<=0 and d2<=0:return list(a)
    bp=sub(p,b);d3,d4=dot(ab,bp),dot(ac,bp)
    if d3>=0 and d4<=d3:return list(b)
    vc=d1*d4-d3*d2
    if vc<=0 and d1>=0 and d3<=0:return add(a,mul(ab,d1/(d1-d3)))
    cp=sub(p,c);d5,d6=dot(ab,cp),dot(ac,cp)
    if d6>=0 and d5<=d6:return list(c)
    vb=d5*d2-d1*d6
    if vb<=0 and d2>=0 and d6<=0:return add(a,mul(ac,d2/(d2-d6)))
    va=d3*d6-d5*d4
    if va<=0 and d4-d3>=0 and d5-d6>=0:
        return add(b,mul(sub(c,b),(d4-d3)/((d4-d3)+(d5-d6))))
    denominator=va+vb+vc
    if abs(denominator)<1e-20:raise ValueError('nondegenerate triangle required')
    return add(a,add(mul(ab,vb/denominator),mul(ac,vc/denominator)))


def closest_segments(p1,q1,p2,q2):
    d1,d2,r=sub(q1,p1),sub(q2,p2),sub(p1,p2)
    a,e=dot(d1,d1),dot(d2,d2);f=dot(d2,r)
    if a<=1e-20 and e<=1e-20:return list(p1),list(p2)
    if a<=1e-20:s,t=0.,clamp(f/e)
    else:
        c=dot(d1,r)
        if e<=1e-20:s,t=clamp(-c/a),0.
        else:
            b=dot(d1,d2);denominator=a*e-b*b
            s=clamp((b*f-c*e)/denominator) if denominator>1e-20 else 0.
            t=(b*s+f)/e
            if t<0:t=0.;s=clamp(-c/a)
            elif t>1:t=1.;s=clamp((b-c)/a)
    return add(p1,mul(d1,s)),add(p2,mul(d2,t))


def segment_triangle_distance(start,end,triangle):
    a,b,c=triangle;normal=cross(sub(b,a),sub(c,a));length=math.sqrt(dot(normal,normal))
    if length<1e-10:raise ValueError('nondegenerate triangle required')
    direction=sub(end,start);denominator=dot(normal,direction)
    if abs(denominator)>1e-16:
        t=dot(normal,sub(a,start))/denominator
        if 0<=t<=1:
            point=add(start,mul(direction,t));other=closest_point_triangle(point,triangle)
            if math.dist(point,other)<1e-8:return 0.,point,other
    pairs=[(list(p),closest_point_triangle(p,triangle)) for p in (start,end)]
    pairs.extend(closest_segments(start,end,u,v) for u,v in ((a,b),(b,c),(c,a)))
    p,q=min(pairs,key=lambda pair:dot(sub(*pair),sub(*pair)))
    return math.dist(p,q),p,q


def sweep_triangle(position,delta,half_height,radius,triangle, tolerance=.001):
    speed=math.sqrt(dot(delta,delta))
    if speed<1e-12:return None
    if not 0<radius<=half_height:raise ValueError('valid upright capsule dimensions required')
    segment=half_height-radius;t=0.
    for _ in range(256):
        centre=add(position,mul(delta,t))
        start=add(centre,[0.,0.,-segment]);end=add(centre,[0.,0.,segment])
        distance,p,q=segment_triangle_distance(start,end,triangle)
        gap=distance-radius
        if distance>1e-12:normal=mul(sub(p,q),1/distance)
        else:
            normal=cross(sub(triangle[1],triangle[0]),sub(triangle[2],triangle[0]))
            normal=mul(normal,1/math.sqrt(dot(normal,normal)))
            if dot(normal,delta)>0:normal=mul(normal,-1)
        if gap<=tolerance:
            if t==0 and dot(delta,normal)>=-1e-9:return None
            return {'fraction':t,'normal':normal,'point':q,'separation':gap}
        t+=gap/speed
        if t>1:return None
    # Near-tangent convergence cannot grant an unchecked final displacement.
    return {'fraction':min(t,1.),'normal':normal,'point':q,'separation':gap,
            'iteration_limit':True}


def sweep_capsule(position,delta,half_height,radius,triangles):
    hits=[hit for tri in triangles if (hit:=sweep_triangle(position,delta,half_height,radius,tri)) is not None]
    return min(hits,key=lambda hit:hit['fraction']) if hits else None


def limit_upward_slide(slide, attempted, normal):
    """A falling wall slide cannot create ascent beyond the attempted ascent."""
    limit=max(0.,attempted[2])
    if slide[2]<=limit+1e-9:
        return slide
    retained=mul(slide,limit/slide[2])
    remainder=[slide[0]-retained[0],slide[1]-retained[1],0.]
    length=math.hypot(*normal[:2])
    if length>1e-10:
        horizontal=[normal[0]/length,normal[1]/length,0.]
        remainder=sub(remainder,mul(horizontal,min(0.,dot(remainder,horizontal))))
    return add(retained,remainder)


def move_capsule(position,delta,half_height,radius,query, *, grounded=False,walkable_floor_z=.6156615,
                 limit_falling_ascent=False):
    current=list(position);remaining=list(delta);hits=[]
    if dot(remaining,remaining)<1e-12:return current,hits
    for _ in range(4):
        triangles=query(current,remaining,half_height,radius)
        hit=sweep_capsule(current,remaining,half_height,radius,triangles)
        if hit is None:return add(current,remaining),hits
        if grounded and 0<=hit['normal'][2]<walkable_floor_z:
            # Walking must not turn horizontal input into climbing a steep
            # wall. Preserve its measured surface normal for diagnostics.
            hit['surface_normal']=hit['normal']
            horizontal=hit['normal'][:2];length=math.hypot(*horizontal)
            if length>1e-10:hit['normal']=[horizontal[0]/length,horizontal[1]/length,0.]
        current=add(current,mul(remaining,hit['fraction']));hits.append(hit)
        remaining=mul(remaining,1-hit['fraction'])
        inward=min(0.,dot(remaining,hit['normal']))
        attempted=remaining
        remaining=sub(remaining,mul(hit['normal'],inward))
        if limit_falling_ascent:
            remaining=limit_upward_slide(remaining,attempted,hit['normal'])
        if dot(remaining,remaining)<1e-12:break
    return current,hits
