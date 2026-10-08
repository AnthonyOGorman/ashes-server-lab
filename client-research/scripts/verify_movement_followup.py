"""Verify native evidence for the implementation handoff, not server/gameplay equivalence."""
import hashlib,json,sqlite3,struct,sys
from datetime import datetime,timezone
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'vendor'))
import capstone,pefile
from capstone.x86 import X86_OP_MEM,X86_REG_RIP
d=sqlite3.connect((R/'index/client-index.sqlite').as_uri()+'?mode=ro',uri=True)
meta=json.loads(d.execute("SELECT value FROM metadata WHERE key='native'").fetchone()[0]);raw=Path(meta['path']).read_bytes()
checks=[]
def check(name,result):checks.append(dict(name=name,passed=bool(result)))
check('exact executable identity',hashlib.sha256(raw).hexdigest()==meta['sha256'])
p=pefile.PE(data=raw,fast_load=True);base=p.OPTIONAL_HEADER.ImageBase
c=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);c.detail=True
def ptr(table,slot):return struct.unpack('<Q',p.get_data(table+slot,8))[0]-base
check('CalcVelocity and overspeed dispatch',ptr(0xb110970,0x7e8)==0x5e9aa10 and ptr(0xb110970,0x570)==0x3e4ebe0)
check('MoveSpeedMult callback dispatch',ptr(0xb741268,0xdb8)==ptr(0xb7bf4e8,0xdb8)==0x6b527c0)
check('cached speed getter field',p.get_data(0x6b3cdc0,9)==bytes.fromhex('f30f1081a0130000c3'))
ctor=list(c.disasm(p.get_data(0x5e928b0,0x759),0x5e928b0))
table_installed=False
for inst,nxt in zip(ctor,ctor[1:]):
    references_table=any(o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP and inst.address+inst.size+o.mem.disp==0xb111938 for o in inst.operands)
    if inst.mnemonic=='lea' and references_table and nxt.mnemonic=='mov' and nxt.operands[0].type==X86_OP_MEM and nxt.operands[0].mem.disp==0x1e0:
        table_installed=True
check('prediction interface installs known table',table_installed and ptr(0xb111938,0x28)==0x5ea6060)
check('prediction allocator dispatch',ptr(0xb7cd4b0,0x10)==0x5e95b40)
check('saved move sender and setup dispatch',ptr(0xb7cd440,0x50)==0x5ea46c0 and ptr(0xb7cd440,0x10)==0x5ec39a0)
instructions=list(c.disasm(p.get_data(0x5ea46c0,0x3f),0x5ea46c0))
mask_refs={i.address+i.size+o.mem.disp for i in instructions for o in i.operands if o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP}
check('sender references all three receiver mask globals',{0xd378c7c,0xd378c80,0xd378c84}.issubset(mask_refs))
check('overspeed tolerance initializer',struct.unpack('<f',p.get_data(0x9f7a7a0,4))[0]==1.0099999904632568)
check('sprint getters preserve exact instance offsets',p.get_data(0x6c181a0,9)==bytes.fromhex('f30f1081f8240000c3') and p.get_data(0x6c11b80,9)==bytes.fromhex('f30f108100250000c3'))
targets=json.loads((R/'proofs/movement-followup-targets.json').read_text());snapshots=[f for t in targets['targets'] for f in t['snapshots']]
snapshots += ['proofs/movement-overspeed-leaf.json','proofs/movement-saved-base-compressed-flags.json','proofs/movement-player-sprint-speed-getter.json','proofs/movement-player-crouch-sprint-speed-getter.json']
ok=True
for file in snapshots:
    proof=json.loads((R/file).read_text());rv=int(proof['rva'],16);size=proof.get('bytes',int(proof['end'],16)-rv)
    ok &= proof['exe_sha256']==meta['sha256'] and hashlib.sha256(p.get_data(rv,size)).hexdigest()==proof['fragment_sha256']
check('all followup snapshots match executable',ok)
bad=[]
for t in targets['targets']:
    file=R/f"decompiled/movement-followup/function_{int(t['rva'],16):x}.c"
    if not file.exists():bad.append(str(file));continue
    text=file.read_text();
    if meta['sha256'] not in text or 'Decompilation failed:' in text:bad.append(str(file))
check('manifest outputs are present and hash-bound',not bad)
out=dict(verified_at=datetime.now(timezone.utc).isoformat(),passed=all(x['passed'] for x in checks),checks=checks,manifest_ranges=len(targets['targets']),snapshot_count=len(snapshots),missing=bad,limitations=['Static provenance/selected link checks, not complete control-flow or server compatibility tests.','Constructor-installed tables may have runtime subclass overrides; runtime mask values remain unmeasured.'])
(R/'proofs/movement-followup-verification.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2));d.close();p.close()
if not out['passed']:raise SystemExit(1)
