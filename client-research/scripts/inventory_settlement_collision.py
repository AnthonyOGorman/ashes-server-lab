"""Inventory existing settlement heightfields without admitting/modifying CPP terrain."""
import collections, hashlib, json
from pathlib import Path
R = Path(__file__).resolve().parents[1]
p = R.parent/'CPP/data/terrain-offline/decoded-other-worlds/manifest.json'
raw = p.read_bytes(); data = json.loads(raw)
catalog = json.loads((R/'proofs/settlement-placement-catalog.json').read_bytes())
groups = collections.defaultdict(list)
for tile in data['tiles']:
    groups[tile['package']].append(tile)
paths = sorted({a['path']['package'] for n in catalog['nodes']
    if n['world'] == 'Verra_World_Master'
    for s in n['tier1_props_candidates'] for d in s['definitions'] for a in d['assets']
    if '/Landscape_Platforms/' in a['path']['package']})
win = next(n for n in catalog['nodes'] if n['record_name'] == 'Verra_RVR_Winstead')
wp = '/Game/ENV/Nodes/Nodes_Master/Node_Sublevels/Landscape_Platforms/Layout_Flat_D/Landscape_Flat_D_Master_01'
tiles = groups[wp]; checked = 0; all_checked = 0; verified_paths = []
for package in paths:
    count=0
    for t in groups[package]:
        for key in ('heights','materials'):
            buf = (p.parent/t[key]).read_bytes()
            assert hashlib.sha256(buf).hexdigest() == t[key+'_sha256']
            count += 1
    all_checked += count
    verified_paths.append({'package':package,'tiles':len(groups[package]),'buffer_hashes_verified':count})
    if package==wp:checked=count
out = {'source':str(p),'source_sha256':hashlib.sha256(raw).hexdigest(),
    'all_tiles':len(data['tiles']),'all_candidate_buffer_hashes_verified':all_checked,'verified_candidate_paths':verified_paths,
    'verra_tier1_candidate_landscape_paths':[{'path':x,'cached_tiles':len(groups.get(x,[])),
        'solid_cells':sum(t.get('solid_cells',0) for t in groups.get(x,[]))} for x in paths],
    'winstead':{'node_id':win['record_id'],'origin_cm':win['location_cm'],
        'rotation_degrees':win['rotation_degrees'],'package':wp,'tiles':tiles,
        'buffer_hashes_verified':checked,'solid_cells':sum(t['solid_cells'] for t in tiles)},
    'limits':['Read-only inventory of CPP offline cache; no collision admission or CPP changes.',
        'Local transforms require proven settlement instance composition, not global local-origin admission.',
        'Material255 holes remain holes; this inventory does not establish live client loaded collision.']}
(R/'proofs/settlement-platform-collision-inventory.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps({'candidate_paths':len(paths),'cached_paths':sum(bool(groups.get(x)) for x in paths),
    'winstead_tiles':len(tiles),'solid_cells':out['winstead']['solid_cells'],'verified_buffers':checked,'all_candidate_buffers':all_checked},indent=2))
