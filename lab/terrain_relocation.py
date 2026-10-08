"""Explicit local test placement, checked against the active collision world."""
import copy
import json
import math
from pathlib import Path
import time

from .capsule_sweep import segment_triangle_distance

REQUEST=Path(__file__).resolve().parents[1]/'data/terrain-relocation-experiment.json'


def validated_position(state, position):
    if len(position)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in position):
        raise ValueError('finite test placement required')
    probe=copy.copy(state);probe.position=list(position)
    floor=probe.floor(*position[:2])
    if floor is None or abs(position[2]-floor)>.1:
        raise ValueError('test placement must match a supported walkable capsule floor')
    low=[position[0]-state.radius,position[1]-state.radius,position[2]-state.half_height]
    high=[position[0]+state.radius,position[1]+state.radius,position[2]+state.half_height]
    segment=state.half_height-state.radius
    start=[position[0],position[1],position[2]-segment]
    end=[position[0],position[1],position[2]+segment]
    # Surface distance alone also passes a capsule buried deep inside a hull.
    # Crossing its boundary is caught below; fully contained segments need an
    # explicit solid-volume check before considering triangle clearance.
    for mesh in getattr(state,'static_meshes',()):
        if mesh.contains_point(position):
            raise ValueError('test placement lies inside solid collision')
    for source in (*state.tiles,*getattr(state,'static_meshes',())):
        for triangle in source.triangles(low,high):
            if segment_triangle_distance(start,end,triangle)[0]<state.radius-.001:
                raise ValueError('test placement overlaps loaded collision')
    return list(position)


def apply_request(connection,state,event):
    if not REQUEST.exists():return False
    request=json.loads(REQUEST.read_text())
    keys={'id','profile_id','connection_id','pawn_guid','position','expires_at'}
    if set(request)!=keys:raise ValueError('exact local test placement schema required')
    if (request['profile_id']!=getattr(connection,'terrain_experiment_id',None) or
            request['connection_id']!=connection.connection_id or
            request['pawn_guid']!=connection.actor_guids.get('pawn') or
            connection.phase!='joined' or not connection.possession_acknowledged):return False
    if request['id']==getattr(connection,'terrain_relocation_id',None):return False
    connection.terrain_relocation_id=request['id']
    try:
        if not isinstance(request['id'],str) or not request['id'] or not 0<request['expires_at']-time.time()<=120:
            raise ValueError('fresh explicit test placement required')
        target=validated_position(state,request['position'])
    except ValueError as exc:
        event('terrain_relocation_rejected',{'id':request['id'],'reason':str(exc)})
        return False
    old=state.position.copy()
    state.position=target;state.velocity=[0.,0.,0.];state.mode=1;state.jump_pressed=False
    event('terrain_relocation_applied',{'id':request['id'],'connection_id':connection.connection_id,
          'profile_id':connection.terrain_experiment_id,'previous_position':old,'position':target,
          'timestamp':state.timestamp,'time_budget':state.time_budget,'client_placement_verified':False})
    return True
