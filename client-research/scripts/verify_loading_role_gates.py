"""Verify saved static role/input consumers; this does not execute client physics."""
import hashlib,json,struct,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'vendor'))
import pefile
m=json.loads((R/'index/summary.json').read_bytes())['native'];raw=Path(m['path']).read_bytes()
assert hashlib.sha256(raw).hexdigest()==m['sha256'];pe=pefile.PE(data=raw,fast_load=True);base=pe.OPTIONAL_HEADER.ImageBase
source=R/'proofs/loading-pawn-targets.json';d=json.loads(source.read_bytes());assert d['exe_sha256']==m['sha256']
for t in d['targets']:
    target=int(t['target_rva'],16);assert struct.unpack('<Q',pe.get_data(int(t['table_rva'],16)+int(t['slot'],16),8))[0]-base==target
    assert hashlib.sha256(pe.get_data(target,256)).hexdigest()==t['fragment_sha256']
jump=pe.get_data(0x3d5c010,18);assert jump.hex()=='80892805000008c7812c05000000000000c3'
(R/'proofs/loading-character-jump-leaf.bin').write_bytes(jump)
outputs=[]
for batch,rvas in [('loading-movement-tick',[0x3e0b830,0x5ec95d0,0x3dc41d0,0x433a900,0x433a940,0x431f290]),
                   ('loading-simulated-tick',[0x5ec5e20,0x3dc0be0,0x3e2fe30])]:
    for rva in rvas:
        p=R/f'decompiled/{batch}/function_{rva:x}.c';text=p.read_text()
        assert m['sha256'] in text and 'Decompilation failed:' not in text
        outputs.append(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
v=json.loads((R/'proofs/movement-native-map.json').read_bytes())
expected={0x480:0x5ec95d0,0xad0:0x5ec5e20,0xad8:0x5ec5020,0x8b8:0x5e9fbd0}
for slot,target in expected.items():
    assert next(s for s in v['slots'] if int(s['slot'],16)==slot)['target_rva']==hex(target)
    assert struct.unpack('<Q',pe.get_data(0xb110970+slot,8))[0]-base==target
out=dict(status='static_input_role_dispatch_verified',exe_sha256=m['sha256'],decompiled_outputs=outputs,
    pawn_targets_source=dict(path=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest()),
    jump=dict(rva='0x3d5c010',complete_leaf_bytes=jump.hex(),sha256=hashlib.sha256(jump).hexdigest(),
              pressed_jump_offset='0x528',pressed_jump_mask=8,hold_time_offset='0x52c',counter_or_role_check=False),
    dispatch={hex(k):hex(val) for k,val in expected.items()},
    observations=['Base movement Tick3E0B830 dispatches Role1 to AD0 instead of Role>=2 input/prediction branch.',
      'Custom Tick5EC95D0 calls base first and caches Role1 local-controller pose/velocity afterwards.',
      'AD0 wrapper delegates ordinary simulated movement AD8; Role1 alone does not freeze gravity.'],
    limits=['Static dispatch/byte proof, not runtime simulation equivalence or all transitive call analysis.',
      'Fresh pawn role/counter0->1->0, supported grounded pose/floor and immediate-input trial required.',
      'No client calls, writes, process input/access, packets or server changes.'])
(R/'proofs/loading-role-gate-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(dict(status=out['status'],outputs=len(outputs))));pe.close()
