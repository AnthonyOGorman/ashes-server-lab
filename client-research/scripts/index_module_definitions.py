"""Inventory every installed managed MethodDef and native export/exception range.

Reads metadata and bytes only. Managed assemblies are never loaded or executed.
"""
import argparse,hashlib,json,sqlite3,subprocess,sys
from collections import Counter
from pathlib import Path
import pefile
RESEARCH=Path(__file__).resolve().parents[1]
CLIENT=Path(r'E:\Games\Steam Library\steamapps\common\Ashes of Creation')
DOTNET=Path(r'E:\Ashes Of Creation GPT\CPP\vendor\terrain\dotnet-sdk10\dotnet.exe')
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--reuse-managed-output',action='store_true')
args=parser.parse_args()
db=sqlite3.connect(RESEARCH/'index/client-index.sqlite',timeout=60)
modules=db.execute('SELECT path,kind,sha256 FROM modules ORDER BY path').fetchall()
manifest=RESEARCH/'batches/managed-modules.tsv'
output=RESEARCH/'index/all-managed-methods.jsonl'
manifest.write_text('\n'.join(f'{CLIENT/path}\t{sha}' for path,kind,sha in modules if kind=='managed')+'\n',encoding='utf-8')
if not args.reuse_managed_output:
    subprocess.run([str(DOTNET),str(RESEARCH/'scripts/metadata-reader/bin/Release/net10.0/MetadataReader.dll'),str(manifest),str(output)],check=True)
db.executescript('''
CREATE TABLE IF NOT EXISTS all_managed_methods(path TEXT,sha256 TEXT,owner TEXT,name TEXT,token INTEGER,rva INTEGER,attributes TEXT,implementation TEXT,signature TEXT,il_bytes INTEGER,max_stack INTEGER,exception_regions INTEGER,il_hash TEXT,body_error TEXT,import_module TEXT,import_name TEXT);
CREATE TABLE IF NOT EXISTS all_managed_modules(path TEXT PRIMARY KEY,status TEXT,types INTEGER,methods INTEGER,bodies INTEGER,error TEXT);
CREATE TABLE IF NOT EXISTS module_native_ranges(path TEXT,begin INTEGER,end INTEGER,unwind INTEGER,status TEXT);
CREATE TABLE IF NOT EXISTS module_native_exports(path TEXT,name TEXT,ordinal INTEGER,rva INTEGER,forwarder TEXT);
CREATE INDEX IF NOT EXISTS all_managed_names ON all_managed_methods(owner,name);
DELETE FROM all_managed_methods; DELETE FROM all_managed_modules; DELETE FROM module_native_ranges; DELETE FROM module_native_exports;
''')
for line in output.open(encoding='utf-8-sig'):
    row=json.loads(line);path=str(Path(row['path']).relative_to(CLIENT))
    if row['kind']=='method':
        keys=['sha256','owner','name','token','rva','attributes','implementation','signature','ilBytes','maxStack','exceptionRegions','ilHash','bodyError','importModule','importName']
        db.execute('INSERT INTO all_managed_methods VALUES('+','.join('?' for _ in range(16))+')',[path]+[row.get(k) for k in keys])
    else:db.execute('INSERT INTO all_managed_modules VALUES(?,?,?,?,?,?)',(path,row['status'],row.get('types'),row.get('methods'),row.get('bodies'),row.get('error')))
native_status=Counter()
for relative,kind,expected in modules:
    if kind!='native':continue
    path=CLIENT/relative
    with path.open('rb') as file:
        if hashlib.sha256(file.read()).hexdigest()!=expected:raise SystemExit(f'Input hash changed: {relative}')
    pe=pefile.PE(str(path),fast_load=True);pe.parse_data_directories(directories=[0,3])
    for entry in getattr(getattr(pe,'DIRECTORY_ENTRY_EXPORT',None),'symbols',[]):
        db.execute('INSERT INTO module_native_exports VALUES(?,?,?,?,?)',(relative,entry.name.decode(errors='replace') if entry.name else None,entry.ordinal,entry.address,entry.forwarder.decode(errors='replace') if entry.forwarder else None))
    if pe.FILE_HEADER.Machine==0x8664:
        for entry in getattr(pe,'DIRECTORY_ENTRY_EXCEPTION',[]):
            record=entry.struct;begin,end=record.BeginAddress,record.EndAddress
            section=pe.get_section_by_rva(begin)
            status='executable_range' if end>begin and section and section.Characteristics&0x20000000 and end<=section.VirtualAddress+section.Misc_VirtualSize else 'requires_review'
            db.execute('INSERT INTO module_native_ranges VALUES(?,?,?,?,?)',(relative,begin,end,record.UnwindData,status));native_status[status]+=1
    else:native_status['non_amd64_range_parse_not_supported']+=1
    pe.close()
db.commit()
summary={
 'managed_modules':db.execute('SELECT count(*) FROM all_managed_modules').fetchone()[0],
 'managed_module_status':dict(db.execute('SELECT status,count(*) FROM all_managed_modules GROUP BY status')),
 'managed_methods':db.execute('SELECT count(*) FROM all_managed_methods').fetchone()[0],
 'managed_il_bodies':db.execute('SELECT count(*) FROM all_managed_methods WHERE il_bytes IS NOT NULL').fetchone()[0],
 'managed_body_errors':db.execute('SELECT count(*) FROM all_managed_methods WHERE body_error IS NOT NULL').fetchone()[0],
 'native_exports':db.execute('SELECT count(*) FROM module_native_exports').fetchone()[0],
 'native_exception_records':db.execute('SELECT count(*) FROM module_native_ranges').fetchone()[0],
 'native_range_status':dict(native_status),
 'limits':['Method definitions and IL fingerprints are not reconstructed C# or semantic review.','Assembly copies retain separate installed paths.','Exception ranges may be fragments and omit leaf or inlined functions.','The installed EOS module is a local replacement.']}
(RESEARCH/'index/module-definitions-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2));db.close()
