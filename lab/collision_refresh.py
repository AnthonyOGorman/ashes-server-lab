"""Session-scoped native collision refresh using the existing guarded exporters."""
import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import threading
import time
import uuid

from .world_initialization import ready_entry,still_current,run_stage
from .terrain import Heightfield
from .terrain_cache_extension import slot,content
from .static_cache_extension import signature,remember_geometry
from .static_collision import from_export

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'data/auto-collision-refresh.json'


def read_config():
    if not CONFIG.exists():return None
    config=json.loads(CONFIG.read_text())
    if config.get('enabled') is not True:return None
    if (set(config)!={'enabled','pid','sha256','interval_seconds','distance_cm'} or
            type(config['pid']) is not int or not isinstance(config['sha256'],str) or
            type(config['interval_seconds']) not in (int,float) or
            not 15<=config['interval_seconds']<=300 or
            type(config['distance_cm']) not in (int,float) or
            not 100<=config['distance_cm']<=10000):
        raise ValueError('bounded exact collision refresh configuration required')
    return config


def current_entry(owner,config):
    entry=ready_entry(owner,{k:config[k] for k in ('enabled','pid','sha256')})
    if not entry or not entry['initialized']:return None
    with owner.world.protocol_lock:
        c=owner.world.protocol.connections.get(('127.0.0.1',entry['port']))
        if not c or c.connection_id!=entry['connection_id']:return None
        state=c.terrain_experiment;profile=c.terrain_experiment_config
        entry.update(profile_id=profile['id'],pawn_guid=c.actor_guids['pawn'],
                     pawn=json.loads((ROOT/profile['static_collision_snapshot']).read_text())['pawn']['address'],
                     position=state.position.copy())
    return entry


def due(entry,last,now,config):
    return (last is None or last['connection_id']!=entry['connection_id'] or
            now-last['completed_at']>=config['interval_seconds'] or
            math.dist(entry['position'][:2],last['position'][:2])>=config['distance_cm'])


def new_tiles(state,manifest):
    """Count terrain additions independently of expensive static geometry."""
    known={slot(t):content(t) for t in state.tiles};added_tiles=0
    data=json.loads(manifest.read_text())
    for t in data['tiles']:
        buffers=[(manifest.parent/t[k]).read_bytes() for k in ('heights','materials')]
        tile=Heightfield(t['rows'],t['cols'],t['origin'],t['scale'],
                         t['minimum'],t['quantization'],*buffers)
        key=slot(tile)
        if key in known and known[key]!=content(tile):
            raise ValueError('conflicting cached native terrain samples')
        if key not in known:added_tiles+=1;known[key]=content(tile)
    return added_tiles


def new_geometry(state,manifest,report,raw=None):
    """Find additions without changing physics or accepting conflicting terrain."""
    added_tiles=new_tiles(state,manifest)
    existing={signature(m) for m in state.static_meshes}
    meshes,errors=from_export(report)
    if errors:raise ValueError('refresh snapshot must contain supported geometry only')
    additions=sum(signature(m) not in existing for m in meshes)
    if raw is not None:remember_geometry(raw,meshes,errors)
    return added_tiles,additions


