"""Bind loaded settlement/math structs and their native operations as read-only leads."""
import argparse,json,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R.parent/'tools'))
from inspect_movement_prerequisites import MovementProbe
from dump_runtime_reflection import Reader,ReadError,pointer
from protocol_proof import client_proof,EXPECTED_EXE
a=argparse.ArgumentParser();a.add_argument('pid',type=int);args=a.parse_args();proof=client_proof(args.pid)
assert proof['sha256']==json.loads((R/'index/summary.json').read_bytes())['native']['sha256']
r=Reader(args.pid,EXPECTED_EXE)
try:
 p=MovementProbe(r);wanted={'NodeLayoutAssetSetGuids','NodeAssetSetFastArrayItem','AssetSetCompoundId','Transform','Quat','GameplayTagContainer'};found=[]
 for address,obj in p.reflection.objects():
  if obj['name'] not in wanted or p.reflection.class_name(obj['class_address'])!='ScriptStruct':continue
  size=r.unpack(address+0x78,'<i')[0];ops=r.unpack(address+0xd8,'<Q')[0];assert pointer(ops)
  table=r.unpack(ops,'<Q')[0];assert r.base<=table<r.base+r.image_size
  slots=[]
  for slot in range(0,0xd0,8):
   target=r.unpack(table+slot,'<Q')[0]
   if r.base<=target<r.base+r.image_size:slots.append({'slot':hex(slot),'rva':hex(target-r.base),'prefix32':r.read(target,32).hex()})
  found.append({'identity':p.identity(address),'size':size,'properties':p.reflection.properties(r.unpack(address+0x70,'<Q')[0],size),
   'ops_address':hex(ops),'vtable_rva':hex(table-r.base),'dispatch':slots})
 assert {x['identity']['name'] for x in found}==wanted
 end=client_proof(args.pid)
 for key in ('pid','exe','sha256','process_created_filetime'):assert end[key]==proof[key]
 out={'proof':end,'access':'read-only; no game calls/input/process writes','structs':found,
  'limits':['Ops slots are executable dispatch leads; semantic ABI requires native callsite binding.']}
 (R/f'proofs/settlement-struct-ops-{args.pid}-{end["process_created_filetime"]}.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
 (R/'proofs/settlement-struct-ops.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
 print(json.dumps({x['identity']['name']:{'size':x['size'],'vtable':x['vtable_rva'],'slots48_58':[s for s in x['dispatch']if s['slot']in('0x48','0x50','0x58')]} for x in found},indent=2))
finally:r.close()
