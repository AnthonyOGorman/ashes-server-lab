"""Preserve hash-bound movement constructor, virtual slots and focused native evidence.

Static candidates only: slot ownership requires the accessor/callback/constructor chain.
Memory displacement hits are search leads, not type or behavior proof.
"""
import hashlib,json,sqlite3,struct,sys
import argparse
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'vendor'))
import capstone,pefile
from capstone.x86 import X86_OP_MEM,X86_REG_RIP
db=sqlite3.connect(R/'index/client-index.sqlite',timeout=60)
meta=json.loads(db.execute("SELECT value FROM metadata WHERE key='native'").fetchone()[0])
raw=Path(meta['path']).read_bytes()
assert hashlib.sha256(raw).hexdigest()==meta['sha256'],'Executable changed'
pe=pefile.PE(data=raw,fast_load=True);base=pe.OPTIONAL_HEADER.ImageBase
cs=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);cs.detail=True
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--extended',action='store_true');args=parser.parse_args()
def ins(rva,size):return list(cs.disasm(pe.get_data(rva,size),rva))
def save_fragment(rva,size,name):
    data=pe.get_data(rva,size);lines=[f'{i.address:08x} {i.bytes.hex():24} {i.mnemonic} {i.op_str}' for i in ins(rva,size)]
    out=R/'proofs'/name
    out.with_suffix('.asm').write_text('\n'.join(lines)+'\n')
    out.with_suffix('.bin').write_bytes(data)
    out.with_suffix('.json').write_text(json.dumps(dict(exe_sha256=meta['sha256'],rva=hex(rva),bytes=size,fragment_sha256=hashlib.sha256(data).hexdigest(),boundary='explicit bounded fragment',instructions=lines),indent=2))
    return lines
