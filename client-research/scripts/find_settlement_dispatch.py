"""Read-only PE/index xrefs for exact custom-delta error strings and serializer constants."""
import hashlib,json,re,sqlite3,struct,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'vendor'))
import capstone,pefile
meta=json.loads((R/'index/summary.json').read_bytes())['native'];raw=Path(meta['path']).read_bytes()
assert hashlib.sha256(raw).hexdigest()==meta['sha256']
pe=pefile.PE(data=raw,fast_load=True);d=sqlite3.connect((R/'index/client-index.sqlite').as_uri()+'?mode=ro',uri=True)
cs=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);targets={0xaa7d610,0xaa7d710,0x9ddb290};hits=[]
for sec in pe.sections:
 if not sec.Characteristics&0x20000000:continue
 data=sec.get_data();base=sec.VirtualAddress
 for m in re.finditer(rb'[\x48\x4c][\x8d\x8b][\x05\x0d\x15\x1d\x25\x2d\x35\x3d]',data):
  at=m.start();instruction=base+at
  if at+7>len(data):continue
  target=instruction+7+struct.unpack_from('<i',data,at+3)[0]
  if target not in targets:continue
  bounds=d.execute('SELECT begin,end FROM native_ranges WHERE begin<=? AND end>? ORDER BY begin DESC LIMIT 1',(instruction,instruction)).fetchone()
  if not bounds:continue
  decoded=list(cs.disasm(pe.get_data(bounds[0],bounds[1]-bounds[0]),bounds[0]))
  inst=next((x for x in decoded if x.address==instruction),None)
  if inst is None or inst.size!=7:continue
  root=d.execute('SELECT root_begin FROM native_unwind WHERE begin=?',(bounds[0],)).fetchone()
  hits.append({'instruction':hex(instruction),'target':hex(target),'fragment':hex(bounds[0]),
   'root':hex(root[0] if root else bounds[0]),'bytes':inst.bytes.hex(),'disassembly':inst.mnemonic+' '+inst.op_str})
out={'exe_sha256':meta['sha256'],'hits':hits,'limits':['Validated instruction boundaries; reviewed xrefs are leads, not function identities.']}
(R/'proofs/settlement-dispatch-xrefs.json').write_text(json.dumps(out,indent=2),encoding='utf-8');print(json.dumps(out,indent=2))