def publish_terrain(owner,entry,result):
    """Queue completed native heightfields before static export/construction."""
    if not read_config() or not still_current(owner,entry):
        raise ValueError('current enabled refresh session required')
    manifest=(ROOT/result['manifest']).resolve()
    if not manifest.is_relative_to((ROOT/'evidence').resolve()) or manifest.name!='manifest.json':
        raise ValueError('local native terrain manifest required')
    path=ROOT/'data/terrain-cache-extension.json'
    with owner.world.protocol_lock:
        c=owner.world.protocol.connections.get(('127.0.0.1',entry['port']))
        if (not c or c.connection_id!=entry['connection_id'] or c.phase!='joined' or
                not c.possession_acknowledged or c.terrain_experiment_id!=entry['profile_id'] or
                c.actor_guids.get('pawn')!=entry['pawn_guid']):
            raise ValueError('current acknowledged refresh pawn required')
        if path.exists():raise ValueError('existing terrain extension must finish first')
        target=c;generation=c.terrain_manifest_hash
        state=copy.copy(c.terrain_experiment);state.tiles=list(state.tiles)
        existing=tuple(map(id,state.tiles))
    added=new_tiles(state,manifest)
    if not added:return []
    digest=hashlib.sha256(manifest.read_bytes()).hexdigest()
    if not read_config() or not still_current(owner,entry):
        raise ValueError('current enabled refresh session required')
    with owner.world.protocol_lock:
        c=owner.world.protocol.connections.get(('127.0.0.1',entry['port']))
        if (c is not target or c.connection_id!=entry['connection_id'] or c.phase!='joined' or
                not c.possession_acknowledged or c.terrain_experiment_id!=entry['profile_id'] or
                c.actor_guids.get('pawn')!=entry['pawn_guid'] or
                c.terrain_manifest_hash!=generation or tuple(map(id,c.terrain_experiment.tiles))!=existing):
            raise ValueError('terrain session or cache changed during preparation')
        if path.exists():raise ValueError('existing terrain extension must finish first')
        request={'id':uuid.uuid4().hex,'profile_id':entry['profile_id'],
            'connection_id':entry['connection_id'],'pawn_guid':entry['pawn_guid'],
            'base_terrain_sha256':generation,'manifest':result['manifest'],
            'manifest_sha256':digest,'expires_at':time.time()+115.}
        temporary=path.with_suffix('.json.tmp');temporary.write_text(json.dumps(request));temporary.replace(path)
    owner.event('collision_refresh_terrain_ready',dict(entry,manifest=result['manifest'],
        new_tiles=added,request_id=request['id'],static_export_complete=False))
    return [(path,request)]


def stage_progress(owner,entry,name,arguments,directory):
    if name!='export' or not arguments or arguments[0]!='tools/refresh_streamed_collision.py':
        return
    marker=directory/'terrain-ready.json'
    if not marker.exists():return
    completed=getattr(owner,'terrain_ready_stages',set())
    key=str(directory)
    if key in completed:return
    result=json.loads(marker.read_text())
    requests=publish_terrain(owner,entry,result)
    if requests:finish_requests(owner,entry,requests)
    completed.add(key)
    # This tracks only recent stage paths, never physics or native identities.
    owner.terrain_ready_stages=completed if len(completed)<=64 else {key}


def publish(owner,entry,result):
    if not read_config() or not still_current(owner,entry):
        raise ValueError('current enabled refresh session required')
    with owner.world.protocol_lock:
        c=owner.world.protocol.connections.get(('127.0.0.1',entry['port']))
        if (not c or c.connection_id!=entry['connection_id'] or c.phase!='joined' or
                not c.possession_acknowledged or c.terrain_experiment_id!=entry['profile_id'] or
                c.actor_guids.get('pawn')!=entry['pawn_guid']):
            raise ValueError('current acknowledged refresh pawn required')
        terrain_request=ROOT/'data/terrain-cache-extension.json'
        static_request=ROOT/'data/static-cache-extension.json'
        if terrain_request.exists() or static_request.exists():
            raise ValueError('existing collision extension request must finish first')
        # Geometry construction can take seconds for cooked triangle meshes.
        # Snapshot immutable geometry references while holding the protocol lock,
        # then build/query the incoming export without stopping movement packets.
        target=c
        state=copy.copy(c.terrain_experiment)
        state.tiles=list(getattr(state,'tiles',()))
        state.static_meshes=list(getattr(state,'static_meshes',()))
        generation=(c.terrain_manifest_hash,c.static_extension_generation)
        existing=(tuple(map(id,state.tiles)),tuple(map(id,state.static_meshes)))
    manifest=ROOT/result['manifest'];snapshot=ROOT/result['snapshot']
    raw=snapshot.read_bytes()
    report=json.loads(raw)
    tiles,meshes=new_geometry(state,manifest,report,raw)
    if not read_config() or not still_current(owner,entry):
        raise ValueError('current enabled refresh session required')
    with owner.world.protocol_lock:
        c=owner.world.protocol.connections.get(('127.0.0.1',entry['port']))
        if (c is not target or c.connection_id!=entry['connection_id'] or c.phase!='joined' or
                not c.possession_acknowledged or c.terrain_experiment_id!=entry['profile_id'] or
                c.actor_guids.get('pawn')!=entry['pawn_guid']):
            raise ValueError('current acknowledged refresh pawn required')
        current=(tuple(map(id,getattr(c.terrain_experiment,'tiles',()))),
                 tuple(map(id,getattr(c.terrain_experiment,'static_meshes',()))))
        if (generation!=(c.terrain_manifest_hash,c.static_extension_generation) or
                existing!=current):
            raise ValueError('collision cache changed during refresh preparation')
        if terrain_request.exists() or static_request.exists():
            raise ValueError('existing collision extension request must finish first')
        common={'profile_id':entry['profile_id'],'connection_id':entry['connection_id'],
                'pawn_guid':entry['pawn_guid'],'expires_at':time.time()+115.}
        requests=[]
        if tiles:
            requests.append((terrain_request,dict(common,id=uuid.uuid4().hex,
                base_terrain_sha256=c.terrain_manifest_hash,manifest=result['manifest'],
                manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest())))
        if meshes:
            requests.append((static_request,dict(common,id=uuid.uuid4().hex,
                base_static_sha256=c.static_extension_generation,snapshot=result['snapshot'],
                snapshot_sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest())))
        for path,request in requests:
            temporary=path.with_suffix('.json.tmp')
            temporary.write_text(json.dumps(request,indent=2));temporary.replace(path)
        owner.event('collision_refresh_exported',dict(entry,**result,
            new_tiles=tiles,new_colliders=meshes,request_ids=[r['id'] for _,r in requests]))
        return requests


