"""Find and test a real exported steep landscape face, entirely offline."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lab.terrain import Heightfield
from lab.terrain_movement import TerrainMovement


def verify(manifest):
    report=json.loads(manifest.read_text());tiles=[]
    for entry in report['tiles']:
        tiles.append(Heightfield(entry['rows'],entry['cols'],entry['origin'],entry['scale'],
            entry['minimum'],entry['quantization'],(manifest.parent/entry['heights']).read_bytes(),
            (manifest.parent/entry['materials']).read_bytes()))
    checked=0
    for tile in tiles:
        for y in range(1,tile.rows-2):
            for x in range(2,tile.cols-3):
                if tile.vertex(x+1,y)-tile.vertex(x,y)<200:continue
                checked+=1
                if checked>2000:return {'verified':False,'reason':'candidate budget reached','checked':checked}
                px=tile.origin[0]+(x-.5)*tile.scale[0]
                py=tile.origin[1]+(y+.5)*tile.scale[1]
                hit=tile.ground(px,py)
                if not hit or hit['normal'][2]<.6156615:continue
                spawn=[px,py,hit['height']+96+22*(1/hit['normal'][2]-1)+2.15]
                try:s=TerrainMovement(tiles,spawn,speed=996,gravity=-1225,
                    half_height=96,radius=22,floor_clearance=2.15)
                except ValueError:continue
                # Start on verified support and require a swept native hit.
                start=s.position.copy()
                s.advance({'timestamp':0,'acceleration':[0,0,0],'compressed_flags':0},0)
                result=s.advance({'timestamp':.25,'acceleration':[8192,0,0],'compressed_flags':0},.25)
                # Compare against the same acceleration and substep schedule,
                # rather than assuming an immediate full-speed249cm advance.
                speed=0.;unobstructed=0.
                steps=5;step=.25/steps
                for _ in range(steps):
                    speed=min(996,speed+8192*step)
                    unobstructed+=speed*step
                if result['collision_hits'] and result['server_position'][0]<start[0]+unobstructed-.1:
                    return {'verified':True,'manifest':str(manifest),'checked':checked,
                        'native_cell':[x,y],'native_rise_cm':tile.vertex(x+1,y)-tile.vertex(x,y),
                        'start':start,'spawn':spawn,'unchecked_horizontal_endpoint':start[0]+unobstructed,
                        'result':result,'scope':'offline actual landscape face; no live input or client observation'}
    return {'verified':False,'reason':'no qualifying native face found','checked':checked}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=verify(a.manifest);a.output.write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
