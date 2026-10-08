"""Proof-bound local terrain movement, scoped to one possessed connection."""
import hashlib
import json
import math
from pathlib import Path
import time

from .terrain import Heightfield
from .terrain_movement import TerrainMovement
from .movement_response import encode_move_ack_content, encode_move_correction_content

ROOT=Path(__file__).resolve().parents[1]
PROFILE=ROOT/'data/terrain-movement-experiment.json'


def current_generation_moves(moves):
    current=[m for m in moves if m.get('kind')=='new']
    if current:
        # A pending move can never be newer than this packet's new move.
        # Numerically larger pending clocks belong to the previous240s epoch.
        newest=max(m['timestamp'] for m in current)
        return [m for m in moves if m['timestamp']<=newest]
    return moves


def profile_active(connection, config, peer, now):
    """A continuous profile expires before activation, never mid-jump.

    Retaining authority requires the same acknowledged pawn and profile ID.
    Removing the profile or closing the connection withdraws authority.
    """
    if (config['peer']!=list(peer) or config['connection_id']!=connection.connection_id
            or connection.phase!='joined'):
        return False
    if config['pawn_guid']!=connection.actor_guids.get('pawn') or not connection.possession_acknowledged:
        return False
    retained=(getattr(connection,'terrain_experiment_id',None)==config['id']
              and getattr(connection,'terrain_experiment',None) is not None
              and getattr(connection,'terrain_experiment_config',None)==config)
    if retained and config['mode']=='connection-landscape-locomotion-v1':
        return True
    return 0<config['expires_at']-now<=120


