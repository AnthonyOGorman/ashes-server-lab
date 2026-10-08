"""Find capsule-clear test positions on newly recovered native mesh hulls."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lab.static_collision import from_export
from lab.terrain import Heightfield
from lab.terrain_movement import TerrainMovement
from lab.terrain_relocation import validated_position

ROOT=Path(__file__).resolve().parents[1]


def find(profile_path, previous_path):
    profile=json.loads(profile_path.read_text())
    raw=(ROOT/profile['static_collision_snapshot']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=profile['static_collision_sha256']:
        raise ValueError('active static geometry hash mismatch')
    report=json.loads(raw)
    meshes,unsupported=from_export(report)
    if unsupported:raise ValueError('current export must load without unsupported shapes')
    _,previous=from_export(json.loads(previous_path.read_text()))
    recovered={(r['component'],r.get('index')) for r in previous}
    manifest=ROOT/profile['terrain_manifest'];raw=manifest.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=profile['terrain_sha256']:
        raise ValueError('active terrain hash mismatch')
    tiles=[]
    for tile in json.loads(raw)['tiles']:
        buffers=[]
        for key in ('heights','materials'):
            path=(manifest.parent/tile[key]).resolve()
            if path.parent!=manifest.parent.resolve():raise ValueError('sibling tile required')
            buf=path.read_bytes()
            if hashlib.sha256(buf).hexdigest()!=tile[key+'_sha256']:raise ValueError('tile hash mismatch')
            buffers.append(buf)
        tiles.append(Heightfield(tile['rows'],tile['cols'],tile['origin'],tile['scale'],tile['minimum'],tile['quantization'],*buffers))
    candidates=[]
    for component in report['components']:
        asset=report['assets'][component['asset']]
        for shape in asset['shapes']:
            if (component['identity']['address'],shape.get('index')) not in recovered:continue
            single=dict(report,components=[component],assets={component['asset']:dict(asset,shapes=[shape])})
            targets,errors=from_export(single)
            if errors or len(targets)!=1:continue
            mesh=targets[0]
            for triangle,normal in mesh.faces:
                if normal[2]<.6156615018844604:continue
                x,y=[sum(v[i] for v in triangle)/3 for i in (0,1)]
                position=[x,y,mesh.maximum[2]+140]
                try:
                    state=TerrainMovement(tiles,position,speed=996,gravity=-1225,
                        half_height=96,radius=22,floor_clearance=2.15,static_meshes=meshes)
                    floor=state.floor(x,y)
                    state.position=[x,y,floor]
                    validated_position(state,state.position)
                    hit=mesh.ground(x,y,floor-96+2.5,state.floor_z)
                    if hit is None or floor-hit['height']>140:continue
                    candidates.append({'component':component['identity'],'mesh':asset['mesh'],
                        'shape_index':shape.get('index'),'layout':shape.get('CookedGeometry',{}).get('layout'),
                        'position':state.position,'shape_bounds':[mesh.minimum,mesh.maximum],
                        'native_component_transform':component['native_component_transform'],
                        'pawn':report['pawn'],'profile_id':profile['id'],'connection_id':profile['connection_id']})
                except ValueError:continue
    return candidates


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',type=Path,default=ROOT/'data/terrain-movement-experiment.json')
    parser.add_argument('--previous',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();rows=find(args.profile,args.previous)
    args.output.write_text(json.dumps(rows,indent=2));print(json.dumps({'capsule_clear_platform_candidates':len(rows),'meshes':sorted({r['mesh']['name'] for r in rows})}))
