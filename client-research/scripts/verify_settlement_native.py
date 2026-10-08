"""Verify settlement batch/source fingerprints and independently bound receive/load links."""
import hashlib,json,struct,sys
from datetime import datetime,timezone
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'vendor'))
import pefile
meta=json.loads((R/'index/summary.json').read_bytes())['native']
raw=Path(meta['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==meta['sha256']
pe=pefile.PE(data=raw,fast_load=True);base=pe.OPTIONAL_HEADER.ImageBase
batches=['settlement-streaming','settlement-assets','settlement-bootstrap',
 'settlement-array-receiver','settlement-construction','settlement-actor-constructor',
 'settlement-level-creation','settlement-level-creation-retry','settlement-level-load-helper',
 'settlement-transform-bindings','settlement-world-class','settlement-custom-delta',
 'settlement-fastarray-receiver','settlement-quat-net','settlement-delta-dispatch',
 'settlement-plot-client','settlement-plot-component']
checks=[];outputs=[];snapshots=[];gaps=[];failures=[]
def check(name,value): checks.append({'name':name,'passed':bool(value)})
for batch in batches:
 t=json.loads((R/f'proofs/{batch}-targets.json').read_bytes());check(batch+' identity',t['exe_sha256']==meta['sha256'])
 for rv in t['missing']:gaps.append({'batch':batch,'rva':rv,'reason':'No indexed exception entry; direct leaf/trampoline bytes separately reviewed'})
 for target in t['targets']:
  rv=int(target['rva'],16);f=R/f'decompiled/{batch}/function_{rv:x}.c';s=f.read_text(encoding='utf-8')
  check(str(f.relative_to(R))+' header',meta['sha256'] in s and 'Entry range: '+target['rva'] in s)
  if 'Decompilation failed:' in s:failures.append(f.relative_to(R).as_posix())
  outputs.append({'path':str(f.relative_to(R)),'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'complete':'Decompilation failed:' not in s})
  for rel in target['snapshots']:
   fp=R/rel;proof=json.loads(fp.read_bytes());start=int(proof['rva'],16);n=int(proof['end'],16)-start;data=pe.get_data(start,n)
   check(rel,proof['exe_sha256']==meta['sha256'] and hashlib.sha256(data).hexdigest()==proof['fragment_sha256'] and fp.with_suffix('.bin').read_bytes()==data);snapshots.append(rel)
check('Only preserved 30s level-creation failure',failures==['decompiled/settlement-level-creation/function_65a25a0.c'])
for slot,target in ((0x2a8,0x3bca830),(0x2b0,0x65a9260)):
 check(f'CDO receive slot {slot:x}',struct.unpack('<Q',pe.get_data(0xb4a11e8+slot,8))[0]-base==target)
for source,target in ((0x5b80160,0x65a8f40),(0x5b7f3b0,0x65a1430)):
 b=pe.get_data(source,26);check(f'VM cursor then tail jump {source:x}',
  b[:21]==bytes.fromhex('488b42204533c04885c0410f95c04c03c04c894220') and
  b[21]==0xe9 and source+26+struct.unpack('<i',b[22:])[0]==target)
 name=f'settlement-reflection-thunk-{source:x}'
 proof={'exe_sha256':meta['sha256'],'rva':hex(source),'end':hex(source+26),
  'fragment_sha256':hashlib.sha256(b).hexdigest(),'target_rva':hex(target),
  'scope':'Complete 26-byte reflected VM thunk; no exception-range claim'}
 (R/f'proofs/{name}.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
 (R/f'proofs/{name}.bin').write_bytes(b)
check('Native load helper matches reflected LoadLevelInstanceBySoftObjectPtr',
 'FUN_144189470' in (R/'decompiled/settlement-level-load-helper/function_3af0da0.c').read_text())
check('Quat W reconstruction unit constant',struct.unpack('<d',pe.get_data(0x9ddb290,8))[0]==1.)
for rv,name in ((0xb55af88,'RoadBase'),(0xb144b20,'AoCNodePlotComponent')):
 data=pe.get_data(rv,128);end=next(i for i in range(0,len(data),2) if data[i:i+2]==b'\0\0')
 check(f'Selected native class name {rv:x}',data[:end].decode('utf-16-le')==name)
check('Client SetNodePlotState target is shared empty RET0 stub',pe.get_data(0x131c2f0,3)==bytes.fromhex('c20000'))
node_call=pe.get_data(0x658b71a,5)
check('Plot initializer node lookup directly calls shared zero-return stub',
 node_call[0]==0xe8 and 0x658b71f+struct.unpack('<i',node_call[1:])[0]==0x131c360 and
 pe.get_data(0x131c360,3)==bytes.fromhex('33c0c3'))
check('Plot initializer requires nonnull lookup before plot-map path',
 pe.get_data(0x658b71f,9)==bytes.fromhex('4885c00f85a9020000'))
node_stub=pe.get_data(0x131c360,3)
(R/'proofs/settlement-plot-state-stub.json').write_text(json.dumps({
 'exe_sha256':meta['sha256'],'call_rva':'0x658b71a','lookup_target_rva':'0x131c360',
 'lookup_bytes':node_stub.hex(),'lookup_fragment_sha256':hashlib.sha256(node_stub).hexdigest(),
 'nonnull_branch_rva':'0x658b9d1',
 'scope':'The shipped plot initializer has a zero-return node lookup; saved successful-path pseudocode is unreachable through this call in this build. No claim about the original dedicated-server implementation.'
},indent=2),encoding='utf-8')
for vtable,slot,thunk,jump_at,target in ((0xb49c8d8,0x58,0x5b76490,3,0x5b7e440),
 (0x9e8eda0,0x50,0x16c7780,5,0x1438440)):
 check(f'CppStructOps {vtable:x}/{slot:x}',struct.unpack('<Q',pe.get_data(vtable+slot,8))[0]-base==thunk)
 b=pe.get_data(thunk,jump_at+5)
 check(f'Ops thunk {thunk:x}',b[jump_at]==0xe9 and thunk+jump_at+5+struct.unpack('<i',b[jump_at+1:])[0]==target)
out={'verified_at':datetime.now(timezone.utc).isoformat(),'exe_sha256':meta['sha256'],
 'passed':all(x['passed'] for x in checks),'checks':checks,'outputs':outputs,
 'snapshot_count':len(snapshots),'exception_entry_gaps':gaps,'preserved_failures':failures,
 'limits':['Static fingerprints and selected dispatch links; not live wire/streaming/collision acceptance.',
 'NodeLayout custom delta and Quat ops are independently bound; earlier cleanup/noop candidates remain excluded.',
 'Native exception fragments and decompiler types are not complete original source.']}
(R/'proofs/settlement-native-verification.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps({'passed':out['passed'],'outputs':len(outputs),'snapshots':len(snapshots),'exception_entry_gaps':gaps,'preserved_failures':failures},indent=2))
assert out['passed'];pe.close()
