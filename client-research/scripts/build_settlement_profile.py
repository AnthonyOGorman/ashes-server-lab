"""Resolve exact Crossroads/Kaelar/Spring/empty-tags props and correlate historical service owners."""
import collections,hashlib,json,sqlite3
from pathlib import Path
R=Path(__file__).resolve().parents[1]
files=[R/'proofs/settlement-records-live.json',R/'proofs/settlement-service-records-live.json',R/'proofs/settlement-winstead-capture-decoded.json']
base,services,capture=[json.loads(x.read_bytes()) for x in files]
assert base['proof']['sha256']==services['proof']['sha256']==capture['native_binding_lifetime']['sha256']
idx={k:{x['record_id']:x for x in v['records']} for doc in (base,services) for k,v in doc['records'].items()}
db=sqlite3.connect((R/'index/client-index.sqlite').as_uri()+'?mode=ro',uri=True)
def choose(assetset_id,node):
 out=[]
 for item in idx['NodeAssetSet'][assetset_id]['fields']['ContainedAssetDefinitions']['items']:
  definition=idx['NodeAssetDefinition'][item['Asset']['record_id']];f=definition['fields']
  tags=f['ValidGameplayTags'];assert tags['status']=='unsupported_reflected_type'
  raw=bytes.fromhex(tags['raw']);assert len(raw)==32;tagcount=int.from_bytes(raw[8:12],'little',signed=True);assert 0<=tagcount<=1024
  if not (f['NodeLevelMinimum']<=1<=f['NodeLevelMaximum'] and 0 in f['ValidCultures']['items'] and 1 in f['ValidSeasons']['items'] and node['node_type'] in f['ValidNodeTypes']['items'] and (f['bAllBiomes'] or node['biome'] in f['ValidBiomes']['items']) and tagcount==0):continue
  assets=[]
  for entry in f['ContainedAssets']['items']:
   path=entry['key'];rows=db.execute('SELECT DISTINCT cls FROM assets WHERE package=? AND name=?',(path['package'],path['asset'])).fetchall()
   assets.append({'path':path,'inventory_classes':[x[0] for x in rows],
    'instances':entry['value']['InstanceData']['items']})
  out.append({'definition_id':definition['record_id'],'name':definition['name'],'transform':item['Transform'],'assets':assets})
 return out
nodes=[];purposes=collections.Counter()
for node in idx['CityNode'].values():
 f=node['fields']
 if f['mapName']!='Verra_World_Master' or f['LayoutId']['record_id']=='0x0':continue
 zoi=idx['ZOI'].get(f['native_zoi_id_at_9b8']);assert zoi
 row={'node_id':node['record_id'],'name':node['name'],'node_type':f['NodeType'],'biome':zoi['fields']['Biome'],
  'origin_cm':f['Location'],'rotation_degrees':f['Rotation'],'layout_id':f['LayoutId']['record_id'],
  'purpose_review_required':any(x in node['name'] for x in ('HARBOR','ArtisanPOI','StartingArea')),'props':[]}
 layout=idx['Layout'][row['layout_id']];row['layout_name']=layout['name']
 for ordinal,prop in enumerate(layout['fields']['Props']['items']):
  asset=prop['AssetSet']['record_id'];chosen=choose(asset,row)
  if not chosen:continue
  row['props'].append({'owner_guid':node['record_id'],'owner_secondary_id':0,'owner_array_index':ordinal,
   'assetset_record_guid':asset,'assetset_name':idx['NodeAssetSet'][asset]['name'],
   'item_transform':prop['Transform'],'selected_definitions':chosen})
 nodes.append(row);purposes['needs_purpose_review' if row['purpose_review_required'] else 'ordinary_named_node']+=1
win=idx['CityNode']['0x62d024b45678'];layout=idx['Layout'][win['fields']['LayoutId']['record_id']]
plots=next(x['value']['Plots']['items'] for x in layout['fields']['PlotsPerNodeLevel']['items'] if x['key']==3)
plot_refs={x['Plot']['record_id']:x for x in plots};correlation=[]
for item in capture['custom_delta']['items']:
 if item['matched_layout_prop']:continue
 owner=item['owner_guid'];assert owner in plot_refs and owner in idx['ServiceBuildingPlot']
 assert item['owner_secondary_id']==2 and item['owner_array_index']==0
 t=plot_refs[owner]['Transform'];q=[*item['quat_xyz'],item['quat_w_positive_sqrt']]
 errors={'translation':max(abs(a-b) for a,b in zip(item['translation_cm'],t['translation'])),
  'scale':max(abs(a-b) for a,b in zip(item['scale3d'],t['scale'])),
  'quat':min(max(abs(a-b) for a,b in zip(q,t['quaternion'])),max(abs(a+b) for a,b in zip(q,t['quaternion'])))}
 assert errors['translation']<1e-5 and errors['scale']<1e-9 and errors['quat']<1e-6
 plot=idx['ServiceBuildingPlot'][owner];pf=plot['fields'];matches=[]
 for ref in [*pf['BuildingsIds']['items'],pf['EmptyBuildingId']]:
  building=idx['Building'].get(ref['record_id'])
  if not building:continue
  group=idx['BuildingNodeAssetSets'][building['fields']['BuildingAssetSetId']['record_id']]
  for field,array in group['fields'].items():
   if not field.endswith('AssetSetIds'):continue
   for at,asset in enumerate(array['items']):
    if asset['record_id']==item['assetset_record_guid']:
     matches.append({'building_id':building['record_id'],'building_name':building['name'],'state_group':field,'group_array_index':at})
 assert matches,(owner,item['assetset_record_guid'])
 correlation.append({'item_ordinal':item['ordinal'],'plot_id':owner,'plot_name':plot['name'],
  'observed_owner_secondary_id':2,'observed_owner_array_index':0,'assetset':item['assetset_record_guid'],
  'transform_errors':errors,'matching_building_groups':matches})
assert len(correlation)==22
out={'sources':[{'path':str(x),'sha256':hashlib.sha256(x.read_bytes()).hexdigest()} for x in files],
 'profile':{'level':1,'culture':0,'season':1,'gameplay_tags':[],'node_type_and_biome':'exact CityNode/ZOI definitions'},
 'nodes':nodes,'purpose_name_heuristics':dict(purposes),'historical_service_owner_correlation':correlation,
 'limits':['Explicit lab profile; not reconstructed official progression state.',
 'Name-based purpose review is a heuristic requiring implementation selection, not authoritative node classification.',
 'Selected definitions retain native instance transforms/data; static mesh/PCG collision remains to export.',
 'SecondaryId2 is observed for service plots across construction/operational groups; do not equate it with BuildingState2.',
 'Historical service transform/group membership validates tuple provenance; native state-selection producer remains unresolved.']}
(R/'proofs/settlement-crossroads-profile.json').write_text(json.dumps(out,indent=2),encoding='utf-8');db.close()
print(json.dumps({'nodes':len(nodes),'selected_props':sum(len(x['props']) for x in nodes),'purpose_review':dict(purposes),
 'winstead_props':[x['owner_array_index'] for n in nodes if n['node_id']=='0x62d024b45678' for x in n['props']],
 'service_owner_transforms_matched':len(correlation)},indent=2))