def initialize(connection, peer):
    if not PROFILE.exists():
        return None
    config=json.loads(PROFILE.read_text())
    required={'mode','id','peer','connection_id','pawn_guid','pid','expires_at',
              'cache_snapshot','actor_snapshot','terrain_manifest','terrain_sha256','spawn','stats_mapping_snapshot'}
    mesh_keys={'static_collision_snapshot','static_collision_sha256'}
    if set(config) not in (required,required|mesh_keys) or config['mode'] not in ('bounded-landscape-locomotion-v1','connection-landscape-locomotion-v1'):
        raise ValueError('exact terrain experiment schema required')
    if not profile_active(connection,config,peer,time.time()):
        return None
    if config['pawn_guid']!=connection.actor_guids.get('pawn') or not connection.possession_acknowledged:
        raise ValueError('current acknowledged pawn required')
    if (getattr(connection,'terrain_experiment_id',None)==config['id']
            and getattr(connection,'terrain_experiment_config',None)==config):
        state=getattr(connection,'terrain_experiment',None)
        if state is not None:
            # Parser hot reload preserves position, clock and wall-time budget.
            # Refresh method code on the retained state, without reinitializing
            # physics or allowing a fresh time allowance mid-jump.
            state.__class__=TerrainMovement
            for tile in state.tiles:
                tile.__class__=Heightfield
            from .static_collision import ConvexCollision, GEOMETRY_VERSION, from_export
            if mesh_keys<=set(config) and getattr(connection,'static_collision_geometry_version',None)!=GEOMETRY_VERSION:
                from .static_cache_extension import retained_geometry
                prepared=retained_geometry(config,list(getattr(connection,'static_cache_sources',())))
                if prepared is not None:
                    state.static_meshes,connection.static_collision_unsupported=prepared
                    connection.static_collision_geometry_version=GEOMETRY_VERSION
            for mesh in getattr(state,'static_meshes',()):
                if getattr(mesh,'_shared_collision',False):
                    from .shared_collision import SharedCollision
                    mesh.__class__=SharedCollision
                elif getattr(mesh,'_geometry_kind',None)=='triangle':
                    from .triangle_collision import TriangleCollision
                    mesh.__class__=TriangleCollision
                else:mesh.__class__=ConvexCollision
        return state
    from tools.protocol_proof import proof_paths,validate_current_client_proofs
    pid,cp,ap=proof_paths(ROOT,config['cache_snapshot'],config['actor_snapshot'])
    if pid!=config['pid']:
        raise ValueError('matching current PID required')
    cache,actors=[json.loads(p.read_text()) for p in (cp,ap)]
    validate_current_client_proofs(pid,cache,actors)
    matches=[m for m in actors['network_guid_actor_matches'] if m['guid']==config['pawn_guid']]
    pawn=next((p for p in actors['pawns'] if matches and p['address']==matches[0]['actor']['address']),None)
    if actors['errors'] or not pawn or pawn['network_roles']['Role']!=2 or not pawn['controller']:
        raise ValueError('accepted autonomous possessed pawn required')
    if math.dist(pawn['root_component']['unattached_location'],config['spawn'])>0.1:
        raise ValueError('initial server spawn must match observed candidate placement')
    caches={c['cache']:c for c in cache['candidate_caches']}
    cursor=next(c for c in caches.values() if c['class']=='PlayerPawn_C')
    if cursor['normal_rpc_field_maximum']!=198:
        raise ValueError('exact pawn RPC maximum required')
    found=False;seen=set()
    while cursor:
        if cursor['cache'] in seen:
            raise ValueError('cache inheritance cycle')
        seen.add(cursor['cache'])
        if not cursor.get('header_weak_class_matches') or not cursor.get('fields_base_matches'):
            raise ValueError('unverified RPC cache')
        found|=any(f['name']=='ClientMoveResponsePacked' and f['field_net_index']==35
                   and f['kind']=='UFunction' for f in cursor['fields'])
        cursor=caches.get(cursor.get('super_cache'))
    if not found:
        raise ValueError('exact client correction RPC required')
    expected_mapping=f'evidence/stats_mapping_{pid}.json'
    if config['stats_mapping_snapshot']!=expected_mapping:
        raise ValueError('fixed current stats mapping proof required')
    stats=json.loads((ROOT/expected_mapping).read_text())
    validate_current_client_proofs(pid,actors,stats)
    if (stats['component']['outer_address']!=pawn['address'] or
            stats['accepted_component_guids']!=[connection.actor_guids.get('stats')] or
            stats.get('gravity_value_bits')!=0x3f000000 or
            stats.get('movement_speed_value_bits')!=0x3fd47ae1):
        raise ValueError('exact applied gravity/speed stats on this pawn required')
    manifest=(ROOT/config['terrain_manifest']).resolve()
    if not manifest.is_relative_to((ROOT/'evidence').resolve()) or manifest.name!='manifest.json':
        raise ValueError('local evidence terrain manifest required')
    raw=manifest.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=config['terrain_sha256']:
        raise ValueError('terrain manifest hash mismatch')
    data=json.loads(raw);tiles=[]
    if any(data['client_proof'][k]!=actors['client_proof'][k] for k in
           ('pid','exe','sha256','process_created_filetime')):
        raise ValueError('terrain source client mismatch')
    for tile in data['tiles']:
        buffers=[]
        for key in ('heights','materials'):
            path=(manifest.parent/tile[key]).resolve()
            if path.parent!=manifest.parent:
                raise ValueError('terrain data must be sibling files')
            buf=path.read_bytes()
            if hashlib.sha256(buf).hexdigest()!=tile[key+'_sha256']:
                raise ValueError('terrain sample hash mismatch')
            buffers.append(buf)
        tiles.append(Heightfield(tile['rows'],tile['cols'],tile['origin'],tile['scale'],
                     tile['minimum'],tile['quantization'],*buffers))
    # Match the independently observed initialized pawn: 996cm/s horizontal
    # limit, gravity2.5*0.5*-980, 96cm capsule, and native floor clearance2.15.
    meshes=[];unsupported=[]
    if mesh_keys<=set(config):
        from .static_collision import from_export
        path=(ROOT/config['static_collision_snapshot']).resolve()
        if path.parent!=(ROOT/'evidence').resolve() or not path.name.endswith(f'_{pid}.json'):
            raise ValueError('fixed local current-client collision export required')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=config['static_collision_sha256']:
            raise ValueError('static collision export hash mismatch')
        report=json.loads(raw)
        validate_current_client_proofs(pid,actors,report)
        if report['pawn']['address']!=pawn['address']:
            raise ValueError('static collision must belong to the current pawn world')
        meshes,unsupported=from_export(report)
    state=TerrainMovement(tiles,config['spawn'],speed=996.,gravity=-1225.,
                          half_height=96.,radius=22.,floor_clearance=2.15,static_meshes=meshes)
    connection.static_collision_unsupported=unsupported
    from .static_collision import GEOMETRY_VERSION
    connection.static_collision_geometry_version=GEOMETRY_VERSION
    connection.static_cache_sources=[]
    connection.static_extension_generation=config.get('static_collision_sha256')
    connection.terrain_experiment=state
    connection.terrain_experiment_id=config['id']
    connection.terrain_experiment_config=config
    connection.terrain_experiment_expires=config['expires_at']
    connection.terrain_manifest_hash=config['terrain_sha256']
    return state


