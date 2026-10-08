"""Compact exact main-layout authoring inputs; offline definitions only."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1];p=R/'proofs/settlement-tier-profiles.json';d=json.loads(p.read_bytes())
nodes=[];coverage=[]
for n in d['nodes']:
    row={k:v for k,v in n.items() if k!='tiers'};row['tiers']=[]
    for t in n['tiers']:
        props=[{k:v for k,v in prop.items() if k in ('owner_guid','owner_secondary_id','owner_array_index','assetset_record_guid','item_transform')} for prop in t['props']]
        row['tiers'].append(dict(level=t['level'],name=t['name'],props=props))
        if n['name']!='Verra_RVR_Winstead':continue
        assets=[]
        for prop in t['props']:
            for selection in d['selection_pool'][prop['selection_key']]:
                assets.extend(d['definition_pool'][selection['definition_id']]['assets'])
        service=[]
        for plot in t['service_plots']:
            alternatives=[]
            for key in plot['building_candidate_keys']+[plot['empty_building_key']]:
                if key is None:continue
                b=d['building_pool'][key]
                counts={state:sum(len(d['selection_pool'].get(s['selection_key'],[])) for s in sets) for state,sets in b['state_asset_groups'].items()}
                alternatives.append(dict(building_id=b['building_id'],name=b['name'],selected_definition_counts=counts,visual_assets_status=b.get('visual_assets_status','references resolved')))
            service.append(dict(plot_id=plot['plot_id'],starting_state=plot['starting_state_definition'],pre_construct=plot['pre_construct_definition'],alternatives=alternatives))
        coverage.append(dict(level=t['level'],name=t['name'],main_props=len(props),main_asset_entries=len(assets),
            main_instances=sum(len(a['instances']) for a in assets),service_plots=service))
    nodes.append(row)
out=dict(build_sha256=d['build_sha256'],source=dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()),
         profile=d['profile'],nodes=nodes,limits=d['limits']+['Main-layout projection only: no service-state producer or service GUID assignment.',
             'Each tier transition still needs native receipt/load/unload validation and uninterrupted floor/collision support.'])
dest=R/'proofs/settlement-main-tier-wire-recipes.json';dest.write_text(json.dumps(out,separators=(',',':'))+'\n')
(R/'proofs/winstead-tier-visual-coverage.json').write_text(json.dumps(dict(build_sha256=d['build_sha256'],source=out['source'],tiers=coverage),indent=2)+'\n')
print(json.dumps(dict(wire_bytes=dest.stat().st_size,nodes=len(nodes),winstead=[{k:v for k,v in c.items() if k!='service_plots'} for c in coverage]),indent=2))
