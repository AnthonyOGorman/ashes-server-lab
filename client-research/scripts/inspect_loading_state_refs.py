"""Bounded native instruction review for loading show/hide and provider leads."""
import hashlib,json,sqlite3,struct,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'vendor'))
import capstone,pefile
d=sqlite3.connect((R/'index/client-index.sqlite').as_uri()+'?mode=ro',uri=True)
m=json.loads((R/'index/summary.json').read_bytes())['native'];raw=Path(m['path']).read_bytes()
assert hashlib.sha256(raw).hexdigest()==m['sha256'];pe=pefile.PE(data=raw,fast_load=True)
cs=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);cs.detail=True
strings={rva:value for rva,value in d.execute('SELECT rva,value FROM strings WHERE rva BETWEEN ? AND ?',(0xb87a000,0xb87b500))}
hits=[]
for begin,end in d.execute('SELECT begin,end FROM native_ranges WHERE begin BETWEEN ? AND ? ORDER BY begin',(0x6500000,0x6515000)):
    for i in cs.disasm(pe.get_data(begin,end-begin),begin):
        for o in i.operands:
            if o.type==capstone.x86.X86_OP_MEM and o.mem.base==capstone.x86.X86_REG_RIP:
                target=i.address+i.size+o.mem.disp
                if target in strings or 0xb87b100<=target<=0xb87b3f0:
                    value=strings.get(target)
                    if value is None:
                        b=pe.get_data(target,320);ptr=struct.unpack('<Q',b[:8])[0]-pe.OPTIONAL_HEADER.ImageBase
                        value=strings.get(ptr,'Non-string RIP target; do not infer a text value')
                    hits.append(dict(begin=hex(begin),rva=hex(i.address),target=hex(target),value=value,instruction=f'{i.mnemonic} {i.op_str}'))
out=dict(exe_sha256=m['sha256'],range='native exception ranges starting6500000..6515000; RIP-relative operands only',hits=hits)
(R/'proofs/loading-screen-state-refs.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(hits,indent=2))
d.close();pe.close()
