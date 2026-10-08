"""Recover exact per-tier prop/plot recipes for dashboard selection, offline only.

No authoritative progression/state selection is invented and no live content sent.
"""
import collections,hashlib,json,sqlite3
from functools import lru_cache
from pathlib import Path
R=Path(__file__).resolve().parents[1]
inputs=[R/'proofs/settlement-records-live-145444-134358596923129243.json',
        R/'proofs/settlement-service-records-live-115384-134358634073559490.json']
base,service=[json.loads(p.read_bytes()) for p in inputs]
assert base['proof']['sha256']==service['proof']['sha256']
idx={k:{x['record_id']:x for x in v['records']} for d in (base,service) for k,v in d['records'].items()}
db=sqlite3.connect((R/'index/client-index.sqlite').as_uri()+'?mode=ro',uri=True)
levels=['Wilderness','Crossroads','Encampment','Village','Town','City','Metropolis']
definition_pool={}
selection_pool={}
building_pool={}
needed_packages=sorted({a['key']['package'] for d in idx['NodeAssetDefinition'].values()
                        for a in d['fields']['ContainedAssets']['items']})
class_index=collections.defaultdict(set)
placeholders=','.join('?' for _ in needed_packages)
for package,asset,cls in db.execute(f'SELECT DISTINCT package,name,cls FROM assets WHERE package IN ({placeholders})',needed_packages):
    class_index[(package,asset)].add(cls)
@lru_cache(None)
def classes(package,asset):
    return sorted(class_index[(package,asset)])
@lru_cache(None)
def choose(assetset,level,ntype,biome):
    chosen=[]
    for tuple_ in idx['NodeAssetSet'][assetset]['fields']['ContainedAssetDefinitions']['items']:
        definition=idx['NodeAssetDefinition'][tuple_['Asset']['record_id']];f=definition['fields']
        tags=f['ValidGameplayTags'];assert tags['status']=='unsupported_reflected_type'
        raw=bytes.fromhex(tags['raw']);assert len(raw)==32
        count=int.from_bytes(raw[8:12],'little',signed=True);assert 0<=count<=1024
        if not(f['NodeLevelMinimum']<=level<=f['NodeLevelMaximum'] and
                0 in f['ValidCultures']['items'] and 1 in f['ValidSeasons']['items'] and
                ntype in f['ValidNodeTypes']['items'] and
                (f['bAllBiomes'] or biome in f['ValidBiomes']['items']) and count==0):continue
        if definition['record_id'] not in definition_pool:
            assets=[]
            for a in f['ContainedAssets']['items']:
                path=a['key'];assets.append({'path':path,'inventory_classes':classes(path['package'],path['asset']),
                    'instances':a['value']['InstanceData']['items']})
            definition_pool[definition['record_id']]={'name':definition['name'],'assets':assets}
        chosen.append({'definition_id':definition['record_id'],'name':definition['name'],
                       'definition_transform':tuple_['Transform']})
    return chosen
def selection_key(assetset,level,ntype,biome):
    selected=choose(assetset,level,ntype,biome)
    if not selected:return None
    key=f'{assetset}/level{level}/type{ntype}/biome{biome}'
    selection_pool.setdefault(key,selected)
    return key
def building(ref,level,node):
    record=idx['Building'].get(ref['record_id'])
    if not record:return None
    group_id=record['fields']['BuildingAssetSetId']['record_id']
    if group_id=='0x0':
        return {'building_id':record['record_id'],'name':record['name'],
                'service_type':record['fields']['ServiceBuildingType'],
                'building_asset_group_id':group_id,'state_asset_groups':{},
                'visual_assets_status':'zero asset-group reference in definition'}
    group=idx['BuildingNodeAssetSets'][group_id]
    states={}
    for name,array in group['fields'].items():
        if not name.endswith('AssetSetIds'):continue
        states[name]=[]
        for ordinal,a in enumerate(array['items']):
            aid=a['record_id'];selected=selection_key(aid,level,node['node_type'],node['biome'])
            states[name].append({'group_array_index':ordinal,'assetset_record_guid':aid,'selection_key':selected})
    return {'building_id':record['record_id'],'name':record['name'],
            'service_type':record['fields']['ServiceBuildingType'],'state_asset_groups':states}
