"""Build offline settlement placement/asset catalogs and captured actor evidence."""
import csv,hashlib,json,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
from lab.world_bootstrap import decode_exports,decode_actor_location
from lab.unreal import BitReader

source=ROOT/'proofs/settlement-records-live.json'
raw=source.read_bytes();snapshot=json.loads(raw)
lookup={n:{x['record_id']:x for x in data.get('records',[])} for n,data in snapshot['records'].items()}
catalog=[];unresolved=[]
for node in lookup['CityNode'].values():
 f=node['fields'];layout=lookup['Layout'].get(f['LayoutId']['record_id'])
 zoi=lookup['ZOI'].get(f['native_zoi_id_at_9b8']);biome=zoi['fields']['Biome'] if zoi else None
 row={'record_id':node['record_id'],'record_name':node['name'],'name':f['NodeName'],
  'world':f['mapName'],'location_cm':f['Location'],'rotation_degrees':f['Rotation'],
  'node_type':f['NodeType'],'biome':biome,'zoi_id':f['native_zoi_id_at_9b8'],
  'layout_id':f['LayoutId']['record_id'],'layout_name':layout['name'] if layout else None,
  'generation_seed':f['generationSeed'],'tier1_props_candidates':[],
  'tier1_service_plots':None,'status':'layout available' if layout else 'no loaded nonzero layout'}
 if layout:
  plot=next((x for x in layout['fields']['PlotsPerNodeLevel']['items'] if x['key']==1),None)
  row['tier1_service_plots']=plot['value']['Plots']['items'] if plot else []
  for ordinal,prop in enumerate(layout['fields']['Props']['items']):
   assetset=lookup['NodeAssetSet'].get(prop['AssetSet']['record_id'])
   if not assetset:
    unresolved.append({'node':node['record_id'],'reference':prop['AssetSet']});continue
   candidates=[]
   for definition_ordinal,item in enumerate(assetset['fields']['ContainedAssetDefinitions']['items']):
    definition=lookup['NodeAssetDefinition'].get(item['Asset']['record_id'])
    if not definition:
     unresolved.append({'node':node['record_id'],'reference':item['Asset']});continue
    df=definition['fields']
    if not df['NodeLevelMinimum']<=1<=df['NodeLevelMaximum']:continue
    if f['NodeType'] not in df['ValidNodeTypes']['items']:continue
    if not df['bAllBiomes'] and biome not in df['ValidBiomes']['items']:continue
    assets=[]
    for asset in df['ContainedAssets']['items']:
     instances=[]
     for instance in asset['value']['InstanceData']['items']:
      data=instance['DataString']
      instances.append({'transform':instance['Transform'],'type':instance['Type'],
       'data_string_units':len(data),'data_string_sha256_utf8':hashlib.sha256(data.encode()).hexdigest()})
     assets.append({'path':asset['key'],'instances':instances})
    candidates.append({'definition_id':definition['record_id'],'name':definition['name'],
     'definition_ordinal':definition_ordinal,'transform':item['Transform'],
     'levels':[df['NodeLevelMinimum'],df['NodeLevelMaximum']],
     'valid_cultures':df['ValidCultures']['items'],'valid_seasons':df['ValidSeasons']['items'],
     'gameplay_tag_filter':df['ValidGameplayTags'],'assets':assets})
   if candidates:row['tier1_props_candidates'].append({'assetset_id':assetset['record_id'],
    'name':assetset['name'],'layout_ordinal':ordinal,'transform':prop['Transform'],
    'definitions':candidates})
 catalog.append(row)

out={'source':str(source),'source_sha256':hashlib.sha256(raw).hexdigest(),'proof':snapshot['proof'],
 'tier':1,'tier_name':'Crossroads','nodes':catalog,'unresolved_references':unresolved,
 'limits':['Definitions and candidate props, not active server settlement state.',
  'Filter by exact world/nonzero layout/purpose. Culture, season and gameplay tags remain required selection inputs.',
  'Transform chains are preserved; exact native composition and collision admission require further verification.',
  'Service plot definition/building references remain unresolved in this catalog.']}
