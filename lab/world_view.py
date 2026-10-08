"""Read-only views of authoritative player state and admitted collision geometry."""
import base64
import math
import struct
import sys
import threading
import time
from urllib.parse import parse_qs, urlparse

_lock = threading.Lock()
_trails = {}


def snapshot(owner):
    players = []
    world = getattr(owner, 'world', None)
    if world is not None:
        with world.protocol_lock:
            for peer, connection in world.protocol.connections.items():
                state = getattr(connection, 'terrain_experiment', None)
                if connection.phase != 'joined' or state is None:
                    continue
                from .shared_collision import resident_faces
                players.append({'id': connection.connection_id, 'peer': str(peer),
                    'position': state.position.copy(), 'velocity': state.velocity.copy(),
                    'mode': state.mode, 'timestamp': state.timestamp,
                    'radius': state.radius, 'half_height': state.half_height,
                    'tiles': len(state.tiles), 'colliders': len(state.static_meshes),
                    'resident_faces':resident_faces(state.static_meshes),
                    'world_faces':sum(len(m.faces) for m in state.static_meshes),
                    'geometry_version':getattr(connection,'static_collision_geometry_version',None),
                    'geometry': [connection.terrain_manifest_hash,
                                 getattr(connection, 'static_extension_generation', '')]})
    with _lock:
        active = {p['id'] for p in players}
        for key in list(_trails):
            if key not in active:
                del _trails[key]
        for player in players:
            trail = _trails.setdefault(player['id'], [])
            if not trail or math.dist(trail[-1], player['position']) > 1:
                trail.append(player['position'].copy())
                del trail[:-600]
            player['trail'] = [point.copy() for point in trail]
    return {'observed_at': time.time(), 'players': players,
            'units': 'centimetres', 'source': 'authoritative server simulation'}


