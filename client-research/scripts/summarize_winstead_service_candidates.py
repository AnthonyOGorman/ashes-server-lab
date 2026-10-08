"""Summarize saved per-tier service alternatives; never choose authoritative state."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
source=R/'proofs/winstead-tier-recipes.json';raw=source.read_bytes();d=json.loads(raw)
state_fields={0:'empty',1:'ConstructionAssetSetIds',2:'OperationalAssetSetIds',3:'DisarrayAssetSetIds',4:'DamagedAssetSetIds',5:'RepairingAssetSetIds',6:'DestroyedAssetSetIds',7:'DemolitionAssetSetIds'}
tiers=[]
for tier in d['node']['tiers']:
    plots=[]
    for p in tier['service_plots']:
        alternatives=[]
        for key in p['building_candidate_keys']:
            b=d['building_pool'][key]
            groups={name:[g for g in values if g.get('selection_key')] for name,values in b['state_asset_groups'].items()}
            alternatives.append(dict(candidate_key=key,building_id=b['building_id'],name=b['name'],service_type=b['service_type'],
                selected_group_counts={name:len(values) for name,values in groups.items()},
                selected_state_asset_groups=groups))
        field=state_fields[p['starting_state_definition']]
        available=[x['candidate_key'] for x in alternatives if x['selected_group_counts'].get(field,0)]
        operational=[x['candidate_key'] for x in alternatives if x['selected_group_counts'].get('OperationalAssetSetIds',0)]
        plots.append(dict(plot_id=p['plot_id'],name=p['name'],starting_state_definition=p['starting_state_definition'],
            pre_construct_definition=p['pre_construct_definition'],starting_state_candidate_keys=available,
            operational_candidate_keys=operational,alternatives=alternatives,
            starting_availability='none' if not available else 'one' if len(available)==1 else 'multiple'))
    tiers.append(dict(level=tier['level'],name=tier['name'],plots=plots,
        starting_candidate_availability={label:sum(p['starting_availability']==label for p in plots) for label in ['none','one','multiple']},
        operational_candidate_availability={label:sum((len(p['operational_candidate_keys'])==0 if label=='none' else len(p['operational_candidate_keys'])==1 if label=='one' else len(p['operational_candidate_keys'])>1) for p in plots) for label in ['none','one','multiple']}))
out=dict(build_sha256=d['build_sha256'],source=dict(path=str(source),sha256=hashlib.sha256(raw).hexdigest()),profile=d['profile'],
    node_id=d['node']['node_id'],node_type=d['node']['node_type'],biome=d['node']['biome'],tiers=tiers,
    limits=['Saved definition/profile filtering only; nonempty selected groups are not proof of rendered or collidable building contents.',
        'One available candidate is not an authoritative active-building choice; state/progression/ownership are separate.',
        'StartingState is a definition default, not current server state. SecondaryId2 must not be equated with Operational state2.',
        'No packets, CPP edits, process access, native calls or input.'])
(R/'proofs/winstead-service-selection-candidates.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps([dict(level=t['level'],plots=len(t['plots']),starting=t['starting_candidate_availability'],operational=t['operational_candidate_availability']) for t in tiers],indent=2))