(ROOT/'proofs/settlement-placement-catalog.json').write_text(json.dumps(out,indent=2))
with (ROOT/'catalogs/settlement-locations.csv').open('w',newline='',encoding='utf-8') as stream:
 writer=csv.writer(stream);writer.writerow(['record_id','record_name','world','name','x_cm','y_cm','z_cm','pitch','yaw','roll','node_type','biome','layout_id','layout_name'])
 for row in catalog:writer.writerow([row['record_id'],row['record_name'],row['world'],row['name'],*row['location_cm'],*row['rotation_degrees'],row['node_type'],row['biome'],row['layout_id'],row['layout_name']])

fixture=ROOT.parent/'evidence/world_bootstrap_capture.json';data=fixture.read_bytes();capture=json.loads(data)
row=next(x for x in capture['evidence'] if x['frame']==3898)
exports=next(b for b in row['decoded']['bunches'] if b['channel']==38 and b['exports'])
body=next(b for b in row['decoded']['bunches'] if b['channel']==38 and not b['exports'])
decoded=decode_exports(bytes.fromhex(exports['payload_hex']),exports['payload_bits'])
assert decoded==exports['export_decode']
prefix=decode_actor_location(bytes.fromhex(body['payload_hex']),body['payload_bits'])
archetype=decoded['objects'][0];assert prefix['archetype']==archetype['guid']
assert archetype['path']=='Default__NodeLayoutReplicator' and archetype['checksum']==4242000812
package_refs=[]
def visit(item,frame):
 if isinstance(item,dict):
  if item.get('guid')==archetype['outer']['guid'] and item.get('path'):
   assert item['path']=='/Script/GameSystemsPlugin' and item['checksum']==0
   package_refs.append({'frame':frame,'object':item})
  for child in item.values():visit(child,frame)
 elif isinstance(item,list):
  for child in item:visit(child,frame)
for item in capture['evidence']:visit(item['decoded'],item['frame'])
assert package_refs
reader=BitReader(bytes.fromhex(body['payload_hex']),body['payload_bits']);reader.pos=prefix['consumed_bits']
assert [reader.read(1) for _ in range(3)]==[0,0,0]
content_flags=[reader.read(1),reader.read(1)];length=reader.packed();start=reader.pos
assert content_flags==[1,1] and length==reader.remaining==239 and start==486
assert reader.read(1)==0
node=next(x for x in catalog if x['record_name']=='Verra_RVR_ArtisanPOI_BriarmoorWorkshops')
assert all(abs(a-b)<=0.051 for a,b in zip(prefix['location'],node['location_cm']))
reader.pos=653;assert reader.read(64)==int(node['record_id'],0) and reader.packed()==0 and reader.remaining==0
proof={'fixture':str(fixture),'fixture_sha256':hashlib.sha256(data).hexdigest(),'frame':3898,'channel':38,
 'export':decoded,'package_export_references':package_refs,'actor_body':body,'prefix':prefix,
 'three_remaining_default_transform_flags':[0,0,0],'content_flags':content_flags,'content_start_bit':start,
 'content_bits':length,'checksum_enabled':0,'matched_node_id':node['record_id'],
 'raw_node_id_bit_position':653,'tail_terminator_consumes_body':True,
 'limits':['Property body not fully traversed; no wire property name/handle claim from raw ID match.',
  'Captured dynamic actor GUID is historical; author a fresh actor/export identity for a new connection.']}
(ROOT/'proofs/settlement-captured-actor.json').write_text(json.dumps(proof,indent=2))
print(json.dumps({'catalog_nodes':len(catalog),'verra_nodes':sum(x['world']=='Verra_World_Master' for x in catalog),
 'unresolved_references':len(unresolved),'capture_header_verified':True,'matched_node':node['record_name']},indent=2))
