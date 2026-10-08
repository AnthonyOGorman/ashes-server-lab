"""Recover x64 exception-fragment parent chains without guessing logical functions."""
import hashlib,json,sqlite3,struct
from collections import Counter
from pathlib import Path
import pefile
RESEARCH=Path(__file__).resolve().parents[1]
db=sqlite3.connect(RESEARCH/'index/client-index.sqlite',timeout=60)
native=json.loads(db.execute("SELECT value FROM metadata WHERE key='native'").fetchone()[0])
with open(native['path'],'rb') as file:
    if hashlib.sha256(file.read()).hexdigest()!=native['sha256']:raise SystemExit('Input executable hash changed.')
pe=pefile.PE(native['path'],fast_load=True)
ranges=db.execute('SELECT begin,end,unwind FROM native_ranges').fetchall();directory=set(ranges)
headers={}
def header(rva):
    if rva in headers:return headers[rva]
    raw=pe.get_data(rva,4)
    if len(raw)!=4:return {'status':'truncated_header'}
    version=raw[0]&7;flags=raw[0]>>3;codes=raw[2]
    result={'version':version,'flags':flags,'prologue':raw[1],'codes':codes,'status':'header_parsed'}
    tail=rva+4+2*((codes+1)&~1)
    if version not in (1,2):result['status']='version_requires_review'
    elif flags&4:
        data=pe.get_data(tail,12)
        if len(data)!=12:result['status']='truncated_chain'
        else:result['parent']=struct.unpack('<III',data)
    elif flags&3:
        data=pe.get_data(tail,4)
        if len(data)!=4:result['status']='truncated_handler'
        else:result['handler']=struct.unpack('<I',data)[0]
    headers[rva]=result;return result
db.executescript('''
CREATE TABLE IF NOT EXISTS native_unwind(begin INTEGER PRIMARY KEY,unwind INTEGER,version INTEGER,flags INTEGER,prologue INTEGER,codes INTEGER,parent_begin INTEGER,parent_end INTEGER,parent_unwind INTEGER,parent_in_directory INTEGER,handler_rva INTEGER,root_begin INTEGER,depth INTEGER,status TEXT);
CREATE INDEX IF NOT EXISTS unwind_root ON native_unwind(root_begin);
DELETE FROM native_unwind;
''')
counts=Counter();batch=[]
for begin,end,unwind in ranges:
    first=header(unwind);item=(begin,end,unwind);seen=set();depth=0;status=first['status']
    while True:
        if item in seen:status='cycle_requires_review';break
        seen.add(item);current=header(item[2]);parent=current.get('parent')
        if current['status']!='header_parsed':status=current['status'];break
        if not parent:break
        if parent[1]<=parent[0] or not pe.get_section_by_rva(parent[0]):status='parent_requires_review';break
        item=parent;depth+=1
        if depth>128:status='depth_requires_review';break
    parent=first.get('parent');counts[status]+=1
    batch.append((begin,unwind,first.get('version'),first.get('flags'),first.get('prologue'),first.get('codes'),*(parent or (None,None,None)),int(parent in directory) if parent else None,first.get('handler'),item[0] if status=='header_parsed' else None,depth,status))
    if len(batch)>=10000:db.executemany('INSERT INTO native_unwind VALUES('+','.join('?' for _ in range(14))+')',batch);batch.clear()
db.executemany('INSERT INTO native_unwind VALUES('+','.join('?' for _ in range(14))+')',batch);db.commit()
summary={'exception_records':len(ranges),'header_status':dict(counts),'chained_records':db.execute('SELECT count(*) FROM native_unwind WHERE depth>0').fetchone()[0],'distinct_unwind_roots':db.execute('SELECT count(DISTINCT root_begin) FROM native_unwind').fetchone()[0],'max_chain_depth':db.execute('SELECT max(depth) FROM native_unwind').fetchone()[0],'handler_records':db.execute('SELECT count(*) FROM native_unwind WHERE handler_rva IS NOT NULL').fetchone()[0],'limits':['A root groups compiler unwind fragments; it is not a full census of logical functions.','Leaf functions and inlined code remain omitted.','Unwind operations, language-handler scope tables and exception behavior are not decoded here.']}
(RESEARCH/'index/unwind-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary,indent=2));pe.close();db.close()
