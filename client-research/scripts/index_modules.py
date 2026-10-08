"""Fingerprint the client's PE modules, import dependencies and debug records."""
import json
import sqlite3
from pathlib import Path
import pefile
RESEARCH=Path(__file__).resolve().parents[1]
CLIENT=Path(r'E:\Games\Steam Library\steamapps\common\Ashes of Creation')
db=sqlite3.connect(RESEARCH/'index/client-index.sqlite')
db.executescript('''
CREATE TABLE IF NOT EXISTS modules(path TEXT PRIMARY KEY,kind TEXT,machine TEXT,entry_rva INTEGER,image_base INTEGER,exception_records INTEGER,export_count INTEGER,sha256 TEXT,status TEXT);
CREATE TABLE IF NOT EXISTS module_dependencies(path TEXT,dll TEXT,kind TEXT,symbol_count INTEGER);
DELETE FROM modules; DELETE FROM module_dependencies;
''')
for relative,sha in db.execute('SELECT path,sha256 FROM files WHERE path LIKE "%.exe" OR path LIKE "%.dll"').fetchall():
    try:
        pe=pefile.PE(str(CLIENT/relative),fast_load=True)
        pe.parse_data_directories(directories=[0,1,13])
        kind='managed' if pe.OPTIONAL_HEADER.DATA_DIRECTORY[14].VirtualAddress else 'native'
        count=pe.OPTIONAL_HEADER.DATA_DIRECTORY[3].Size//12 if pe.FILE_HEADER.Machine==0x8664 else None
        export_count=len(getattr(getattr(pe,'DIRECTORY_ENTRY_EXPORT',None),'symbols',[]))
        db.execute('INSERT INTO modules VALUES(?,?,?,?,?,?,?,?,?)',(relative,kind,hex(pe.FILE_HEADER.Machine),pe.OPTIONAL_HEADER.AddressOfEntryPoint,pe.OPTIONAL_HEADER.ImageBase,count,export_count,sha,'headers_parsed'))
        for depkind,attr in [('regular','DIRECTORY_ENTRY_IMPORT'),('delayed','DIRECTORY_ENTRY_DELAY_IMPORT')]:
            for entry in getattr(pe,attr,[]):
                db.execute('INSERT INTO module_dependencies VALUES(?,?,?,?)',(relative,entry.dll.decode(errors='replace'),depkind,len(entry.imports)))
        pe.close()
    except Exception as e:
        db.execute('INSERT INTO modules VALUES(?,?,?,?,?,?,?,?,?)',(relative,None,None,None,None,None,None,sha,str(e)))
db.commit()
summary={'modules':db.execute('SELECT count(*) FROM modules').fetchone()[0],'kinds':dict(db.execute('SELECT kind,count(*) FROM modules GROUP BY kind')),'dependencies':db.execute('SELECT count(*) FROM module_dependencies').fetchone()[0],'errors':db.execute('SELECT count(*) FROM modules WHERE status!="headers_parsed"').fetchone()[0]}
(RESEARCH/'index/module-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary,indent=2));db.close()
