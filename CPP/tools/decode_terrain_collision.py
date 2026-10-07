"""Decode this build's cooked Chaos landscape heightfields into a server cache.

Preserves quantized heights, hole/material bytes and placement transforms.
Rejects unknown layouts instead of substituting visual heightmap data.
"""
import json, pathlib, struct, hashlib, math, sys

class Cursor:
    def __init__(self,data):self.data=data;self.pos=0
    def read(self,fmt):
        size=struct.calcsize('<'+fmt)
        if self.pos+size>len(self.data):raise ValueError('Truncated Chaos archive')
        values=struct.unpack_from('<'+fmt,self.data,self.pos);self.pos+=size
        return values[0] if len(values)==1 else values
    def raw(self,size):
        if size<0 or self.pos+size>len(self.data):raise ValueError('Invalid Chaos array bounds')
        result=self.data[self.pos:self.pos+size];self.pos+=size;return result
    def array(self,element_size,limit=16_777_216):
        count=self.read('i')
        if not 0<=count<=limit:raise ValueError('Excessive Chaos array count')
        return self.raw(count*element_size),count

def heightfield(c,tag):
    if c.read('i')!=1 or c.read('i')!=tag or c.read('B')!=12:raise ValueError('Expected unique Chaos heightfield pointer')
    if c.read('i')!=0 or c.read('i')!=1 or c.read('B')!=12:raise ValueError('Unsupported implicit object flags')
    if c.read('ii')!=(8,2):raise ValueError('Expected double heights with uint16 storage')
    heights,count=c.array(2)
    scale=list(c.read('fff'));minimum,maximum=c.read('dd');rows,cols=c.read('HH');span,quant=c.read('dd')
    if not 2<=rows<=4096 or not 2<=cols<=4096 or count!=rows*cols:raise ValueError('Heightfield dimension mismatch')
    if not all(math.isfinite(x) for x in scale+[minimum,maximum,span,quant]) or any(x<=0 for x in scale) or span<0 or quant<0:raise ValueError('Invalid quantization')
    if abs(span-(maximum-minimum))>1e-7 or abs(quant*65535-span)>1e-7:raise ValueError('Inconsistent quantization')
    materials,material_count=c.array(1)
    cells=(rows-1)*(cols-1)
    if material_count==1:materials*=cells
    elif material_count==0:materials=bytes(cells)
    elif material_count!=cells:raise ValueError('Material cell count mismatch')
    lowres,lowcount=c.array(4);lowcols=c.read('H')
    if lowcount!=math.ceil(rows/6)*math.ceil(cols/6) or lowcols!=math.ceil(cols/6):raise ValueError('Low-resolution height bounds mismatch')
    grid=c.read('ffffiiff');flat=c.read('ffff');bounds=c.read('ffffff')
    if grid[:4]!=(0,0,cols-1,rows-1) or grid[4:6]!=(cols-1,rows-1):raise ValueError('Grid extent mismatch')
    import numpy as np
    samples=np.frombuffer(heights,dtype='<u2')
    # Cached bounds use decoded quantized samples. A source maximum can fall
    # just below 65535 after quantization, so it need not equal MaxValue.
    actual_min=minimum+int(samples.min())*quant;actual_max=minimum+int(samples.max())*quant
    if not all(math.isfinite(x) for x in bounds) or abs(bounds[2]-actual_min)>0.01 or abs(bounds[5]-actual_max)>0.01:raise ValueError('Local collision bounds mismatch')
    return dict(rows=rows,cols=cols,minimum=minimum,quantization=quant,heights=heights,materials=materials,cooked_scale=scale)

def decode(data):
    c=Cursor(data);simple=c.read('i')
    if simple not in (0,1):raise ValueError('Invalid simple collision flag')
    fields=[heightfield(c,0)]
    if simple:fields.append(heightfield(c,1))
    if c.pos!=len(data):raise ValueError(f'Unconsumed collision data: {len(data)-c.pos} bytes')
    return fields

