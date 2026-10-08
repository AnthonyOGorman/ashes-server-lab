"""Check movement evidence provenance and native links; not gameplay equivalence."""
import hashlib,json,sqlite3,struct,sys
from datetime import datetime,timezone
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'vendor'))
import capstone,pefile
from capstone.x86 import X86_OP_MEM,X86_OP_IMM,X86_REG_R8,X86_REG_R8D,X86_REG_R8W,X86_REG_R8B
report=json.loads((R/'proofs/movement-native-map.json').read_text())
db=sqlite3.connect((R/'index/client-index.sqlite').as_uri()+'?mode=ro',uri=True)
meta=json.loads(db.execute("SELECT value FROM metadata WHERE key='native'").fetchone()[0])
raw=Path(meta['path']).read_bytes();checks=[]
def check(name,result):
    checks.append(dict(name=name,passed=bool(result)))
check('executable hash matches evidence',hashlib.sha256(raw).hexdigest()==report['exe_sha256']==meta['sha256'])
pe=pefile.PE(data=raw,fast_load=True);base=pe.OPTIONAL_HEADER.ImageBase
cs=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);cs.detail=True
def instructions(rva):
    end=db.execute('SELECT end FROM native_ranges WHERE begin=?',(rva,)).fetchone()[0]
    return list(cs.disasm(pe.get_data(rva,end-rva),rva))
check('movement constructor callback',pe.get_data(0x58d657e,5)==bytes.fromhex('e92dc35b00'))
check('movement constructor installs primary table',pe.get_data(0x5e928cd,10)==bytes.fromhex('488d059ce02705488907'))
check('GetMaxSpeed thunk slot',any(i.mnemonic=='call' and any(o.type==X86_OP_MEM and o.mem.disp==0x568 for o in i.operands) for i in instructions(0x3e64f00)))
expected={0x568:0x5ea5370,0xb60:0x5ece600,0xbc0:0x3dcf5a0,0xbc8:0x5e9e420,0xbe8:0x5ec1f80,0xbf0:0x5ec20b0,0xbf8:0x3dd0a90,0xd80:0x5ea4b90,0x978:0x3de4f70}
check('movement table targets',all(struct.unpack('<Q',pe.get_data(0xb110970+s,8))[0]-base==t for s,t in expected.items()))
serialized=instructions(0x63e7a80)
sites=[i for i in serialized if i.mnemonic=='call' and any(o.type==X86_OP_MEM and o.mem.disp==0x188 for o in i.operands)]
check('input serializer has four bit-archive calls',len(sites)==4)
one_bits=0
r8_family={X86_REG_R8,X86_REG_R8D,X86_REG_R8W,X86_REG_R8B}
last_r8_write=None
for instruction in serialized:
    if r8_family.intersection(instruction.regs_access()[1]):
        last_r8_write=instruction
    if instruction in sites:
        one_bits+=last_r8_write is not None and last_r8_write.mnemonic=='mov' and last_r8_write.op_str=='r8d, 1'
    if instruction.mnemonic=='call':
        # Win64 calls may clobber R8; require a new definition for the next call.
        last_r8_write=None
check('four input fields each request one bit',one_bits==4)
pos=struct.unpack('<d',pe.get_data(0x9e08fd8,8))[0];neg=struct.unpack('<d',pe.get_data(0x9e09278,8))[0]
check('direction thresholds preserved',pos==report['input_positive_threshold'] and neg==report['backwards_threshold'])
check('mask on-disk initializers preserved',all(struct.unpack('<I',pe.get_data(int(r,16),4))[0]==v['uint32'] for r,v in report['initial_globals'].items()))
check('walk setter updates reflected flag',pe.get_data(0x6b61ebb,7)==bytes.fromhex('44888169120000') and db.execute("SELECT offset FROM sdk_properties WHERE owner='GameSystemsPlugin.BaseCharacter' AND name='bWantsToWalk'").fetchone()[0]==0x1269)
snapshots=[f for fs in report['instruction_snapshots'].values() for f in fs]
snapshot_ok=True
for item in snapshots:
    proof=json.loads((R/item['file']).read_text());data=pe.get_data(int(proof['rva'],16),proof['bytes'])
    snapshot_ok &= proof['exe_sha256']==meta['sha256'] and hashlib.sha256(data).hexdigest()==proof['fragment_sha256']
check('all native fragment snapshots match executable',snapshot_ok)
manifest=(R/'batches/movement-extended.tsv').read_text().splitlines();missing=[];failed=[]
for line in manifest:
    if not line.strip():continue
    rva=int(line.split('\t')[0],0);path=R/f'decompiled/movement/function_{rva:x}.c'
    if not path.exists():missing.append(hex(rva));continue
    content=path.read_text()
    if meta['sha256'] not in content or 'Decompilation failed:' in content:failed.append(hex(rva))
check('focused pseudocode outputs present and hash-bound',not missing and not failed)
vectors=[]
for x,y in [(0,0),(1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,-1),(pos,neg),(pos*2,neg*2)]:
    flags=[x>pos,x<neg,y>pos,y<neg]
    decoded=[1 if flags[0] else -1 if flags[1] else 0,1 if flags[2] else -1 if flags[3] else 0]
    vectors.append(dict(input=[x,y],ordered_flags=[int(f) for f in flags],decoded=decoded))
out=dict(generated_at=datetime.now(timezone.utc).isoformat(),passed=all(c['passed'] for c in checks),checks=checks,fragment_count=len(snapshots),manifest_ranges=len(manifest),missing=missing,failed=failed,semantic_direction_vectors=vectors,limitations=['Checks bind static evidence and dispatch to the local executable; they do not execute the game or verify the official server.','Direction examples reproduce reviewed branch semantics; not independent native execution or full packet vectors.','Flags are in serializer call order, not an established UDP byte offset.'])
(R/'proofs/movement-verification.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2));db.close();pe.close()
if not out['passed']:raise SystemExit(1)
