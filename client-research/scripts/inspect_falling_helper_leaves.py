"""Hash-bound static leaf discovery/constants; no live client access or input.

Run only outside the coordinated input window. Prefixes are explicitly partial.
"""
import hashlib,json,struct,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'vendor'))
import pefile,capstone
meta=json.loads((R/'index/summary.json').read_bytes())['native']
raw=Path(meta['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==meta['sha256']
pe=pefile.PE(data=raw,fast_load=True);base=pe.OPTIONAL_HEADER.ImageBase
cs=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
bindings=[]
for slot,target in [(0x888,0x3ddc2f0),(0x808,0x5ea51c0),(0x810,0x5ea51d0)]:
    assert struct.unpack('<Q',pe.get_data(0xb110970+slot,8))[0]-base==target
    bindings.append(dict(table_rva='0xb110970',slot=hex(slot),target_rva=hex(target)))
prefixes=[]
for rva in [0x5ea51c0,0x5ea51d0,0x3de2380]:
    data=pe.get_data(rva,128)
    item=dict(rva=hex(rva),bytes=len(data),fragment_sha256=hashlib.sha256(data).hexdigest(),
        boundary='128-byte discovery prefix; no inferred exception range or complete logical function claim',
        instructions=[f'{i.address:08x} {i.bytes.hex():24} {i.mnemonic} {i.op_str}' for i in cs.disasm(data,rva)])
    path=R/f'proofs/falling-helper-prefix-{rva:x}';path.with_suffix('.bin').write_bytes(data)
    path.with_suffix('.json').write_text(json.dumps(dict(exe_sha256=meta['sha256'],**item),indent=2)+'\n')
    prefixes.append(item)
constants=[]
for rva,fmt in [(0x9ddb278,'<d'),(0x9ddb290,'<d'),(0x9ddb208,'<d'),(0x9df1760,'<d'),(0x9ddb1e0,'<f'),(0xd26ee98,'<i'),(0x3de239e+0x6012212,'<f'),(0x3de23aa+0x6026b6a,'<f')]:
    data=pe.get_data(rva,struct.calcsize(fmt));constants.append(dict(rva=hex(rva),format=fmt,bytes=data.hex(),on_disk_value=struct.unpack(fmt,data)[0]))
braking_table=pe.get_data(0x5ea522c,28);targets=list(struct.unpack('<7I',braking_table))
assert all(0x5ea51f0<=t<=0x5ea5226 for t in targets)
assert targets[3]==0x5ea51f9 and pe.get_data(targets[3],9)==bytes.fromhex('f30f1081f4020000c3')
out=dict(exe_sha256=meta['sha256'],bindings=bindings,prefixes=prefixes,constants=constants,
    braking_switch=dict(table_rva='0x5ea522c',raw=braking_table.hex(),mode_targets={str(i):hex(t) for i,t in enumerate(targets)},
        falling_mode=3,falling_target='0x5ea51f9',falling_field_offset='0x2f4',falling_target_bytes='f30f1081f4020000c3'),
    limits=['Static on-disk values; mutable apex toggle requires current live binding/readback before assuming enabled.',
        'Saved prefixes do not replace exception/unwind boundaries; bytes after early return may belong to another function.',
        'No live process read, writes, game calls, packets or input.'])
(R/'proofs/falling-helper-leaves.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(dict(status='static_falling_helper_discovery_saved',bindings=bindings,constants=constants),indent=2));pe.close()
