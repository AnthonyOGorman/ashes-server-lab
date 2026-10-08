"""Bounded landscape/convex locomotion; other world mesh collision remains required."""
import math
from .terrain import highest_ground
from .capsule_sweep import move_capsule,dot,mul,sub,cross,sweep_triangle,limit_upward_slide


class TerrainMovement:
    def __init__(self, tiles, spawn, *, speed=220., acceleration=8192., gravity=-2450.,
                 half_height=95.98999786376953, radius=21.989999771118164,
                 step_height=45., floor_z=0.6156615018844604, jump_velocity=900., floor_clearance=0.,
                 max_simulation_step=.05, static_meshes=()):
        self.tiles=tiles;self.position=list(spawn);self.velocity=[0.,0.,0.]
        self.static_meshes=list(static_meshes)
        self.speed=speed;self.max_acceleration=acceleration;self.gravity=gravity
        self.half_height=half_height;self.radius=radius;self.step_height=step_height;self.floor_z=floor_z
        if not math.isfinite(jump_velocity) or not 0 < jump_velocity <= 2000 or not 0 <= floor_clearance <= 2.5:
            raise ValueError('bounded jump velocity and floor clearance required')
        self.jump_velocity=jump_velocity;self.floor_clearance=floor_clearance;self.jump_pressed=False
        if not math.isfinite(max_simulation_step) or not .001 <= max_simulation_step <= .05:
            raise ValueError('bounded simulation step required')
        self.max_simulation_step=max_simulation_step
        self.timestamp=None;self.wall_start=None;self.client_start=None;self.mode=3
        self.wall_observed=None;self.time_budget=.125
        if self.floor(*spawn[:2]) is None:
            raise ValueError('terrain-supported initial spawn required')

    def _ground(self,x,y,maximum_height):
        hit=highest_ground(self.tiles,x,y)
        for mesh in getattr(self,'static_meshes',()):
            candidate=mesh.ground(x,y,maximum_height,self.floor_z)
            if candidate is not None and (hit is None or candidate['height']>hit['height']):
                hit=candidate
        return hit

    def floor(self,x,y,step_up=0.):
        maximum_height=self.position[2]-self.half_height+2.5+step_up
        hit=self._ground(x,y,maximum_height)
        if hit is None or hit['normal'][2]<self.floor_z:
            return None
        mesh_support=hit.get('source') in ('native convex mesh','native triangle mesh')
        if not mesh_support and any(self._ground(x+dx,y+dy,maximum_height) is None for dx,dy in
               ((self.radius,0),(-self.radius,0),(0,self.radius),(0,-self.radius))):
            return None
        estimate=hit['height']+self.half_height+self.radius*(1/hit['normal'][2]-1)+self.floor_clearance
        if not mesh_support:
            return estimate
        # Small mesh facets cannot be treated as infinite slope planes. Find
        # the capsule's finite face/edge contact instead, including neighboring
        # facets. Mesh support uses actual capsule contact: requiring ground at
        # the outer radius at the capsule's bottom height rejects valid curved
        # hemisphere contact on small or sloped facets.
        padding=max(2.,self.radius)
        travel=padding+self.radius*(1/self.floor_z-1)+self.floor_clearance+2.5
        start=[x,y,estimate+padding];delta=[0.,0.,-travel]
        low=[x-self.radius,y-self.radius,start[2]-travel-self.half_height]
        high=[x+self.radius,y+self.radius,start[2]+self.half_height]
        contacts=[]
        for mesh in getattr(self,'static_meshes',()):
            for triangle in mesh.triangles(low,high):
                normal=cross(sub(triangle[1],triangle[0]),sub(triangle[2],triangle[0]))
                length=math.sqrt(dot(normal,normal))
                if length<1e-9 or normal[2]/length<self.floor_z:
                    continue
                contact=sweep_triangle(start,delta,self.half_height,self.radius,triangle)
                if contact and contact['normal'][2]>=self.floor_z and not contact.get('iteration_limit'):
                    contacts.append(start[2]-travel*contact['fraction']+self.floor_clearance)
        return max(contacts) if contacts else None

    def advance(self,move,now):
        t=move['timestamp'];a=move['acceleration']
        if not math.isfinite(t) or t<0 or len(a)!=3 or not all(math.isfinite(v) for v in a):
            raise ValueError('finite nonnegative time and input required')
        if move['compressed_flags'] not in (0,1) or abs(a[2])>0.1 or math.hypot(a[0],a[1])>self.max_acceleration+0.3:
            raise ValueError('unsupported flags or input outside locomotion bounds')
        if self.timestamp is None:
            self.timestamp=t;self.client_start=t;self.wall_start=now
            self.wall_observed=now
            return None
        dt=t-self.timestamp
        timestamp_reset=False
        # This exact client resets its move clock every240 seconds. Accept
        # only a new move crossing that boundary; it spends the existing wall
        # time budget and cannot grant an extra simulation allowance.
        wrapped=t+240.-self.timestamp
        if (dt<0 and move.get('kind')=='new' and 239.5<=self.timestamp<=240.25
                and 0<=t<=120. and 0<wrapped<=max(.25,now-self.wall_observed+.125)):
            dt=t+240.-self.timestamp
            timestamp_reset=True
        if dt<=0:
            return None  # old/pending retransmission already handled
        # Fund simulation with elapsed server time. Discarding queued history
        # advances the timestamp but cannot permanently poison later input or
        # reset the budget to manufacture simulation time.
        # Keep up to two ordinary packet intervals of earned server time.
        # A delayed idle update can otherwise consume the entire .25s cap
        # immediately before a legitimate movement batch. Each interval still
        # stays at most .25s and the initial allowance remains .125s.
        self.time_budget=min(.5,self.time_budget+max(0.,now-self.wall_observed))
        self.wall_observed=max(self.wall_observed,now)
        if dt>.25 or dt>self.time_budget:
            # Packet gaps must not permanently poison every later timestamp.
            # Discard this interval, keep authoritative position unchanged,
            # and correct the client at its current timestamp. Retain the
            # accumulated wall-clock budget so repeats cannot manufacture time.
            self.timestamp=t
            return {'timestamp':t,'server_position':self.position.copy(),
                    'server_velocity':self.velocity.copy(),'movement_mode':self.mode,
                    'delta':[0.,0.,0.],'discarded_time':dt,'time_budget':self.time_budget,
                    'timestamp_reset':timestamp_reset,
                    'scope':'discarded time interval; server position preserved'}
        self.time_budget=max(0.,self.time_budget-dt)
        old=self.position.copy();hits=[];jumped=False
        # Keep each swept chord close to the ballistic path, including when a
        # packet interval straddles the apex. Only the accepted interval is
        # subdivided; timestamp and wall-time funding remain packet-scoped.
        steps=max(1,math.ceil(dt/getattr(self,'max_simulation_step',.05)-1e-10))
        for index in range(steps):
            step_hits,step_jump=self._simulate(move,dt/steps)
            hits.extend({**hit,'simulation_step':index} for hit in step_hits)
            jumped|=step_jump
        self.timestamp=t
        mode=self.mode
        return {'timestamp':t,'server_position':self.position.copy(),
                'server_velocity':self.velocity.copy(),'movement_mode':mode,
                'delta':[self.position[i]-old[i] for i in range(3)],
                'jump_started':jumped,
                'timestamp_reset':timestamp_reset,
                'collision_hits':hits,
                'scope':'landscape and exported convex mesh capsule sweep/walk/jump; other mesh shapes remain unsupported'}

    def _simulate(self,move,dt):
        a=move['acceleration']
        old=self.position.copy();vx,vy,vz=self.velocity
        old_floor=self.floor(old[0],old[1])
        grounded=old_floor is not None and abs(old[2]-old_floor)<=2.5 and vz<=0
        jump_pressed=bool(move['compressed_flags']&1)
        jumped=jump_pressed and not self.jump_pressed and grounded
        self.jump_pressed=jump_pressed
        if jumped:
            vz=self.jump_velocity;grounded=False
        if math.hypot(a[0],a[1])>0.1:
            vx+=a[0]*dt;vy+=a[1]*dt
            speed=math.hypot(vx,vy)
            if speed>self.speed:
                vx*=self.speed/speed;vy*=self.speed/speed
        elif grounded:
            speed=math.hypot(vx,vy)
            factor=max(0.,1-self.max_acceleration*dt/speed) if speed else 0.
            vx*=factor;vy*=factor
        x,y=old[0]+vx*dt,old[1]+vy*dt
        floor=self.floor(x,y,self.step_height if grounded else 0.)
        if grounded and floor is not None and floor-old_floor>self.step_height:
            x,y=old[:2];vx=vy=0.;floor=old_floor
        if grounded and floor is not None and abs(floor-old_floor)<=self.step_height:
            z=floor;vz=0.;mode=1
        else:
            z=old[2]+vz*dt+0.5*self.gravity*dt*dt;vz+=self.gravity*dt;mode=3
            if floor is not None and z<=floor and old[2]>=floor-2.5:
                z=floor;vz=0.;mode=1
        def triangles(position,delta,half_height,radius):
            end=[position[i]+delta[i] for i in range(3)]
            low=[min(position[i],end[i])-(radius if i<2 else half_height) for i in range(3)]
            high=[max(position[i],end[i])+(radius if i<2 else half_height) for i in range(3)]
            for tile in self.tiles:
                for tri in tile.triangles(low,high):
                    if min(p[2] for p in tri)<=high[2] and max(p[2] for p in tri)>=low[2]:
                        yield tri
            for mesh in getattr(self,'static_meshes',()):
                yield from mesh.triangles(low,high)
        target=[x,y,z]
        target,hits=move_capsule(old,sub(target,old),self.half_height,self.radius,triangles,
                                 grounded=grounded,walkable_floor_z=self.floor_z,
                                 limit_falling_ascent=not grounded)
        velocity=[vx,vy,vz]
        for hit in hits:
            attempted_velocity=velocity
            velocity=sub(velocity,mul(hit['normal'],min(0.,dot(velocity,hit['normal']))))
            if not grounded:
                velocity=limit_upward_slide(velocity,attempted_velocity,hit['normal'])
            if hit['normal'][2]>=self.floor_z and velocity[2]<=.1:
                mode=1
        if grounded:
            velocity[2]=min(0.,velocity[2])
        if mode==1:
            velocity[2]=0.
        x,y,z=target;vx,vy,vz=velocity
        support=self.floor(x,y)
        if mode==1 and support is not None and abs(z-support)<=.01 and abs(vz)<=1e-7:
            # Remove sweep tolerance and projection roundoff at a supported
            # floor, so an idle walker does not become airborne from tiny vz.
            z=support;vz=0.
        self.position=[x,y,z];self.velocity=[vx,vy,vz];self.mode=mode
        return hits,jumped
