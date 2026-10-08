"""Bind historical controller vtable gates to exact static executable bytes."""
import hashlib, json, struct, sys
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'vendor'))
import capstone, pefile
m=json.loads((R/'index/summary.json').read_bytes())['native']
raw=Path(m['path']).read_bytes(); assert hashlib.sha256(raw).hexdigest()==m['sha256']
source=R/'proofs/controller-playerstate-live.json'; prior=json.loads(source.read_bytes())
assert prior['proof']['sha256']==m['sha256']
pe=pefile.PE(data=raw,fast_load=True); base=pe.OPTIONAL_HEADER.ImageBase
vtable=int(prior['controller_onrep_playerstate']['table_rva'],16)
entries=[]
disassembler=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
for slot,label in ((0x910,'SetIgnoreMoveInput'),(0x918,'ResetIgnoreMoveInput'),
                   (0x920,'IsMoveInputIgnored'),(0xb70,'ClientIgnoreMoveInput_Implementation')):
    at=vtable+slot; target=struct.unpack('<Q',pe.get_data(at,8))[0]-base
    assert 0<target<pe.OPTIONAL_HEADER.SizeOfImage
    instructions=list(disassembler.disasm(pe.get_data(target,128),target))
    terminal=next(x for x in instructions if x.mnemonic in ('ret','jmp'))
    length=terminal.address+terminal.size-target
    assert length<=64 and not any(x.mnemonic.startswith('j') for x in instructions if x.address<terminal.address)
    fragment=pe.get_data(target,length)
    name=f'loading-input-gate-{target:x}'
    (R/f'proofs/{name}.bin').write_bytes(fragment)
    lines=[f'{x.address:08x} {x.bytes.hex():24} {x.mnemonic} {x.op_str}' for x in instructions if x.address<=terminal.address]
    (R/f'proofs/{name}.asm').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    entries.append({'label':label,'slot':hex(slot),'vtable_rva':hex(vtable),'target_rva':hex(target),
        'entry_bytes32':pe.get_data(target,32).hex(),'complete_selected_linear_leaf_bytes':fragment.hex(),
        'fragment_sha256':hashlib.sha256(fragment).hexdigest(),'instructions':lines,
        'boundary':'Selected linear leaf through RET or pure tail-JMP; no exception range claim'})
out={'exe_sha256':m['sha256'],'historical_source':str(source),
     'historical_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'entries':entries,
     'limits':['Historical controller vtable plus static bytes; current connection/vtable/RPC field cache still requires readback.',
               'Only read evidence/executable; no game calls, inputs, process access or server edits.']}
(R/'proofs/loading-controller-gate-targets.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps(entries,indent=2)); pe.close()
