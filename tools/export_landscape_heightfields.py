"""Export bounded native terrain samples read-only, with identity and layout checks."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from dump_runtime_reflection import Reader, ReadError, pointer
from inspect_movement_prerequisites import MovementProbe
from protocol_proof import EXPECTED_EXE, client_proof


def export(pid, source, output, x, y):
    report=json.loads(source.read_text())
    proof=client_proof(pid)
    if any(report['client_proof'][key] != proof[key] for key in
           ('pid','exe','sha256','process_created_filetime')):
        raise ValueError('fresh exact client identity required')
    reader=Reader(pid,EXPECTED_EXE)
    result={'pid':pid,'client_proof':proof,'source':str(source),'tiles':[], 'skipped':[],
            'scope':'Axis-aligned landscape triangles only; no static meshes or capsule sweep'}
    try:
        probe=MovementProbe(reader)
        from export_static_collision import CollisionProbe
        world_probe=CollisionProbe(reader)
        pawns=[obj for obj in report['objects'] if obj['kind']=='PlayerCharacter']
        if len(pawns)!=1:
            raise ValueError('one current gameplay pawn required for terrain export')
        pawn=int(pawns[0]['identity']['address'],16)
        if probe.identity(pawn)!=pawns[0]['identity']:
            raise ValueError('current terrain pawn identity required')
        world=world_probe.world(pawn)
        if world is None:raise ValueError('current pawn world required')
        result['world']=probe.identity(world,'World')
        # Exact native leaf: bounded cell index, material byte == 255 => hole.
        hole_code=bytes.fromhex('8b414885c07e1885d278113bd07d0d488b41404863d2803c02ff7503b001c332c0c3')
        if reader.read(reader.base+0x2141090,len(hole_code)) != hole_code:
            raise ValueError('native heightfield hole semantics mismatch')
        for obj in report['objects']:
            if obj['kind'] != 'LandscapeHeightfieldCollisionComponent':
                continue
            if world_probe.world(int(obj['identity']['address'],16))!=world:
                continue
            chain=obj['transform_chain']
            if len(chain)!=2 or any(chain[1]['fields']['RelativeRotation']['value']):
                continue
            child,parent=[c['fields'] for c in chain]
            if any(child['RelativeRotation']['value']) or child['RelativeScale3D']['value'] != [1,1,1]:
                continue
            root=parent['RelativeLocation']['value'];scale=parent['RelativeScale3D']['value']
            rel=child['RelativeLocation']['value']
            origin=[root[i]+rel[i]*scale[i] for i in range(3)]
            quads=obj['fields']['CollisionSizeQuads']['value']
            # Export only a bounded neighbourhood needed for this spawn test.
            distance=math.hypot(max(origin[0]-x,0,x-origin[0]-quads*scale[0]),
                                max(origin[1]-y,0,y-origin[1]-quads*scale[1]))
            if distance>10000:
                continue
            a=int(obj['identity']['address'],16)
            if probe.identity(a) != obj['identity']:
                raise ValueError('terrain identity changed during export')
            props=probe.properties_for(a)
            guid=props['HeightfieldGuid']
            if guid['type']!='StructProperty' or guid['referenced_type']!='Guid' or guid['element_size']!=16:
                raise ValueError('invalid reflected heightfield GUID')
            ref=reader.unpack(a+0x618,'<Q')[0]
            if not pointer(ref):
                result['skipped'].append({'component':obj['identity'],'reason':'no native geometry reference'})
                continue
            if reader.read(ref+0x10,16) != reader.read(a+guid['offset_in_object'],16):
                raise ValueError('geometry reference GUID does not match component')
            g=reader.unpack(ref+0x30,'<Q')[0]
            if not pointer(g) or reader.unpack(g,'<Q')[0]-reader.base != 0x9fae738:
                result['skipped'].append({'component':obj['identity'],'reason':'no matching native heightfield'})
                continue
            rows,cols=reader.unpack(g+0x90,'<HH')
            hp,hn,hc=reader.unpack(g+0x20,'<Qii')
            mp,mn,mc=reader.unpack(g+0x40,'<Qii')
            if not (2<=rows<=1024 and 2<=cols<=1024 and hn==rows*cols<=hc<=1048576
                    and mn==(rows-1)*(cols-1)<=mc<=1048576 and pointer(hp) and pointer(mp)):
                raise ValueError('native sample dimensions mismatch')
            heights=reader.read(hp,hn*2);materials=reader.read(mp,mn)
            gs=reader.unpack(g+0x50,'<ddd')
            minimum=reader.unpack(g+0x80,'<d')[0]
            step=reader.unpack(g+0xa0,'<d')[0]
            if any(abs(gs[i]-scale[i])>1e-6 for i in (0,1)) or abs(gs[2]-scale[2]/128)>1e-6:
                raise ValueError('native heightfield scale does not match component transform')
            prefix=f"tile-{obj['identity']['object_index']}"
            output.mkdir(parents=True,exist_ok=True)
            (output/(prefix+'.heights')).write_bytes(heights)
            (output/(prefix+'.materials')).write_bytes(materials)
            result['tiles'].append({'identity':obj['identity'],'rows':rows,'cols':cols,
                'origin':origin,'scale':gs,'minimum':minimum,'quantization':step,
                'heights':prefix+'.heights','materials':prefix+'.materials',
                'heights_sha256':hashlib.sha256(heights).hexdigest(),
                'materials_sha256':hashlib.sha256(materials).hexdigest(),
                'solid_cells':mn-materials.count(255)})
        result['completed_client_proof']=client_proof(pid)
        output.mkdir(parents=True,exist_ok=True)
        (output/'manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        return result
    finally:
        reader.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid',type=int,required=True)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--x',type=float,required=True)
    p.add_argument('--y',type=float,required=True)
    a=p.parse_args()
    r=export(a.pid,a.source,a.output,a.x,a.y)
    print(json.dumps({'tiles':len(r['tiles']),'skipped':r['skipped']}))
