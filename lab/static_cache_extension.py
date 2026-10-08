"""Add verified static convex collision without resetting locomotion."""
import hashlib
import json
from pathlib import Path
import time
import threading
from collections import OrderedDict
from types import SimpleNamespace

from .static_collision import from_export

ROOT=Path(__file__).resolve().parents[1]
REQUEST=ROOT/'data/static-cache-extension.json'


# Retain in-flight preparation across parser reloads. Geometry is immutable after
# construction; a version and exact byte hash prevent using a stale decoder.
if '_prepared_lock' not in globals():
    _prepared_lock=threading.Lock()
    _prepared=OrderedDict()
    _preparing=set()
if '_retained_lock' not in globals():
    _retained_lock=threading.Lock()
    _retained=OrderedDict()
    _retaining=set()


def retained_geometry(config,sources):
    """Prepare an accepted cache upgrade without blocking movement packets."""
    from .static_collision import GEOMETRY_VERSION
    snapshots=[(config['static_collision_snapshot'],config['static_collision_sha256'])]
    snapshots.extend((source['snapshot'],source['sha256']) for source in sources)
    key=(GEOMETRY_VERSION,str(ROOT.resolve()),tuple(snapshots))
    with _retained_lock:
        if key in _retained:
            value=_retained[key]
            if isinstance(value,str):raise ValueError(value)
            return value
        if _retaining:return None
        _retaining.add(key)
    def build():
        try:
            state=SimpleNamespace(static_meshes=[]);unsupported=[]
            for index,(name,digest) in enumerate(snapshots):
                path=(ROOT/name).resolve()
                if path.parent!=(ROOT/'evidence').resolve() or not path.name.endswith(f"_{config['pid']}.json"):
                    raise ValueError('local accepted collision snapshot required')
                raw=path.read_bytes()
                if hashlib.sha256(raw).hexdigest()!=digest:
                    raise ValueError('accepted static collision hash mismatch')
                meshes,errors=from_export(json.loads(raw))
                if index and errors:raise ValueError('accepted static extension no longer supported')
                if not index:unsupported=errors
                extend_meshes(state,meshes)
            value=(state.static_meshes,unsupported)
        except Exception as exc:value=str(exc)
        with _retained_lock:
            _retained[key]=value
            while len(_retained)>2:_retained.popitem(last=False)
            _retaining.discard(key)
    threading.Thread(target=build,name='retained-collision-preparation',daemon=True).start()
    return None


def preparation_key(raw):
    from .static_collision import GEOMETRY_VERSION
    return GEOMETRY_VERSION,hashlib.sha256(raw).hexdigest()


def remember_geometry(raw,meshes,errors):
    for mesh in meshes:signature(mesh)
    key=preparation_key(raw)
    with _prepared_lock:
        _prepared[key]=(meshes,errors)
        _prepared.move_to_end(key)
        while len(_prepared)>2:_prepared.popitem(last=False)
    return meshes,errors


def prepare_geometry(raw):
    meshes,errors=from_export(json.loads(raw))
    return remember_geometry(raw,meshes,errors)


def prepared_geometry(raw):
    """Return prepared shapes, or start one bounded background construction."""
    key=preparation_key(raw)
    with _prepared_lock:
        if key in _prepared:
            result=_prepared[key]
            if isinstance(result,str):raise ValueError(result)
            return result
        if key in _preparing or _preparing:return None
        _preparing.add(key)
    def build():
        try:prepare_geometry(raw)
        except Exception as exc:
            with _prepared_lock:
                _prepared[key]=str(exc)
                while len(_prepared)>2:_prepared.popitem(last=False)
        finally:
            with _prepared_lock:_preparing.discard(key)
    threading.Thread(target=build,name='static-collision-preparation',daemon=True).start()
    return None


def signature(mesh):
    if not hasattr(mesh,'_static_signature'):
        from .shared_collision import SharedCollision
        if isinstance(mesh,SharedCollision):
            mesh._static_signature=('shared',signature(mesh.source),mesh.matrix)
        else:
            mesh._static_signature=tuple(sorted(tuple(tuple(point) for point in triangle) for triangle, normal in mesh.faces))
    return mesh._static_signature


