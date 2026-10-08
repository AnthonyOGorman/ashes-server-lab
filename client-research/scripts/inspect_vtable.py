"""Inspect an explicitly located constructor-installed vtable; do not guess class ownership."""
import argparse,csv,hashlib,json,sqlite3,struct
from pathlib import Path
import pefile
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('rva',type=lambda v:int(v,0));p.add_argument('--count',type=int,required=True)
p.add_argument('--owner',required=True);p.add_argument('--constructor',type=lambda v:int(v,0),required=True)
p.add_argument('--output',type=Path,required=True)
args=p.parse_args()
if not 1<=args.count<=1024:p.error('count must be 1..1024')
meta=json.loads((R/'index/summary.json').read_text())['native']
raw=Path(meta['path']).read_bytes()
if hashlib.sha256(raw).hexdigest()!=meta['sha256']:raise ValueError('Executable changed')
pe=pefile.PE(data=raw,fast_load=True);base=pe.OPTIONAL_HEADER.ImageBase
section=pe.get_section_by_rva(args.rva)
if section is None or section.Characteristics&0x20000000:raise ValueError('Table must be in non-code section')
db=sqlite3.connect(R/'index/client-index.sqlite',timeout=60)
db.execute('CREATE TABLE IF NOT EXISTS native_virtual_slots(owner TEXT,table_rva INTEGER,slot INTEGER,target_rva INTEGER,constructor_rva INTEGER,status TEXT,PRIMARY KEY(owner,table_rva,slot))')
rows=[]
for idx in range(args.count):
    slot=idx*8;ptr=struct.unpack('<Q',pe.get_data(args.rva+slot,8))[0];target=ptr-base
    target_section=pe.get_section_by_rva(target) if target>=0 else None
    status='executable_pointer' if target_section and target_section.Characteristics&0x20000000 else 'non_code_pointer'
    row={'slot':hex(slot),'entry_rva':hex(args.rva+slot),'target_rva':hex(target),'status':status}
    row['labels']=[dict(name=n,kind=k) for n,k in db.execute('SELECT name,kind FROM native_labels WHERE rva=?',(target,))]
    rows.append(row)
    db.execute('INSERT OR REPLACE INTO native_virtual_slots VALUES(?,?,?,?,?,?)',(args.owner,args.rva,slot,target,args.constructor,status))
db.commit();db.close();pe.close()
report={'exe_sha256':meta['sha256'],'owner_candidate':args.owner,'constructor_rva':hex(args.constructor),'table_rva':hex(args.rva),'slots':rows,'limits':['Ownership depends on the separately preserved registration/callback/constructor chain.','This records the table installed by the inspected constructor. Derived classes and later vptr changes can override dispatch.','The requested slot count is an explicit bounded table inspection, not an automatically recovered complete class ABI.','Slot identity requires an independent thunk/caller check; pointer readability alone is insufficient.']}
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.with_suffix('.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
with args.output.with_suffix('.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=['slot','entry_rva','target_rva','status']);w.writeheader();w.writerows({k:v for k,v in row.items() if k!='labels'} for row in rows)
print(json.dumps({'table_rva':report['table_rva'],'slots':len(rows),'non_code_slots':sum(r['status']!='executable_pointer' for r in rows),'cooldown_slots':[r for r in rows if r['slot'] in ('0x648','0x658','0x668')]},indent=2))