def finish_requests(owner,entry,requests):
    """Wait only for our IDs; never overwrite or remove another request."""
    deadline=time.monotonic()+20
    while requests and still_current(owner,entry) and time.monotonic()<deadline:
        with owner.world.protocol_lock:
            c=owner.world.protocol.connections.get(('127.0.0.1',entry['port']))
            consumed={getattr(c,'terrain_extension_id',None),getattr(c,'static_extension_id',None)}
        if all(r['id'] in consumed for _,r in requests):break
        time.sleep(.25)
    accepted=True
    with owner.world.protocol_lock:
        c=owner.world.protocol.connections.get(('127.0.0.1',entry['port']))
        for path,request in requests:
            generation=(getattr(c,'terrain_manifest_hash',None) if 'manifest' in request
                        else getattr(c,'static_extension_generation',None))
            expected=request.get('manifest_sha256',request.get('snapshot_sha256'))
            accepted &= generation==expected
    for path,request in requests:
        if path.exists() and json.loads(path.read_text()).get('id')==request['id']:
            path.unlink()
    if not accepted:raise ValueError('collision refresh extension rejected or not consumed')
    owner.event('collision_refresh_completed',{'connection_id':entry['connection_id'],
                                              'request_ids':[r['id'] for _,r in requests]})


def worker(owner):
    last=None
    while True:
        entry=None
        try:
            config=read_config()
            if not config:return
            entry=current_entry(owner,config)
            if entry and due(entry,last,time.monotonic(),config):
                directory=ROOT/'evidence'/f'collision_refresh_{uuid.uuid4().hex}'
                directory.mkdir(parents=True,exist_ok=True)
                owner.event('collision_refresh_started',entry)
                run_stage(owner,entry,'export',['tools/refresh_streamed_collision.py',
                    '--pid',str(entry['pid']),'--pawn',entry['pawn'],
                    '--x',str(entry['position'][0]),'--y',str(entry['position'][1]),
                    '--output',str(directory)],directory)
                result=json.loads((directory/'result.json').read_text())
                requests=publish(owner,entry,result)
                finish_requests(owner,entry,requests)
                last=dict(entry,completed_at=time.monotonic())
        except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:
            owner.event('collision_refresh_failed',{'connection_id':entry['connection_id'] if entry else None,
                                                  'reason':str(exc)})
            # Bound retries even for a persistent native/export conflict.
            if entry:last=dict(entry,completed_at=time.monotonic())
        time.sleep(2)


def ensure_worker(owner):
    if owner is None or not hasattr(owner,'world') or read_config() is None:return None
    owner.stage_progress=lambda entry,name,args,directory:stage_progress(owner,entry,name,args,directory)
    previous=getattr(owner,'collision_refresh_thread',None)
    if previous is not None and previous.is_alive():return previous
    thread=threading.Thread(target=worker,args=(owner,),name='native-collision-refresh',daemon=True)
    owner.collision_refresh_thread=thread;thread.start()
    return thread
