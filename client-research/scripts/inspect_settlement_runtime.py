"""Read current settlement class/CDO dispatch and bounded native serializer leads."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'tools'))
from inspect_movement_prerequisites import MovementProbe
from dump_runtime_reflection import Reader,ReadError,pointer
from protocol_proof import client_proof,EXPECTED_EXE
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('pid',type=int)
args=parser.parse_args();proof=client_proof(args.pid)
assert proof['sha256']==json.loads((ROOT/'index/summary.json').read_text())['native']['sha256']
r=Reader(args.pid,EXPECTED_EXE)
try:
 p=MovementProbe(r);found={}
 for address,obj in p.reflection.objects():
  cls=p.reflection.class_name(obj['class_address'])
  if (obj['name'],cls) in [('NodeLayoutReplicator','Class'),('NodeLayoutAssetSetGuids','ScriptStruct')]:found[obj['name']]=address
  if len(found)==2:break
 assert len(found)==2
 cls=found['NodeLayoutReplicator'];cdo=r.unpack(cls+0x150,'<Q')[0]
 identity=p.identity(cdo,'NodeLayoutReplicator');props=p.properties_for(cdo)
 class_code=[]
 for offset in range(0x80,0x240,8):
  target=r.unpack(cls+offset,'<Q')[0]
  if r.base<=target<r.base+r.image_size:
   class_code.append({'offset_candidate':hex(offset),'target_rva':hex(target-r.base)})
 vtable=r.unpack(cdo,'<Q')[0];assert r.base<=vtable<r.base+r.image_size
 dispatch=[]
 for slot in range(0,0x780,8):
  target=r.unpack(vtable+slot,'<Q')[0]
  if r.base<=target<r.base+r.image_size:
   dispatch.append({'slot':hex(slot),'target_rva':hex(target-r.base)})
 known={int(x['address'],16):x for x in props.values()};arrays=[]
 for offset in range(0xd0,0x230,8):
  data,n,cap=r.unpack(cls+offset,'<Qii')
  if not pointer(data) or not 0<n<=cap<=2048:continue
  for stride in (8,16):
   try:raw=r.read(data,n*stride)
   except ReadError:continue
   fields=[]
   for i in range(n):
    q=int.from_bytes(raw[i*stride:i*stride+8],'little')&~1
    if q not in known:break
    fields.append({'array_index':i,'property':known[q]['name'],'raw':raw[i*stride:(i+1)*stride].hex()})
   if len(fields)==n:arrays.append({'offset':hex(offset),'stride':stride,'count':n,'fields':fields})
 script=found['NodeLayoutAssetSetGuids'];ops=[]
 for offset in (0xd0,0xd8):
  candidate=r.unpack(script+offset,'<Q')[0]
  if not pointer(candidate):continue
  try:table=r.unpack(candidate,'<Q')[0]
  except ReadError:continue
  if not r.base<=table<r.base+r.image_size:continue
  slots=[]
  for slot in range(0,0x120,8):
   target=r.unpack(table+slot,'<Q')[0]
   if r.base<=target<r.base+r.image_size:slots.append({'slot':hex(slot),'target_rva':hex(target-r.base)})
  ops.append({'scriptstruct_pointer_offset_candidate':hex(offset),'object_address':hex(candidate),
   'vtable_rva':hex(table-r.base),'dispatch_candidates':slots,
   'scope':'Executable-pointer leads; serializer slot ABI not established by this read.'})
 end=client_proof(args.pid)
 for key in ('pid','exe','sha256','process_created_filetime'):assert proof[key]==end[key]
 out={'proof':end,'access':'read-only; no inputs/calls/process writes',
  'class':p.identity(cls),'cdo':identity,'cdo_fields':p.fields(cdo,['NodeGuid','LayoutAssetSetGuids','RootComponent',
   'bAlwaysRelevant','bOnlyRelevantToOwner','bNetUseOwnerRelevancy','bNetTemporary','bNetLoadOnClient',
   'bReplicates','bReplicateMovement','NetCullDistanceSquared','NetUpdateFrequency','MinNetUpdateFrequency','InitialLifeSpan','NetDormancy']),
  'vtable_rva':hex(vtable-r.base),'dispatch':dispatch,'properties':list(props.values()),
  'class_executable_pointer_candidates':class_code,
  'cdo_native_state':{'node_guid':hex(r.unpack(cdo+0x500,'<Q')[0]),
   'initialized_508':r.unpack(cdo+0x508,'<B')[0],
   'layout_array_count':r.unpack(cdo+0x370+0x110,'<i')[0]},
  'validated_class_property_arrays':arrays,'scriptstruct':p.identity(script),
  'scriptstruct_raw_d0_df':r.read(script+0xd0,16).hex(),'scriptstruct_ops_candidates':ops,
  'limits':['Class property arrays are reflection metadata, not proven wire handles.',
   'Native serializer pointer/slot candidates require instruction and ABI binding.']}
 encoded=json.dumps(out,indent=2)
 (ROOT/f'proofs/settlement-runtime-{args.pid}-{end["process_created_filetime"]}.json').write_text(encoded)
 (ROOT/'proofs/settlement-runtime.json').write_text(encoded)
 print(json.dumps({'proof':end,'vtable_rva':out['vtable_rva'],
  'lifecycle_65a9260_slots':[x for x in dispatch if x['target_rva']=='0x65a9260'],
  'class_arrays':[(x['offset'],x['stride'],x['count']) for x in arrays],
  'class_executable_pointer_candidates':class_code,'cdo_native_state':out['cdo_native_state'],
  'ops_candidates':ops},indent=2))
finally:r.close()
