"""Import asset inventory and hash-matching historical native reflection."""
import json
import sqlite3
from pathlib import Path
RESEARCH=Path(__file__).resolve().parents[1];ROOT=RESEARCH.parent
db=sqlite3.connect(RESEARCH/'index/client-index.sqlite')
db.executescript('''
CREATE TABLE IF NOT EXISTS assets(package TEXT,name TEXT,cls TEXT,path TEXT,chunks TEXT,tags TEXT);
CREATE INDEX IF NOT EXISTS assets_class ON assets(cls);
CREATE INDEX IF NOT EXISTS assets_package ON assets(package);
CREATE TABLE IF NOT EXISTS archive_files(path TEXT PRIMARY KEY,size INTEGER);
CREATE TABLE IF NOT EXISTS runtime_native_labels(rva INTEGER,class_name TEXT,function_name TEXT,source TEXT,captured_at TEXT,status TEXT);
DELETE FROM assets; DELETE FROM archive_files; DELETE FROM runtime_native_labels;
''')
for name,table in [('assets.jsonl','assets'),('archive-files.jsonl','archive_files')]:
    with (RESEARCH/'index'/name).open(encoding='utf-8-sig') as f:
        rows=[]
        for line in f:
            item=json.loads(line)
            if table=='assets':
                rows.append((item['package'],item['name'],item['cls'],item['path'],json.dumps(item['chunks']),json.dumps(item['tags'])))
            else:rows.append((item['path'],item['size']))
            if len(rows)==5000:
                db.executemany('INSERT INTO '+table+' VALUES('+','.join('?' for _ in rows[0])+')',rows);rows.clear()
        if rows:db.executemany('INSERT INTO '+table+' VALUES('+','.join('?' for _ in rows[0])+')',rows)
exe_hash=json.loads(db.execute("SELECT value FROM metadata WHERE key='native'").fetchone()[0])['sha256']
for path in sorted((ROOT/'evidence').glob('runtime_reflection_*.json')):
    document=json.loads(path.read_text(encoding='utf-8'))
    if document.get('sha256')!=exe_hash or not document.get('module_base'):continue
    base=int(str(document['module_base']),0)
    for cls in document.get('classes',[]):
        for f in cls.get('net_functions',[]):
            value=f.get('exec_address')
            if not value:continue
            rva=int(value,0)-base
            db.execute('INSERT INTO runtime_native_labels VALUES(?,?,?,?,?,?)',(rva,cls['name'],f['name'],str(path),document.get('time'),'historical_hash_matched_reflection'))
db.commit()
summary={name:db.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in ['assets','archive_files','runtime_native_labels']}
summary['unique_runtime_native_addresses']=db.execute('SELECT count(DISTINCT rva) FROM runtime_native_labels').fetchone()[0]
summary['matched_registration_labels']=db.execute('SELECT count(DISTINCT r.rva || ":" || r.class_name || ":" || r.function_name) FROM runtime_native_labels r JOIN native_labels n ON n.rva=r.rva WHERE n.kind="native_registration_candidate" AND n.name LIKE "%" || r.class_name || "." || r.function_name').fetchone()[0]
(RESEARCH/'index/import-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2));db.close()