def responses(connection,peer,decoded,event):
    received_at=time.monotonic()
    if not PROFILE.exists():
        return []
    state=initialize(connection,peer)
    if state is None:
        return []
    from .terrain_cache_extension import apply_request as extend_terrain
    try:
        extend_terrain(connection,state,event)
    except (ValueError,TypeError,KeyError,OSError) as exc:
        event('terrain_cache_extension_rejected',{'reason':str(exc)})
    from .static_cache_extension import apply_request as extend_static
    try:
        extend_static(connection,state,event)
    except (ValueError,TypeError,KeyError,OSError) as exc:
        event('static_cache_extension_rejected',{'reason':str(exc)})
    from .terrain_relocation import apply_request
    try:
        relocated=apply_request(connection,state,event)
    except (ValueError,TypeError) as exc:
        event('terrain_relocation_rejected',{'reason':str(exc)})
        relocated=False
    moves=[m for f in decoded['fields'] for m in f.get('movement',{}).get('moves',[])]
    current=[m for m in moves if m.get('kind')=='new']
    moves=current_generation_moves(moves)
    if state.timestamp is None and moves:
        # Attaching to a running client must not use an old saved/pending move
        # as the new session's clock origin.
        current=[m for m in moves if m.get('kind')=='new']
        moves=[max(current or moves,key=lambda m:m['timestamp'])]
    payloads=[]
    for move in sorted(moves,key=lambda m:m['timestamp']):
        try:
            result=state.advance(move,received_at)
        except ValueError as exc:
            event('terrain_movement_rejected',{'connection_id':connection.connection_id,'reason':str(exc)})
            continue
        if result is None:
            continue
        correction=(relocated or 'discarded_time' in result or math.dist(move['client_location'],state.position)>1.)
        payload=(encode_move_correction_content(move['timestamp'],state.position,state.velocity,state.mode)
                 if correction else encode_move_ack_content(move['timestamp']))
        payloads.append(payload)
        event('terrain_movement_processed',{'connection_id':connection.connection_id,
            'pawn_guid':connection.actor_guids['pawn'],'input_acceleration':move['acceleration'],
            'response':'correction' if correction else 'ack','terrain_sha256':connection.terrain_manifest_hash,
            'experiment_id':connection.terrain_experiment_id,
            'static_collision_colliders':len(getattr(state,'static_meshes',())),
            'static_collision_triangles':sum(len(mesh.faces) for mesh in getattr(state,'static_meshes',())),
            'static_collision_unsupported':len(getattr(connection,'static_collision_unsupported',())),
            'movement_proved':False,**result})
    return payloads