def building_key(ref,level,node):
    if ref['record_id']=='0x0':return None
    key=f'{ref["record_id"]}/level{level}/type{node["node_type"]}/biome{node["biome"]}'
    if key not in building_pool:
        variant=building(ref,level,node)
        assert variant is not None,key
        building_pool[key]=variant
    return key
nodes=[]
for n in idx['CityNode'].values():
    f=n['fields'];layoutid=f['LayoutId']['record_id']
    if f['mapName']!='Verra_World_Master' or layoutid=='0x0':continue
    layout=idx['Layout'][layoutid];biome=idx['ZOI'][f['native_zoi_id_at_9b8']]['fields']['Biome']
    row={'node_id':n['record_id'],'name':n['name'],'layout_id':layoutid,'layout_name':layout['name'],
         'node_type':f['NodeType'],'biome':biome,'origin_cm':f['Location'],'rotation_degrees':f['Rotation'],'tiers':[]}
    perlevel={x['key']:x['value']['Plots']['items'] for x in layout['fields']['PlotsPerNodeLevel']['items']}
    assert all(0<=x<=6 for x in perlevel)
    for level,label in enumerate(levels):
        props=[]
        for ordinal,prop in enumerate(layout['fields']['Props']['items']):
            aid=prop['AssetSet']['record_id'];selected=selection_key(aid,level,row['node_type'],biome)
            if selected:props.append({'owner_guid':n['record_id'],'owner_secondary_id':0,'owner_array_index':ordinal,
                'assetset_record_guid':aid,'assetset_name':idx['NodeAssetSet'][aid]['name'],
                'item_transform':prop['Transform'],'selection_key':selected})
        plots=[]
        for ordinal,p in enumerate(perlevel.get(level,[])):
            plot=idx['ServiceBuildingPlot'][p['Plot']['record_id']];pf=plot['fields']
            plots.append({'layout_plot_ordinal':ordinal,'plot_id':plot['record_id'],'name':plot['name'],
                'item_transform':p['Transform'],'starting_state_definition':pf['StartingState'],
                'pre_construct_definition':pf['PreConstruct'],
                'building_candidate_keys':[building_key(b,level,row) for b in pf['BuildingsIds']['items']],
                'empty_building_key':building_key(pf['EmptyBuildingId'],level,row)})
        row['tiers'].append({'level':level,'name':label,'props':props,'service_plots':plots})
    nodes.append(row)
assert len(nodes)==44
win=next(x for x in nodes if x['name']=='Verra_RVR_Winstead')
assert [x['owner_array_index'] for x in win['tiers'][1]['props']]==[8,9,10,11,12,13,14,35,58,60,63,71,72]
assert all(any(x['owner_array_index']==14 and x['assetset_record_guid']=='0x5429e761b0070000'
                   for x in tier['props']) for tier in win['tiers'])
out={'sources':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs],
     'build_sha256':base['proof']['sha256'],'profile':{'culture':0,'season':1,'gameplay_tags':[],
         'maximum_defined_tier':6,'level_names':levels},'nodes':nodes,
     'selection_pool':selection_pool,'definition_pool':definition_pool,'building_pool':building_pool,
     'limits':['Explicit Kaelar/Spring/empty-tag lab profile; official active progression state not inferred.',
        'Props keep exact compound IDs/indexes/transforms; service plots retain alternative state/building groups.',
        'Do not instantiate all alternative buildings or equate historical service SecondaryId2 with building state.',
        'Real-time tier transitions need stable per-array IDs/keys, removals, cached metadata/version and received/load verification.',
        'Staticmesh/building collision and authoritative service-state selection are not established by this catalog.',
        'Only research outputs; no CPP edits, live process access, input or network packets.']}
(R/'proofs/settlement-tier-profiles.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
summary={'nodes':len(nodes),'maximum_tier':6,'winstead':[{'level':x['level'],'name':x['name'],
    'props':len(x['props']),'plots':len(x['service_plots'])} for x in win['tiers']]}
(R/'proofs/settlement-tier-profiles-summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
print(json.dumps(summary,indent=2));db.close()
