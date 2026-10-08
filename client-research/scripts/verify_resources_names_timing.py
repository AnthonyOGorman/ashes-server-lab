"""Check saved native evidence fingerprints; does not test gameplay/server equivalence."""
import hashlib,json,struct,sys
from datetime import datetime,timezone
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'vendor'))
import pefile
m=json.loads((R/'index/summary.json').read_text())['native']
raw=Path(m['path']).read_bytes()
checks=[]
def check(name,value): checks.append({'name':name,'passed':bool(value)})
check('executable identity',hashlib.sha256(raw).hexdigest()==m['sha256'])
p=pefile.PE(data=raw,fast_load=True)
base=p.OPTIONAL_HEADER.ImageBase
facts=[]
for slot,target in ((0xb90,0x3e102b0),(0xba0,0x3df5240)):
    data=p.get_data(0xb110970+slot,8)
    check(f'timing dispatch {slot:x}',struct.unpack('<Q',data)[0]-base==target)
    facts.append({'rva':hex(0xb110970+slot),'hex':data.hex(),'target':hex(target)})
for rva,value in ((0xd26eedc,1.75),(0x9ddb238,1.),(0x9df45b0,.5),(0x9e08f14,9.999999974752427e-7)):
    data=p.get_data(rva,4)
    check(f'timing constant {rva:x}',struct.unpack('<f',data)[0]==value)
    facts.append({'rva':hex(rva),'hex':data.hex(),'float':value})
check('pawn component name getter bytes',p.get_data(0x6b3d100,14)==bytes.fromhex('488b81c8070000480530010000c3'))
check('float stat bit reinterpretation bytes',p.get_data(0x6175ec0,13)==bytes.fromhex('8b0189442408f30f10442408c3'))
batches=['resources-names-timing','resources-names-timing-2','resources-names-timing-3','resources-names-timing-4','resources-replication','resources-replication-routing']
snapshots=[];outputs=[];missing=[];resolved_leaves=[]
for batch in batches:
    manifest=R/'batches'/f'{batch}.tsv'
    target=json.loads((R/'proofs'/f'{batch}-targets.json').read_text())
    check(f'{batch} identity',target['exe_sha256']==m['sha256'])
    for rv in target['missing']:
        if rv=='0x6b3d100':resolved_leaves.append({'rva':rv,'proof':'proofs/identity-name-getter-6b3d100.json'})
        else:missing.append(rv)
    for t in target['targets']:snapshots.extend(t['snapshots'])
    for line in manifest.read_text().splitlines():
        if not line.strip():continue
        rv=int(line.split('\t')[0],0)
        file=R/'decompiled'/batch/f'function_{rv:x}.c'
        if not file.exists():missing.append(str(file));continue
        text=file.read_text()
        check(f'{batch} output {rv:x}',m['sha256'] in text and 'Decompilation failed:' not in text)
        outputs.append({'path':str(file.relative_to(R)),'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
snapshots += ['proofs/timing-leaf-3de2340.json','proofs/timing-substep-3de2380.json','proofs/identity-name-getter-6b3d100.json','proofs/resource-float-getter-6175ec0.json','proofs/timing-effective-dilation-3b7d520.json']
for file in snapshots:
    proof=json.loads((R/file).read_text());rv=int(proof['rva'],16);n=int(proof['end'],16)-rv
    data=p.get_data(rv,n)
    check(file,proof['exe_sha256']==m['sha256'] and hashlib.sha256(data).hexdigest()==proof['fragment_sha256'] and (R/file).with_suffix('.bin').read_bytes()==data)
check('all manifest gaps accounted for',not missing)
out={'verified_at':datetime.now(timezone.utc).isoformat(),'passed':all(c['passed'] for c in checks),'exe_sha256':m['sha256'],'checks':checks,'manifest_ranges':len(outputs),'snapshot_count':len(snapshots),'resolved_no_exception_leaves':resolved_leaves,'missing':missing,'data_facts':facts,'outputs':outputs,'limitations':['Static fingerprint/selected native-link verification, not gameplay equivalence or a live server timing test.','Native compact references and SDK reflected record layouts must remain separate.','Live resource identity/config readbacks are owned by CPP implementation and require session provenance.']}
(R/'proofs/resources-names-timing-verification.json').write_text(json.dumps(out,indent=2))
print(json.dumps({k:out[k] for k in ('verified_at','passed','manifest_ranges','snapshot_count','missing')},indent=2))
p.close()
if not out['passed']:raise SystemExit(1)