def transform(chain):
    # Preserve full Unreal TRS transforms. Main Verra tiles are axis aligned;
    # smaller placed landscapes can be rotated and require an affine consumer.
    import numpy as np
    matrix=np.eye(4)
    for node in reversed(chain):
        pitch,yaw,roll=map(math.radians,node['rotation']);p,y,r=pitch,yaw,roll
        # Unreal FRotator convention: X forward, Y right, Z up.
        cp,sp,cy,sy,cr,sr=math.cos(p),math.sin(p),math.cos(y),math.sin(y),math.cos(r),math.sin(r)
        rot=np.array([[cp*cy,sr*sp*cy-cr*sy,-cr*sp*cy-sr*sy],[cp*sy,sr*sp*sy+cr*cy,-cr*sp*sy+sr*cy],[sp,-sr*cp,cr*cp]])
        local=np.eye(4);local[:3,:3]=rot@np.diag(node['scale']);local[:3,3]=node['location'];matrix=matrix@local
    return matrix

def main():
    root=pathlib.Path(__file__).resolve().parents[1];source=root/'data/terrain-offline'/(sys.argv[1] if len(sys.argv)>1 else 'cooked');output=root/'data/terrain-offline'/(sys.argv[2] if len(sys.argv)>2 else 'decoded');output.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((source/'manifest.json').read_text());tiles=[];failures=[];unique={}
    for tile in manifest['tiles']:
        try:
            key=tile['cooked'];data=(source/key).read_bytes()
            if hashlib.sha256(data).hexdigest()!=tile['sha256']:raise ValueError('Cooked collision hash differs')
            fields=unique.get(key)
            if fields is None:
                fields=decode(data);unique[key]=[{k:v for k,v in f.items() if k not in ('heights','materials')} for f in fields]
                for i,f in enumerate(fields):
                    for name in ('heights','materials'):
                        filename=f'{tile["sha256"]}-{i}.{name}';blob=f.pop(name);(output/filename).write_bytes(blob);f[name]=filename;f[name+'_sha256']=hashlib.sha256(blob).hexdigest()
                unique[key]=fields
            matrix=transform(tile['transform_chain']);origin=list(matrix[:3,3]);scale=[float(sum(matrix[j,i]**2 for j in range(3))**.5) for i in range(3)];scale[2]/=128
            f=fields[0]
            if f['rows']!=tile['quads']+1 or f['cols']!=tile['quads']+1:raise ValueError('Collision quads differ from cooked dimensions')
            import numpy as np
            axis_aligned=bool(np.allclose(matrix[:3,:3],np.diag(np.diag(matrix[:3,:3])),atol=1e-6) and all(matrix[i,i]>0 for i in range(3)))
            entry={**tile,**f,'origin':origin,'scale':scale,'matrix':matrix.flatten().tolist(),'axis_aligned':axis_aligned,'solid_cells':(f['rows']-1)*(f['cols']-1)-(output/f['materials']).read_bytes().count(255)}
            tiles.append(entry)
        except Exception as error:failures.append({'package':tile['package'],'name':tile['name'],'error':str(error)})
    reference_path=root/'baseline/evidence/terrain_epoch18_49892/manifest.json';reference=json.loads(reference_path.read_text()) if reference_path.exists() else {'tiles':[]};matches=[]
    for old in reference['tiles']:
        candidates=[t for t in tiles if t['heights_sha256']==old['heights_sha256'] and t['materials_sha256']==old['materials_sha256']]
        same=[t for t in candidates if all(abs(a-b)<1e-6 for k in ('origin','scale') for a,b in zip(t[k],old[k])) and abs(t['minimum']-old['minimum'])<1e-9 and abs(t['quantization']-old['quantization'])<1e-12]
        matches.append({'native_reference':old['identity']['name'],'matching_offline_tiles':len(same)})
    report={'schema':'ashes-offline-landscape-v1','status':'decoded' if not failures else 'incomplete','source_packages_scanned':manifest['scanned'],'tiles':tiles,'failures':failures,'native_reference_matches':matches,'axis_aligned_tiles':sum(t['axis_aligned'] for t in tiles),'scope':'landscape heightfield terrain only; static meshes excluded; warped landscape mesh reported separately'}
    (output/'manifest.json').write_text(json.dumps(report,indent=2));print(json.dumps({'status':report['status'],'tiles':len(tiles),'failures':len(failures),'examples':failures[:3],'native_reference_matches':matches,'axis_aligned_tiles':report['axis_aligned_tiles']}))
    if failures:sys.exit(1)
if __name__=='__main__':main()
