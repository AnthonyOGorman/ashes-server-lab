"""Bound simple native floor-instance composition for the filtered Crossroads catalog, offline only."""
import hashlib,json,math
from pathlib import Path
R=Path(__file__).resolve().parents[1];sources=[R/'proofs/settlement-crossroads-profile.json',R/'proofs/settlement-platform-collision-inventory.json']
profile,cache=[json.loads(p.read_bytes()) for p in sources]
identity={'quaternion':[0.,0.,0.,1.],'translation':[0.,0.,0.],'scale':[1.,1.,1.]}
paths={x['package']:x for x in cache['verified_candidate_paths']};instances=[];without=[]
for node in profile['nodes']:
 count=0
 for prop in node['props']:
  for definition in prop['selected_definitions']:
   for asset in definition['assets']:
    path=asset['path']['package']
    if '/Landscape_Platforms/' not in path:continue
    assert asset['inventory_classes']==['World'] and path in paths
    pt=prop['item_transform'];assert pt['quaternion']==identity['quaternion'] and pt['scale']==identity['scale']
    assert definition['transform']==identity and node['rotation_degrees'][0]==node['rotation_degrees'][2]==0.
    yaw=node['rotation_degrees'][1]*math.pi/180.;c,s=math.cos(yaw),math.sin(yaw)
    local=pt['translation'];origin=node['origin_cm']
    expected=[origin[0]+c*local[0]-s*local[1],origin[1]+s*local[0]+c*local[1],origin[2]+local[2]]
    for instance in asset['instances']:
     assert instance['Transform']==identity
     instances.append({'node_id':node['node_id'],'name':node['name'],'layout_id':node['layout_id'],
      'owner_guid':prop['owner_guid'],'owner_secondary_id':prop['owner_secondary_id'],
      'owner_array_index':prop['owner_array_index'],'assetset_record_guid':prop['assetset_record_guid'],
      'definition_id':definition['definition_id'],'path':asset['path'],'item_transform':pt,
      'definition_transform':definition['transform'],'instance_transform':instance['Transform'],
      'citynode_origin_cm':origin,'citynode_rotation_degrees':node['rotation_degrees'],
      'expected_world_origin_cm':expected,'expected_world_rotation_degrees':node['rotation_degrees'],
      'expected_world_scale':[1.,1.,1.],'cache':paths[path],
      'purpose_review_required':node['purpose_review_required'],'live_admitted':False})
     count+=1
 if not count:without.append({'node_id':node['node_id'],'name':node['name'],'layout_name':node['layout_name']})
assert len(instances)==26
out={'sources':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sources],
 'native_provenance':['6588CD0/40E7F40 positive-scale composition','65A25A0 CityNode placement','4189470 unit-scale World instance'],
 'instances':instances,'nodes_without_selected_landscape_platform':without,
 'limits':['Offline expected placement for the asserted identity quaternion/unit scale subset; not a general FTransform implementation.',
 'Live native transform/contact admission remains per-instance; no CPP source/configuration changes here.',
 'Layouts without a selected landscape may use static mesh/base-world floor; no invented generic ground.']}
(R/'proofs/settlement-landscape-instances.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps({'instances':len(instances),'without_selected_landscape':len(without),'nonzero_local_translations':sum(x['item_transform']['translation']!=identity['translation'] for x in instances)},indent=2))
