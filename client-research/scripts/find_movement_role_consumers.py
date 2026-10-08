"""Bounded offline movement vtable discovery; displacement hits remain leads."""
import hashlib,json,sqlite3,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'vendor'))
import pefile,capstone
from capstone.x86 import X86_OP_MEM,X86_REG_RIP
m=json.loads((R/'index/summary.json').read_bytes())['native']
raw=Path(m['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==m['sha256']
pe=pefile.PE(data=raw,fast_load=True);cs=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);cs.detail=True
db=sqlite3.connect((R/'index/client-index.sqlite').as_uri()+'?mode=ro',uri=True)
vmap=json.loads((R/'proofs/movement-native-map.json').read_bytes());assert vmap['exe_sha256']==m['sha256']
hits=[];seen=set()
for slot in vmap['slots']:
    target=int(slot['target_rva'],16)
    if target in seen:continue
    seen.add(target)
    bounds=db.execute('SELECT begin,end FROM native_ranges WHERE begin=?',(target,)).fetchone()
    if not bounds or bounds[1]-target>65536:continue
    fragments=db.execute('SELECT u.begin,r.end FROM native_unwind u JOIN native_ranges r ON r.begin=u.begin WHERE u.root_begin=? ORDER BY u.begin',(target,)).fetchall() or [bounds]
    matches=[]
    for begin,end in fragments:
        for i in cs.disasm(pe.get_data(begin,end-begin),begin):
            if any(o.type==X86_OP_MEM and o.mem.base!=X86_REG_RIP and o.mem.disp in (0x1f8,0x528,0x529) for o in i.operands):
                matches.append(dict(site=hex(i.address),instruction=i.mnemonic+' '+i.op_str))
    if matches:hits.append(dict(target_rva=hex(target),slots=[s['slot'] for s in vmap['slots'] if s['target_rva']==hex(target)],matches=matches))
out=dict(exe_sha256=m['sha256'],scan='constructor-bound movement table441slots/exception fragments only',hits=hits,
         limits=['Offsets can refer to other objects; hits are not semantic ownership proof.','No process input/access, game calls or server changes.'])
(R/'proofs/movement-role-consumer-leads.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2));db.close();pe.close()
