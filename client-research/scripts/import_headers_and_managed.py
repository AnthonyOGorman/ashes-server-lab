"""Import Blueprint/package export tables and managed method definitions."""
import json
import sqlite3
from collections import Counter
from pathlib import Path
RESEARCH=Path(__file__).resolve().parents[1]
db=sqlite3.connect(RESEARCH/'index/client-index.sqlite')
db.executescript('''
CREATE TABLE IF NOT EXISTS package_headers(package TEXT PRIMARY KEY,status TEXT,export_count INTEGER,name_count INTEGER,scope TEXT);
CREATE TABLE IF NOT EXISTS package_exports(package TEXT,export_index INTEGER,name TEXT,cls TEXT,size INTEGER,serial_offset INTEGER,flags TEXT);
CREATE INDEX IF NOT EXISTS package_exports_class ON package_exports(cls);
CREATE TABLE IF NOT EXISTS package_names(package TEXT,name TEXT);
CREATE TABLE IF NOT EXISTS managed_methods(assembly TEXT,token TEXT,rva TEXT,name TEXT,attributes TEXT,impl_attributes TEXT,source TEXT);
DELETE FROM package_headers; DELETE FROM package_exports; DELETE FROM package_names; DELETE FROM managed_methods;
''')
for line in (RESEARCH/'index/package-headers-v2.jsonl').open(encoding='utf-8-sig'):
    item=json.loads(line);package=item['package'];exports=item.get('exports',[]);names=item.get('names',[])
    db.execute('INSERT INTO package_headers VALUES(?,?,?,?,?)',(package,item['status'],len(exports),len(names),item.get('scope',item.get('error'))))
    db.executemany('INSERT INTO package_exports VALUES(?,?,?,?,?,?,?)',[(package,e['index'],e['name'],e.get('cls'),e['size'],e['offset'],e['flags']) for e in exports])
    db.executemany('INSERT INTO package_names VALUES(?,?)',[(package,n) for n in names])
for path in sorted((RESEARCH/'index').glob('managed-*-methods.json')):
    item=json.loads(path.read_text(encoding='utf-8-sig'))
    db.executemany('INSERT INTO managed_methods VALUES(?,?,?,?,?,?,?)',[(item['assembly'],r['Token'],r['RVA'],r['Name'],r['Attributes'],r['ImplAttributes'],str(path)) for r in item['rows']])
db.commit()
summary={t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['package_headers','package_exports','package_names','managed_methods']}
summary['package_status']=dict(db.execute('SELECT status,count(*) FROM package_headers GROUP BY status'))
summary['blueprint_function_exports']=db.execute('SELECT count(*) FROM package_exports WHERE cls="Function"').fetchone()[0]
summary['managed_assemblies']=db.execute('SELECT count(DISTINCT assembly) FROM managed_methods').fetchone()[0]
(RESEARCH/'index/header-managed-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2));db.close()
