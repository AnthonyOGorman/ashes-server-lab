"""Read current nearby native collision; never publish requests or move a pawn."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from inspect_world_collision import inspect
from export_landscape_heightfields import export as export_terrain
from export_static_collision import export as export_static
from lab.static_collision import from_export


def refresh(pid,pawn,x,y,directory):
    directory.mkdir(parents=True,exist_ok=True)
    source=directory/'inventory.json'
    inventory=inspect(pid)
    current=[o for o in inventory['objects'] if o['kind']=='PlayerCharacter']
    if len(current)!=1 or int(current[0]['identity']['address'],16)!=pawn:
        raise ValueError('refresh requires the current gameplay pawn')
    source.write_text(json.dumps(inventory))
    manifest=directory/'terrain'/'manifest.json'
    terrain=export_terrain(pid,source,manifest.parent,x,y)
    # Publish a completion marker only after all heightfield buffers and their
    # manifest are durable. The server can admit terrain while mesh work runs.
    ready=directory/'terrain-ready.json'
    temporary=ready.with_suffix('.tmp')
    temporary.write_text(json.dumps({'manifest':manifest.relative_to(ROOT).as_posix(),
                                     'tiles':len(terrain['tiles'])}))
    temporary.replace(ready)
    report=export_static(pid,pawn,[x,y,0.],20000.)
    supported=[];excluded=[]
    for component in report['components']:
        meshes,errors=from_export(dict(report,components=[component]))
        if component.get('mobility')==0 and meshes and not errors:
            supported.append(component)
        else:
            excluded.append({'identity':component['identity'],
                'reasons':errors or ['moving or empty native collision']})
    report['components']=supported
    report['refresh_excluded']=excluded
    snapshot=ROOT/'evidence'/f'collision_refresh_{directory.name}_{pid}.json'
    snapshot.write_text(json.dumps(report))
    result={'manifest':manifest.relative_to(ROOT).as_posix(),
            'snapshot':snapshot.relative_to(ROOT).as_posix(),
            'tiles':len(terrain['tiles']),'supported_components':len(supported),
            'excluded_components':len(excluded)}
    (directory/'result.json').write_text(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid',type=int,required=True)
    p.add_argument('--pawn',type=lambda value:int(value,0),required=True)
    p.add_argument('--x',type=float,required=True);p.add_argument('--y',type=float,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(refresh(a.pid,a.pawn,a.x,a.y,a.output)))