def extend_meshes(state, meshes):
    merged=list(state.static_meshes)
    existing={signature(mesh) for mesh in merged}
    for mesh in meshes:
        key=signature(mesh)
        if key not in existing:
            existing.add(key);merged.append(mesh)
    from .shared_collision import resident_faces
    if len(merged)>4096 or resident_faces(merged)>500000:
        raise ValueError('bounded static collision cache required')
    added=len(merged)-len(state.static_meshes)
    state.static_meshes=merged
    return added


def apply_request(connection,state,event):
    if not REQUEST.exists():return False
    from .static_collision import GEOMETRY_VERSION
    if getattr(connection,'static_collision_geometry_version',GEOMETRY_VERSION)!=GEOMETRY_VERSION:
        return False  # Keep old collision active until its atomic cache upgrade.
    request=json.loads(REQUEST.read_text())
    if set(request)!={'id','profile_id','connection_id','pawn_guid','base_static_sha256',
                       'snapshot','snapshot_sha256','expires_at'}:
        raise ValueError('exact static collision extension schema required')
    if (request['profile_id']!=getattr(connection,'terrain_experiment_id',None) or
            request['connection_id']!=connection.connection_id or
            request['pawn_guid']!=connection.actor_guids.get('pawn') or
            connection.phase!='joined' or not connection.possession_acknowledged):return False
    if request['id']==getattr(connection,'static_extension_id',None):return False
    if not isinstance(request['id'],str) or not request['id']:
        raise ValueError('static extension identity required')
    previous_id=getattr(connection,'static_extension_id',None)
    connection.static_extension_id=request['id']
    if not 0<request['expires_at']-time.time()<=120:
        raise ValueError('fresh static extension required')
    config=connection.terrain_experiment_config
    generation=getattr(connection,'static_extension_generation',config['static_collision_sha256'])
    if request['base_static_sha256']!=generation:
        raise ValueError('current static cache generation required')
    path=(ROOT/request['snapshot']).resolve()
    if path.parent!=(ROOT/'evidence').resolve() or not path.name.endswith(f"_{config['pid']}.json"):
        raise ValueError('local current-client static export required')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=request['snapshot_sha256']:
        raise ValueError('static extension hash mismatch')
    prepared=prepared_geometry(raw)
    if prepared is None:
        # Retry pending preparation on a later movement packet. Invalid or
        # expired requests remain consumed so they cannot flood rejection logs.
        connection.static_extension_id=previous_id
        return False
    report=json.loads(raw)
    from tools.protocol_proof import client_proof
    live=client_proof(config['pid']);proof=report.get('client_proof',{})
    if report.get('pid')!=config['pid'] or any(proof.get(key)!=live[key] for key in
            ('pid','exe','sha256','process_created_filetime')):
        raise ValueError('current native static export process identity required')
    observed=proof.get('observed_at')
    if type(observed) not in (int,float) or not 0<=time.time()-observed<=180:
        raise ValueError('fresh native static observation required')
    base_raw=(ROOT/config['static_collision_snapshot']).read_bytes()
    if hashlib.sha256(base_raw).hexdigest()!=config['static_collision_sha256']:
        raise ValueError('accepted static geometry hash required')
    base=json.loads(base_raw)
    if report.get('world')!=base['world'] or report.get('pawn')!=base['pawn']:
        raise ValueError('current accepted pawn world required')
    if not report['components'] or any(c.get('mobility')!=0 for c in report['components']):
        raise ValueError('native static mobility required; moving bodies need updates')
    meshes,unsupported=prepared
    if unsupported or not meshes:
        raise ValueError('fully supported exported static shapes required')
    added=extend_meshes(state,meshes)
    sources=list(getattr(connection,'static_cache_sources',()))
    source={'snapshot':request['snapshot'],'sha256':request['snapshot_sha256']}
    if source not in sources:sources.append(source)
    connection.static_cache_sources=sources
    connection.static_extension_generation=request['snapshot_sha256']
    event('static_cache_extended',{'id':request['id'],'connection_id':connection.connection_id,
        'profile_id':connection.terrain_experiment_id,'added_colliders':added,
        'total_colliders':len(state.static_meshes),'source':source,
        'physics_position':state.position.copy(),'physics_velocity':state.velocity.copy(),
        'physics_timestamp':state.timestamp,'physics_time_budget':state.time_budget})
    return bool(added)
