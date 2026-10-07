"""Attach verified collision admission to the decoded Verra terrain manifests.

Unknown archive overrides fail closed. This installed build's landscape actors
all inherit BlockAll / QueryAndPhysics from build-matched native defaults.
"""
import json,pathlib,hashlib
from collections import defaultdict,deque
root=pathlib.Path(__file__).resolve().parents[1]
base=root/'data/terrain-offline'
meta=json.loads((base/'collision-metadata.json').read_text())
defaults=json.loads((base/'collision-defaults.json').read_text())
config=json.loads((root/'config/backend.json').read_text())
if meta['failures']:raise ValueError('Incomplete landscape collision metadata')
if defaults['proof']['sha256']!=config['client_sha256']:raise ValueError('Landscape default build differs')
classes={r['class']:r for r in defaults['records']}
identities=defaultdict(deque)
for r in meta['records']:
    key=(r['package'],r['cls'],r['name'])
    identities[key].append(r) # Package export order disambiguates repeated names.
loaded=0
pending=[]
for folder,array in [('decoded','tiles'),('decoded-mesh','meshes')]:
    path=base/folder/'manifest.json';manifest=json.loads(path.read_text())
    for tile in manifest[array]:
        tile.setdefault('cls','LandscapeHeightfieldCollisionComponent' if array=='tiles' else 'LandscapeMeshCollisionComponent')
        key=(tile['package'],tile['cls'],tile['name'])
        if not identities[key]:raise ValueError('Collision component metadata missing')
        record=identities[key].popleft();default=classes[record['owner_cls']]
        if record['body_json'] is not None:raise ValueError('Unreviewed landscape collision override')
        if default['collision_profile']!='BlockAll' or default['collision_enabled_value']!=3 or not default['actor_enabled']:raise ValueError('Unreviewed landscape collision defaults')
        # The native class defaults apply when the archive has no override.
        tile['collision_query_enabled']=record['actor_enabled']
        tile['collision_profile']='BlockAll'
        tile['collision_owner']=record['owner']
        tile['collision_owner_class']=record['owner_cls']
        loaded+=int(record['actor_enabled'])
    manifest['collision_admission']={'status':'verified','exe_sha256':config['client_sha256'],'metadata_sha256':hashlib.sha256((base/'collision-metadata.json').read_bytes()).hexdigest(),'defaults_sha256':hashlib.sha256((base/'collision-defaults.json').read_bytes()).hexdigest(),'method':'archive actor overrides and read-only build-matched native class defaults'}
    pending.append((path,manifest))
if any(identities.values()):raise ValueError('Collision metadata coverage differs')
for path,manifest in pending:path.write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'status':'verified','collision_components':len(meta['records']),'enabled':loaded,'disabled':len(meta['records'])-loaded}))
