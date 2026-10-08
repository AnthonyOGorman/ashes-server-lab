"""Resolve tier-one plot/building/asset-set definition chains; do not choose live state."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sources=[R/'proofs/settlement-placement-catalog.json',R/'proofs/settlement-records-live-145444-134358596923129243.json',R/'proofs/settlement-service-records-live.json']
catalog,base,services=[json.loads(p.read_bytes()) for p in sources]
assert base['proof']['sha256']==services['proof']['sha256']==catalog['proof']['sha256']
idx={name:{x['record_id']:x for x in v.get('records',[])} for doc in (base,services) for name,v in doc['records'].items()}
gaps=[];nodes=[]
def get(kind,id):
 if id=='0x0':return None
 v=idx[kind].get(id)
 if not v:gaps.append({'kind':kind,'id':id})
 return v
def asset_set(id):
 a=get('NodeAssetSet',id)
 if not a:return None
 definitions=[]
 for item in a['fields']['ContainedAssetDefinitions']['items']:
  d=get('NodeAssetDefinition',item['Asset']['record_id'])
  if not d:continue
  f=d['fields'];definitions.append({'id':d['record_id'],'name':d['name'],'transform':item['Transform'],
   'levels':[f['NodeLevelMinimum'],f['NodeLevelMaximum']],'cultures':f['ValidCultures']['items'],
   'node_types':f['ValidNodeTypes']['items'],'biomes':f['ValidBiomes']['items'],'all_biomes':f['bAllBiomes'],
   'seasons':f['ValidSeasons']['items'],'tags':f['ValidGameplayTags'],
   'assets':[{'path':x['key'],'instance_count':x['value']['InstanceData']['count']} for x in f['ContainedAssets']['items']]})
 return {'id':a['record_id'],'name':a['name'],'definitions':definitions}
def building(id):
 b=get('Building',id)
 if not b:return None
 f=b['fields'];a=get('BuildingNodeAssetSets',f['BuildingAssetSetId']['record_id'])
 return {'id':id,'name':b['name'],'service_type':f['ServiceBuildingType'],
  'building_asset_set_id':f['BuildingAssetSetId']['record_id'],
  'state_asset_sets':{k:[asset_set(x['record_id']) for x in v['items']] for k,v in a['fields'].items()
   if k.endswith('AssetSetIds')} if a else None}
for node in catalog['nodes']:
 if node['world']!='Verra_World_Master' or not node['layout_name']:continue
 plots=[]
 for ordinal,ref in enumerate(node['tier1_service_plots']):
  p=get('ServiceBuildingPlot',ref['Plot']['record_id'])
  if not p:continue
  f=p['fields'];plots.append({'ordinal':ordinal,'plot_id':p['record_id'],'name':p['name'],
   'transform':ref['Transform'],'starting_state':f['StartingState'],'pre_construct':f['PreConstruct'],
   'building_candidates':[building(x['record_id']) for x in f['BuildingsIds']['items']],
   'empty_building':building(f['EmptyBuildingId']['record_id'])})
 nodes.append({'id':node['record_id'],'name':node['record_name'],'node_type':node['node_type'],
  'biome':node['biome'],'tier1_plots':plots})
out={'sources':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sources],
 'definition_lifetimes':[base['proof'],services['proof']],'nodes':nodes,'unresolved_references':gaps,
 'limits':['Definition graph across hash-matched client lifetimes; no live building/progression state inferred.',
 'Building candidates/state asset groups retain filters; no generic operational state grant.',
 'Native server producer/compound ownership/plot lifecycle remains to bind before implementation.']}
(R/'proofs/settlement-tier1-services-catalog.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps({'nodes':len(nodes),'tier1_plot_entries':sum(len(x['tier1_plots']) for x in nodes),'unresolved_references':len(gaps),
 'winstead_plot_names':[p['name'] for n in nodes if n['name']=='Verra_RVR_Winstead' for p in n['tier1_plots']]},indent=2))
