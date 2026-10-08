"""Hash-bound restart reset and gravity/jump discovery receipts, offline only."""
import hashlib,json,struct,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'vendor'))
import pefile,capstone
m=json.loads((R/'index/summary.json').read_bytes())['native'];raw=Path(m['path']).read_bytes()
assert hashlib.sha256(raw).hexdigest()==m['sha256'];pe=pefile.PE(data=raw,fast_load=True);base=pe.OPTIONAL_HEADER.ImageBase
cs=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
snapshots=[];outputs=[]
for batch in ['loading-restart-reset','jump-gravity-getters']:
    manifest=json.loads((R/f'proofs/{batch}-targets.json').read_bytes());assert manifest['exe_sha256']==m['sha256']
    for target in manifest['targets']:
        for path in target['snapshots']:
            p=R/path;proof=json.loads(p.read_bytes());assert proof['exe_sha256']==m['sha256']
            data=pe.get_data(int(proof['rva'],16),proof['bytes']);assert hashlib.sha256(data).hexdigest()==proof['fragment_sha256']
            assert p.with_suffix('.bin').read_bytes()==data
            snapshots.append(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
        p=R/f'decompiled/{batch}/function_{int(target["rva"],16):x}.c';text=p.read_text()
        assert m['sha256'] in text and 'Decompilation failed:' not in text
        outputs.append(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
bindings=[]
for table,slot,target,label in [(0xb7165c0,0xb30,0x4412750,'ClientRestart'),(0xb7165c0,0x940,0x4432570,'ResetIgnoreInputFlags'),
                              (0xb7bf4e8,0xcf0,0x6b411a0,'GravityModifier'),(0xb7bf4e8,0xcf8,0x6b4d430,'optional falling modifier predicate')]:
    assert struct.unpack('<Q',pe.get_data(table+slot,8))[0]-base==target
    bindings.append(dict(table_rva=hex(table),slot=hex(slot),target_rva=hex(target),label=label))
assert pe.get_data(0x44127db,6).hex()=='ff9040090000'
instructions=list(cs.disasm(pe.get_data(0x6b4d430,64),0x6b4d430));terminal=next(i for i in instructions if i.mnemonic=='ret')
assert [(i.mnemonic,i.op_str) for i in instructions if i.mnemonic.startswith('j') and i.address<terminal.address]==[
    ('je','0x6b4d451'),('jb','0x6b4d451'),('jmp','0x612dae0')]
leaf=pe.get_data(0x6b4d430,terminal.address+terminal.size-0x6b4d430)
(R/'proofs/gravity-falling-predicate-dispatch.bin').write_bytes(leaf)
lines=[f'{i.address:08x} {i.bytes.hex():24} {i.mnemonic} {i.op_str}' for i in instructions if i.address<=terminal.address]
(R/'proofs/gravity-falling-predicate-dispatch.asm').write_text('\n'.join(lines)+'\n')
out=dict(status='static_restart_gravity_evidence_verified',exe_sha256=m['sha256'],bindings=bindings,outputs=outputs,snapshots=snapshots,
         falling_predicate_dispatch=dict(bytes=leaf.hex(),sha256=hashlib.sha256(leaf).hexdigest(),instructions=lines,
             boundary='Selected multi-block dispatch to false RET or external tail612DAE0; callee semantics separate'),
         limits=['Native bindings/saved decompilations and snapshot fingerprints only; no client execution or equivalence tests.',
             'Configured stat native cache identity, active modifiers and effective fresh values remain required.',
             'Some reflected thunks/falling predicate are selected fragments rather than exception ranges.',
             'No process access/input/writes, RPCs, server source changes or services.'])
(R/'proofs/restart-gravity-evidence-verification.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(dict(status=out['status'],outputs=len(outputs),snapshots=len(snapshots),falling_predicate=lines),indent=2));pe.close()