def geometry(owner, identifier, centre, radius=15000., stride=4, detail='light'):
    if len(centre) != 3 or not all(math.isfinite(v) for v in centre):
        raise ValueError('finite view centre required')
    if not 1000 <= radius <= 100000 or stride not in (1, 2, 4, 8, 16):
        raise ValueError('bounded view radius and terrain stride required')
    if detail not in ('light','full','bounds'):
        raise ValueError('supported collision display detail required')
    world = getattr(owner, 'world', None)
    if world is None:
        raise ValueError('no active server world')
    with world.protocol_lock:
        connections = [c for c in world.protocol.connections.values()
                       if c.connection_id == identifier and c.phase == 'joined']
        if len(connections) != 1 or getattr(connections[0], 'terrain_experiment', None) is None:
            raise ValueError('active player required')
        c = connections[0]; state = c.terrain_experiment
        tiles = list(state.tiles); meshes = list(state.static_meshes)
        generation = [c.terrain_manifest_hash, getattr(c, 'static_extension_generation', '')]
    # Coordinates are rebased before float32 encoding to avoid precision loss
    # at the large native world offsets. Geometry is immutable after admission.
    terrain = bytearray(); collision = bytearray(); bounds = []
    limits = {'terrain': 80000, 'collision': 180000 if detail=='full' else 20000}
    counts = {'terrain': 0, 'collision': 0}; clipped = {'terrain': False, 'collision': False}
    def line(target, kind, a, b):
        if counts[kind] >= limits[kind]:
            clipped[kind] = True
            return False
        target.extend(struct.pack('<6f', *[(p[i]-centre[i])/100 for p in (a, b) for i in range(3)]))
        counts[kind] += 1
        return True
    low = [centre[0]-radius, centre[1]-radius, -1e30]
    high = [centre[0]+radius, centre[1]+radius, 1e30]
    for tile in tiles:
        samples = [v[0] for v in struct.iter_unpack('<H', tile.heights)]
        min_z = tile.origin[2]+(tile.minimum+min(samples)*tile.quantization)*tile.scale[2]
        max_z = tile.origin[2]+(tile.minimum+max(samples)*tile.quantization)*tile.scale[2]
        bounds.append({'kind': 'terrain', 'minimum': [tile.origin[0],tile.origin[1],min_z], 'maximum':
            [tile.origin[0]+(tile.cols-1)*tile.scale[0],
             tile.origin[1]+(tile.rows-1)*tile.scale[1], max_z]})
        x0=max(0, math.floor((low[0]-tile.origin[0])/tile.scale[0]))
        y0=max(0, math.floor((low[1]-tile.origin[1])/tile.scale[1]))
        x1=min(tile.cols-2, math.floor((high[0]-tile.origin[0])/tile.scale[0]))
        y1=min(tile.rows-2, math.floor((high[1]-tile.origin[1])/tile.scale[1]))
        def vertex(x, y):
            return [tile.origin[0]+x*tile.scale[0], tile.origin[1]+y*tile.scale[1], tile.vertex(x,y)]
        for y in range(y0, y1+1, stride):
            for x in range(x0, x1+1, stride):
                ex=min(x+stride,tile.cols-1);ey=min(y+stride,tile.rows-1)
                # Never bridge a native landscape hole in the coarse display.
                if any(tile.materials[j*(tile.cols-1)+i] == 255
                       for j in range(y,ey) for i in range(x,ex)):
                    continue
                if not line(terrain,'terrain',vertex(x,y),vertex(ex,y)):
                    break
                line(terrain,'terrain',vertex(x,y),vertex(x,ey))
            if clipped['terrain']:
                break
    ordered=sorted(meshes,key=lambda m: sum(((m.minimum[i]+m.maximum[i])/2-centre[i])**2 for i in range(2)))
    nearby=sum(all(m.maximum[i]>=low[i] and m.minimum[i]<=high[i] for i in range(2)) for m in meshes)
    per_mesh=max(12,min(2000,(limits['collision']-12*nearby)//max(1,nearby)))
    sampled_meshes=0
    for index,mesh in enumerate(ordered):
        bounds.append({'kind': 'collision', 'index': index, 'minimum': mesh.minimum,
                       'maximum': mesh.maximum, 'faces': len(mesh.faces)})
        if clipped['collision'] or any(mesh.maximum[i]<low[i] or mesh.minimum[i]>high[i] for i in range(2)):
            continue
        if detail!='full':
            vertices=[[mesh.maximum[i] if n&(1<<i) else mesh.minimum[i] for i in range(3)] for n in range(8)]
            for n in range(8):
                for axis in range(3):
                    if not n&(1<<axis):line(collision,'collision',vertices[n],vertices[n|(1<<axis)])
        if detail=='bounds':continue
        sample_step=1 if detail=='full' else max(1,math.ceil(len(mesh.faces)*3/per_mesh))
        if sample_step>1:sampled_meshes+=1
        if detail=='full':
            faces=mesh.triangles(low,high)
        else:
            # Display samples reference real physics edges; no simplified mesh
            # replaces the server geometry, and every nearby body has a box.
            faces=(mesh.faces[j][0] for j in range(0,len(mesh.faces),sample_step)
                   if all(max(v[i] for v in mesh.faces[j][0])>=low[i] and
                          min(v[i] for v in mesh.faces[j][0])<=high[i] for i in range(2)))
        edges=set()
        for face in faces:
            for a,b in ((face[0],face[1]),(face[1],face[2]),(face[2],face[0])):
                key=tuple(sorted((tuple(a),tuple(b))))
                if key in edges:
                    continue
                edges.add(key)
                if not line(collision,'collision',a,b):
                    break
            if clipped['collision']:
                break
    return {'origin': centre, 'radius': radius, 'terrain_stride': stride,
        'collision_detail':detail,'sampled_meshes':sampled_meshes,'nearby_colliders':nearby,
        'generation': generation, 'bounds': bounds, 'segments': counts, 'clipped': clipped,
        'terrain': base64.b64encode(terrain).decode('ascii'),
        'collision': base64.b64encode(collision).decode('ascii'),
        'encoding': 'little-endian float32 XYZ line endpoints in metres relative to origin',
        'scope': 'admitted collision only; excluded or unexported objects are absent'}


def handle(handler):
    parsed=urlparse(handler.path)
    if parsed.path not in ('/api/world-view', '/api/world-geometry'):
        return False
    try:
        if parsed.path == '/api/world-view':
            handler.send(snapshot(handler.lab))
        else:
            query=parse_qs(parsed.query)
            centre=[float(query[key][0]) for key in ('x','y','z')]
            handler.send(geometry(handler.lab,query['player'][0],centre,
                float(query.get('radius',['15000'])[0]),int(query.get('stride',['4'])[0]),
                query.get('detail',['light'])[0]))
    except (ValueError,KeyError,TypeError) as exc:
        handler.send({'error':str(exc)},400)
    return True


def install(owner):
    """Add read-only routes to an existing dashboard without restarting services."""
    if owner is None:
        return
    module=sys.modules.get(type(owner).__module__)
    handler=getattr(module,'Handler',None)
    if handler is None or getattr(handler,'_world_view_installed',False):
        return
    previous=handler.do_GET
    def get(self):
        if not handle(self):
            previous(self)
    handler.do_GET=get
    handler._world_view_installed=True
