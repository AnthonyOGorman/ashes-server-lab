"""Hash-checked static disassembly of an explicit bounded fragment."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
RESEARCH=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(RESEARCH/'vendor'))
import capstone
import pefile
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('rva',type=lambda x:int(x,0));parser.add_argument('--bytes',type=int,default=256)
parser.add_argument('--output',type=Path);parser.add_argument('--stop-at-terminal',action='store_true')
args=parser.parse_args()
if not 1<=args.bytes<=65536:parser.error('bytes must be 1..65536')
metadata=json.loads((RESEARCH/'index/summary.json').read_text())['native']
path=Path(metadata['path']);data=path.read_bytes()
if hashlib.sha256(data).hexdigest()!=metadata['sha256']:raise RuntimeError('Executable changed')
pe=pefile.PE(data=data,fast_load=True)
section=pe.get_section_by_rva(args.rva)
if not section or not section.Characteristics&0x20000000:raise RuntimeError('RVA is not in executable code')
decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);decoder.detail=True
lines=[];used=0
for inst in decoder.disasm(pe.get_data(args.rva,args.bytes),args.rva):
    lines.append(f'{inst.address:08x}  {inst.bytes.hex():24}  {inst.mnemonic} {inst.op_str}')
    used=inst.address+inst.size-args.rva
    if args.stop_at_terminal and (inst.mnemonic in ('ret','retf','jmp','int3','ud2') or inst.group(capstone.CS_GRP_JUMP)):break
fragment=pe.get_data(args.rva,used)
proof={'exe_sha256':metadata['sha256'],'rva':hex(args.rva),'end':hex(args.rva+used),'fragment_sha256':hashlib.sha256(fragment).hexdigest(),'boundary':'explicit bounded fragment; not a full function claim','instructions':lines}
if args.output:
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.with_suffix('.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
    args.output.with_suffix('.asm').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    args.output.with_suffix('.bin').write_bytes(fragment)
print(json.dumps(proof,indent=2));pe.close()