access=ins(0x58d61d0,0xae)
assert any(i.address==0x58d6237 and i.operands[1].mem.disp+i.address+i.size==0x58d6570 for i in access)
assert pe.get_data(0x58d657e,5)==bytes.fromhex('e92dc35b00')
ctor=ins(0x5e928cd,10)
assert [i.mnemonic for i in ctor]==['lea','mov'] and ctor[1].op_str=='qword ptr [rdi], rax'
table=ctor[0].address+ctor[0].size+ctor[0].operands[1].mem.disp
assert table==0xb110970
slots=[]
offsets={0x1000,0x1004,0x1008,0x100c,0x100d,0x1014,0x1020,0x1024,0x1028,0x102c,0x1030,0x1034,0x1090,0x10d0,0x1150,0x1190,0x11d0,0x1218,0x12c5,0x1350,0x1378}
selected={0x5e928b0,0x3db8e80,0x3dff940,0x3de80b0,0x5ec2d80,0x5ea4700,0x6ad89c0,0x6ad93a0,0x6ad4670,0x6c11030,0x6c10de0,0x6c003d0,0x6b4d470}
if args.extended:selected.update({0x58d65e0,0x5eab3b0,0x6b3cfe0,0x3dcf710,0x63e7a80,0x3de7ce0,0x5ead530,0x3dffa90,0x3dd0800,0x5d7a410,0x3d4f660,0x6b2b540,0x3e12a80,0x3e12f90,0x3e12bd0,0x6b3be90,0x6b3cdd0})
for index in range((0xb111738-table)//8):
    target=struct.unpack('<Q',pe.get_data(table+index*8,8))[0]-base
    sec=pe.get_section_by_rva(target) if target>=0 else None
    if not sec or not sec.Characteristics&0x20000000:break
    bounds=db.execute('SELECT end FROM native_ranges WHERE begin=?',(target,)).fetchone()
    hits=[]
    if bounds and bounds[0]-target<=65536:
        for i in ins(target,bounds[0]-target):
            for op in i.operands:
                if op.type==X86_OP_MEM and op.mem.base!=X86_REG_RIP and op.mem.disp in offsets:
                    hits.append(dict(site=hex(i.address),offset=hex(op.mem.disp),instruction=i.mnemonic+' '+i.op_str))
    if hits or index*8 in (0x568,0xbc0,0xbc8):selected.add(target)
    if args.extended and index*8 in (0x6f8,0x978,0xa08,0xa18,0xb40,0xb50,0xb58,0xb68,0xb70,0xb78,0xba8,0xbb0,0xbb8,0xbe8,0xbf0,0xbf8,0xd08,0xd80):selected.add(target)
    slots.append(dict(slot=hex(index*8),target_rva=hex(target),offset_hits=hits))
for rva in list(selected):
    if rva in (0x3dff940,0x3de80b0):
        selected.update(t for t, in db.execute('SELECT target_rva FROM code_refs WHERE source_begin=? AND kind="direct_call"',(rva,)) if t)
extra_tables=[]
if args.extended:
    for trva,count in [(0xb110928,9),(0xb1108f8,3),(0xb110910,3)]:
        ts=[]
        for idx in range(count):
            t=struct.unpack('<Q',pe.get_data(trva+idx*8,8))[0]-base
            sec=pe.get_section_by_rva(t) if t>=0 else None
            if sec and sec.Characteristics&0x20000000:
                selected.add(t);ts.append(dict(slot=hex(idx*8),target=hex(t)))
        extra_tables.append(dict(table=hex(trva),slots=ts,ownership='candidate; inspect embedded container/member constructor'))
manifest=[];missing=[]
player_dispatch=[]
if args.extended:
    pbounds=db.execute('SELECT end FROM native_ranges WHERE begin=0x6bee450').fetchone()
    pinst=ins(0x6bee450,pbounds[0]-0x6bee450)
    for idx,i in enumerate(pinst[:-1]):
        nxt=pinst[idx+1]
        if i.mnemonic=='lea' and i.op_str.startswith('rax, [rip') and nxt.mnemonic=='mov' and nxt.op_str=='qword ptr [r15], rax':
            ptable=i.address+i.size+i.operands[1].mem.disp
            for slot in (0xcd0,0xcd8,0xce0,0xce8):
                target=struct.unpack('<Q',pe.get_data(ptable+slot,8))[0]-base
                selected.add(target);player_dispatch.append(dict(table=hex(ptable),site=hex(i.address),slot=hex(slot),target=hex(target)))
    save_fragment(0x6bee450,pbounds[0]-0x6bee450,'movement-player-character-constructor-full')
for rva in sorted(selected):
    bounds=db.execute('SELECT end,boundary FROM decompile_queue WHERE begin=?',(rva,)).fetchone()
    if bounds and bounds[0]-rva<=65536:
        manifest.append(f'{hex(rva)}\t{hex(bounds[0])}\tmovement research candidate; {bounds[1]}')
    else:missing.append(hex(rva))
if args.extended:
    manifest.append('0x5eab3b0\t0x5eab42c\tmovement input direction predicate; explicit reviewed multi-block fragment')
    missing.remove('0x5eab3b0')
manifest_name='movement-extended.tsv' if args.extended else 'movement-focused.tsv'
(R/'batches'/manifest_name).write_text('\n'.join(manifest)+'\n')
save_fragment(0x58d61d0,0xae,'movement-class-accessor-confirmed')
save_fragment(0x58d6570,0x14,'movement-callback-exact')
save_fragment(0x5e928b0,0x759,'movement-constructor-full-range')
report=dict(exe_sha256=meta['sha256'],accessor_rva='0x58d61d0',constructor_callback_rva='0x58d6570',constructor_rva='0x5e928b0',primary_table_rva=hex(table),slots=slots,manifest_ranges=len(manifest),missing_bounds=missing,limitations=['Constructor-installed base table; derived overrides remain possible.','Explicit scan bound is the next constructor-installed secondary table 0xb111738, not a proven complete ABI.','Displacement hits can refer to unrelated objects; review is required.','An initial neighboring callback 0x58d6530 and constructor 0x5e91b00 were inspected but rejected as ownership evidence; the accessor references 0x58d6570.'])
report['extra_tables']=extra_tables
report['player_speed_dispatch']=player_dispatch
initial_globals={hex(r):dict(raw=pe.get_data(r,4).hex(),uint32=struct.unpack('<I',pe.get_data(r,4))[0],scope='on-disk initializer; runtime configuration may change') for r in (0xd378c7c,0xd378c80,0xd378c84,0xd26ee6c)}
report['initial_globals']=initial_globals
report['direction_threshold']=struct.unpack('<d',pe.get_data(0x9e08fe0,8))[0]
report['input_positive_threshold']=struct.unpack('<d',pe.get_data(0x9e08fd8,8))[0]
report['backwards_threshold']=struct.unpack('<d',pe.get_data(0x9e09278,8))[0]
report['extra_network_slots']=[s for s in slots if int(s['slot'],16) in (0xb40,0xb48,0xb50,0xb58,0xb60,0xb68,0xb70,0xb78,0xba8,0xbb0,0xbb8,0xbe8,0xbf8,0xd80)]
report['constructor_literal_floats']={hex(v):struct.unpack('<f',struct.pack('<I',v))[0] for v in (0x43340000,0x435c0000,0x44898000,0x443b8000,0x42340000,0x3c23d70a,0x3e99999a,0x3e19999a)}
if args.extended:
    report['instruction_snapshots']={}
    for rva in (0x63e7a80,0x5ece600,0x5ea4b90,0x5ea2150,0x5ea5370,0x5ec10b0,0x5e9e780,0x5ec1b30,0x6c11030,0x5ec20b0,0x6b2b540,0x3de4f70):
        frags=db.execute('SELECT u.begin,r.end FROM native_unwind u JOIN native_ranges r ON r.begin=u.begin WHERE u.root_begin=? ORDER BY u.begin',(rva,)).fetchall()
        if not frags:
            frags=db.execute('SELECT begin,end FROM native_ranges WHERE begin=?',(rva,)).fetchall()
        records=[]
        for b,e in frags:
            name=f'movement-evidence-{rva:x}-{b:x}'
            save_fragment(b,e-b,name);records.append(dict(begin=hex(b),end=hex(e),file='proofs/'+name+'.json'))
        report['instruction_snapshots'][hex(rva)]=records
(R/'proofs/movement-native-map.json').write_text(json.dumps(report,indent=2))
print(json.dumps(dict(table=hex(table),slots=len(slots),ranges=len(manifest),missing=missing,selected_slots=[dict(slot=s['slot'],target=s['target_rva'],hits=len(s['offset_hits'])) for s in slots if s['offset_hits'] or s['slot'] in ('0x568','0xbc0','0xbc8')]),indent=2))
pe.close();db.close()
