"""Record the reviewed constructor/thunk/vtable chain for this exact executable."""
import hashlib,json,sqlite3,struct,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'vendor'))
import capstone,pefile
from capstone.x86 import X86_OP_MEM
db=sqlite3.connect(R/'index/client-index.sqlite',timeout=60)
meta=json.loads(db.execute("SELECT value FROM metadata WHERE key='native'").fetchone()[0])
raw=Path(meta['path']).read_bytes()
if hashlib.sha256(raw).hexdigest()!=meta['sha256']:raise ValueError('Executable changed')
pe=pefile.PE(data=raw,fast_load=True)
decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);decoder.detail=True
def instructions(rva,size):return list(decoder.disasm(pe.get_data(rva,size),rva))
ctor=instructions(0x6b8cd1d,10)
assert [(i.mnemonic,i.op_str) for i in ctor]==[('lea','rax, [rip + 0x4afa6ac]'),('mov','qword ptr [rdi], rax')]
table=ctor[0].address+ctor[0].size+ctor[0].operands[1].mem.disp
assert table==0xb6873d0
assert pe.get_data(0x5cd0500,13)==bytes.fromhex('488b094885c90f85f4c7eb00c3')
links=[]
db.execute('CREATE TABLE IF NOT EXISTS native_dispatch_links(owner TEXT,method TEXT,thunk_rva INTEGER,slot INTEGER,table_rva INTEGER,target_rva INTEGER,constructor_rva INTEGER,evidence TEXT,PRIMARY KEY(owner,method))')
owner='GameSystemsPlugin.AoCAbilityComponent'
for name,thunk,slot,target in [('GetRemainingAbilityCooldown',0x5cd4b00,0x648,0x6ba73d0),('GetRemainingAbilityCooldownPercent',0x5cd4c30,0x658,0x6ba7540),('IsAbilityOnCooldown',0x5cd5300,0x668,0x6bb40c0)]:
    registered=db.execute('SELECT rva FROM native_labels WHERE name=? AND kind="native_registration_candidate"',(owner+'.'+name,)).fetchone()
    assert registered and registered[0]==thunk
    end=db.execute('SELECT end FROM native_ranges WHERE begin=?',(thunk,)).fetchone()[0]
    sites=[hex(i.address) for i in instructions(thunk,end-thunk) if any(op.type==X86_OP_MEM and op.mem.disp==slot for op in i.operands)]
    assert sites,'Thunk does not reference expected slot'
    actual=struct.unpack('<Q',pe.get_data(table+slot,8))[0]-pe.OPTIONAL_HEADER.ImageBase
    assert actual==target
    evidence=json.dumps({'file':'proofs/ability-component-vtable.json','thunk_slot_sites':sites,'constructor_vptr_site':'0x6b8cd1d','scope':'Constructor-installed table; derived overrides and later vptr changes remain possible'})
    db.execute('INSERT OR REPLACE INTO native_dispatch_links VALUES(?,?,?,?,?,?,?,?)',(owner,name,thunk,slot,table,target,0x6b8cd00,evidence))
    label=owner+'.'+name+'.constructor_vtable_implementation'
    db.execute('DELETE FROM native_labels WHERE name=? AND kind="constructor_vtable_slot_candidate"',(label,))
    db.execute('INSERT INTO native_labels VALUES(?,?,?,?)',(target,label,'constructor_vtable_slot_candidate',evidence))
    links.append(dict(method=name,thunk_rva=hex(thunk),slot=hex(slot),table_rva=hex(table),target_rva=hex(target),slot_sites=sites))
label=owner+'.CooldownRecordMatch.static_helper'
db.execute('DELETE FROM native_labels WHERE name=? AND kind="reviewed_instruction_helper"',(label,))
db.execute('INSERT INTO native_labels VALUES(?,?,?,?)',(0x61e53c0,label,'reviewed_instruction_helper','proofs/cooldown-ability-match.json: compares Guid at +8 or nonzero SharedCooldownTag at +0x340'))
db.commit();db.close()
clamp_pointer=0x6ba76bb+0x3233bd5
report={'exe_sha256':meta['sha256'],'class_accessor_rva':'0x5cce8c0','class_callback_rva':'0x5cd0500','constructor_rva':'0x6b8cd00','constructor_table_rva':hex(table),'registration_callback_rva':'0x5cd2030','links':links,'percent_upper_clamp_constant':struct.unpack('<d',pe.get_data(clamp_pointer,8))[0],'time_helper_fallback_constant':struct.unpack('<d',pe.get_data(0xb85fc10,8))[0],'limits':['Class ownership is linked through inspected static registration references and the constructor callback; no process was run.','The recorded table is the primary table installed by this constructor. Derived classes can override dispatch.','Time-helper clock maintenance and cooldown record update/expiry/prediction paths remain unreviewed.']}
(R/'proofs/cooldown-dispatch.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2));pe.close()
