"""Decode first straight-line entry blocks omitted by the PE exception table.

These bounded entry blocks are NOT claimed to be full function boundaries.
"""
import json
import sqlite3
import sys
import bisect
import argparse
import hashlib
from pathlib import Path
RESEARCH=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(RESEARCH/'vendor'))
import capstone
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
import pefile
db=sqlite3.connect(RESEARCH/'index/client-index.sqlite')
native=json.loads(db.execute("SELECT value FROM metadata WHERE key='native'").fetchone()[0])
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--core-callees',action='store_true',help='Include direct calls from registered game/Intrepid entry points.')
args=parser.parse_args()
with open(native['path'],'rb') as file:
    digest=hashlib.file_digest(file,'sha256').hexdigest() if hasattr(hashlib,'file_digest') else hashlib.sha256(file.read()).hexdigest()
if digest!=native['sha256']:raise SystemExit('Executable hash changed; refusing mixed-build index.')
pe=pefile.PE(native['path'],fast_load=True)
base=pe.OPTIONAL_HEADER.ImageBase
decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);decoder.detail=True
db.execute('CREATE TABLE IF NOT EXISTS entry_blocks(begin INTEGER PRIMARY KEY,end INTEGER,status TEXT,instructions INTEGER)')
ranges=db.execute('SELECT begin,end FROM native_ranges ORDER BY begin').fetchall()
starts=[row[0] for row in ranges]
done={row[0] for row in db.execute('SELECT begin FROM entry_blocks')}
candidates=[]
targets={r[0] for r in db.execute('SELECT DISTINCT rva FROM native_labels')}
if args.core_callees:
    targets.update(r[0] for r in db.execute('''SELECT DISTINCT c.target_rva FROM code_refs c JOIN native_labels n ON n.rva=c.source_begin WHERE c.kind="direct_call" AND n.kind="native_registration_candidate" AND (n.name LIKE "GameSystemsPlugin.%" OR n.name LIKE "Intrepid.%" OR n.name LIKE "IntrepidNet.%" OR n.name LIKE "IntrepidEOS.%")''') if r[0] is not None)
for target in sorted(targets):
    pos=bisect.bisect_right(starts,target)-1
    if target not in done and (pos<0 or ranges[pos][1]<=target):
        candidates.append(target)
for begin in candidates:
    section=pe.get_section_by_rva(begin)
    if not section or not section.Characteristics&0x20000000:continue
    end=begin;refs=[];count=0;status='bounded_limit'
    for inst in decoder.disasm(pe.get_data(begin,256),base+begin):
        rva=inst.address-base;count+=1;end=rva+inst.size
        if inst.mnemonic in ('int3','ud2'):
            end=rva;status='trap_boundary';break
        if inst.mnemonic in ('call','jmp'):
            target=inst.operands[0].imm-base if inst.operands[0].type==X86_OP_IMM else None
            kind=('direct_' if target is not None else 'indirect_')+inst.mnemonic
            refs.append((begin,rva,target,kind,inst.mnemonic+' '+inst.op_str))
        for op in inst.operands:
            if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
                refs.append((begin,rva,end+op.mem.disp,'rip_relative',inst.mnemonic+' '+inst.op_str))
        if inst.mnemonic in ('ret','retf','jmp') or inst.group(capstone.CS_GRP_JUMP):
            status='entry_block_terminal';break
    if end>begin:
        db.execute('INSERT INTO entry_blocks VALUES(?,?,?,?)',(begin,end,status,count))
        db.executemany('INSERT INTO code_refs VALUES(?,?,?,?,?)',refs)
db.commit()
total=db.execute('SELECT count(*) FROM entry_blocks').fetchone()[0]
summary={'entry_blocks':total,'added_this_run':total-len(done),'candidate_pointers_this_run':len(candidates),'included_core_callees':args.core_callees,'status':dict(db.execute('SELECT status,count(*) FROM entry_blocks GROUP BY status')),'limitation':'Supplemental straight-line blocks from named pointers and optionally their direct calls; not a census of all leaf functions and not full logical function bounds.'}
(RESEARCH/'index/entry-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2));pe.close();db.close()
