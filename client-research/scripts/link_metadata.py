"""Link static evidence without inventing class names or native implementations."""
import json
import re
import sqlite3
import struct
import hashlib
from collections import defaultdict
from pathlib import Path
import pefile

RESEARCH=Path(__file__).resolve().parents[1]
db=sqlite3.connect(RESEARCH/'index/client-index.sqlite')
native=json.loads(db.execute("SELECT value FROM metadata WHERE key='native'").fetchone()[0])
with open(native['path'],'rb') as source:
    if hashlib.sha256(source.read()).hexdigest()!=native['sha256']:raise SystemExit('Executable hash changed; refusing mixed-build metadata links.')
pe=pefile.PE(native['path'],fast_load=True)
base=pe.OPTIONAL_HEADER.ImageBase
code_sections=[(s.VirtualAddress,s.VirtualAddress+s.Misc_VirtualSize) for s in pe.sections if s.Characteristics&0x20000000]
native_methods=defaultdict(set)
for owner,name in db.execute("SELECT owner,name FROM sdk_functions WHERE flags LIKE '%Native%'"):
    native_methods[name].add(owner)
string_addresses={rva:value for rva,value in db.execute('SELECT rva,value FROM strings WHERE encoding="ascii"') if value in native_methods}
# The broad string scan starts at six characters. Recover shorter reflected names
# independently so they do not split otherwise contiguous registration tables.
short_names={name for name in native_methods if len(name)<6}
short_pattern=re.compile(rb'(?<=\x00)[A-Za-z_][A-Za-z0-9_]{0,4}(?=\x00)')
for section in pe.sections:
    if section.Characteristics&0x20000000 or not section.Characteristics&0x40000000:continue
    raw=section.get_data()
    for match in short_pattern.finditer(raw):
        value=match.group().decode('ascii')
        if value in short_names:string_addresses[section.VirtualAddress+match.start()]=value
db.executescript('''
DROP TABLE IF EXISTS native_registration_pairs;
CREATE TABLE native_registration_pairs(table_rva INTEGER PRIMARY KEY,name TEXT,target_rva INTEGER,group_rva INTEGER,inferred_owner TEXT,owner_candidates TEXT,orientation TEXT,evidence TEXT);
CREATE TABLE IF NOT EXISTS source_path_refs(source_begin INTEGER,instruction_rva INTEGER,string_rva INTEGER,path TEXT);
CREATE INDEX IF NOT EXISTS source_refs_begin ON source_path_refs(source_begin);
CREATE TABLE IF NOT EXISTS native_labels(rva INTEGER,name TEXT,kind TEXT,evidence TEXT);
CREATE INDEX IF NOT EXISTS native_label_name ON native_labels(name,kind);
CREATE INDEX IF NOT EXISTS native_label_rva ON native_labels(rva);
DELETE FROM native_registration_pairs;
DELETE FROM source_path_refs;
DELETE FROM native_labels;
''')
def accessor_name(target):
    # Generated UFunction constructor/accessor: ConstructUFunction(&cache,&params).
    # FFunctionParams has NameUTF8 at +16 in this build. Validate the string itself.
    for (params,) in db.execute('SELECT target_rva FROM code_refs WHERE source_begin=? AND kind="rip_relative" AND detail LIKE "lea rdx,%"',(target,)):
        raw=pe.get_data(params+16,8)
        if len(raw)==8:
            actual=string_addresses.get(struct.unpack('<Q',raw)[0]-base)
            if actual:
                return actual
    return None

pairs=[]
for section in pe.sections:
    if section.Characteristics&0x20000000 or not section.Characteristics&0x40000000:
        continue
    raw=section.get_data()
    for at in range(0,len(raw)-15,8):
        first,second=struct.unpack_from('<QQ',raw,at)
        for name_ptr,code_ptr,orientation in [(first,second,'name_code'),(second,first,'code_name')]:
            name=string_addresses.get(name_ptr-base)
            code=code_ptr-base
            if not name or not any(lo<=code<hi for lo,hi in code_sections):
                continue
            actual=accessor_name(code)
            if orientation=='code_name' and actual==name:
                pairs.append((section.VirtualAddress+at,name,code,'function_metadata_accessor'))
            elif orientation=='name_code' and actual is None:
                pairs.append((section.VirtualAddress+at,name,code,'native_registration_candidate'))
pairs.sort()
groups=[]
for pair in pairs:
    if not groups or pair[0]!=groups[-1][-1][0]+16 or pair[3]!=groups[-1][-1][3]:
        groups.append([])
    groups[-1].append(pair)
inferred=0
for group in groups:
    owners=set.intersection(*(native_methods[name] for _,name,_,_ in group))
    inferred_owner=next(iter(owners)) if len(owners)==1 and len(group)>=2 else None
    for table_rva,name,target,orientation in group:
        db.execute('INSERT INTO native_registration_pairs VALUES(?,?,?,?,?,?,?,?)',(table_rva,name,target,group[0][0],inferred_owner,json.dumps(sorted(owners)),orientation, 'Accessor name checked against referenced FFunctionParams.NameUTF8 at +16; name/code native registration candidates exclude these accessors. Owner inferred only for multi-entry groups uniquely matching SDK native method sets.'))
        if inferred_owner:
            inferred+=1
            db.execute('INSERT INTO native_labels VALUES(?,?,?,?)',(target,inferred_owner+'.'+name,orientation,f'pointer-pair table RVA {hex(table_rva)}; owner inferred from SDK; not validated by runtime reflection'))
for rva,name in db.execute('SELECT rva,name FROM exports WHERE name IS NOT NULL').fetchall():
    db.execute('INSERT INTO native_labels VALUES(?,?,?,?)',(rva,name,'pe_export','PE export directory'))
path_pattern=re.compile(r'(?:[A-Za-z]:\\|/)(?:[^\r\n]{0,400}[/\\])[^/\\\r\n]+\.(?:cpp|h|hpp|inl|c)$',re.I)
paths=[(rva,value) for rva,value in db.execute('SELECT rva,value FROM strings') if path_pattern.fullmatch(value)]
for rva,path in paths:
    db.execute('INSERT INTO source_path_refs SELECT source_begin,instruction_rva,?,? FROM code_refs WHERE kind="rip_relative" AND target_rva=?',(rva,path,rva))
db.commit()
summary={'pointer_pairs':len(pairs),'contiguous_groups':len(groups),'inferred_owner_pairs':inferred,'source_path_strings':len(paths),'source_path_refs':db.execute('SELECT count(*) FROM source_path_refs').fetchone()[0],'source_attributed_ranges':db.execute('SELECT count(DISTINCT source_begin) FROM source_path_refs').fetchone()[0],'limitations':['Source path references attribute diagnostic code to a file, not necessarily the definition of the enclosing function.','Unreal pointer pairs and uniquely intersecting SDK method sets yield candidate native thunk labels, not proof of original C++ function identity.','Singleton or ambiguous groups intentionally have no inferred owner.']}
(RESEARCH/'index/link-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2))
pe.close();db.close()
