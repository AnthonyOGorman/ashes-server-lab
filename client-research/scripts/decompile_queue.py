"""Create/refresh the full resumable queue and select one bounded Ghidra batch."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
RESEARCH=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--size',type=int,default=256)
args=parser.parse_args()
if not 1<=args.size<=256:parser.error('size must be 1..256')
db=sqlite3.connect(RESEARCH/'index/client-index.sqlite',timeout=60)
db.executescript('''
CREATE TABLE IF NOT EXISTS decompile_queue(begin INTEGER PRIMARY KEY,end INTEGER,label TEXT,priority INTEGER,boundary TEXT,status TEXT,output TEXT);
CREATE INDEX IF NOT EXISTS queue_status ON decompile_queue(status,priority,begin);
''')
pause_file=RESEARCH/'index/decompile-pause.request'
if pause_file.exists():
    print(json.dumps({'batch_ranges':0,'paused':True,'pause_file':str(pause_file),'status':dict(db.execute('SELECT status,count(*) FROM decompile_queue GROUP BY status'))}))
    db.close();raise SystemExit(0)
if db.execute('SELECT count(*) FROM decompile_queue').fetchone()[0]==0:
    ranges={b:(e,'PE_exception_range') for b,e in db.execute('SELECT begin,end FROM native_ranges')}
    ranges.update({b:(e,'bounded_entry_block_only') for b,e in db.execute('SELECT begin,end FROM entry_blocks')})
    labels={};core=set();accessors=set()
    for rva,name,kind in db.execute('SELECT rva,name,kind FROM native_labels'):
        labels.setdefault(rva,[]).append(name+' ['+kind+']')
        if kind=='function_metadata_accessor':accessors.add(rva)
        elif name.startswith(('GameSystemsPlugin.','Intrepid.','IntrepidNet.','IntrepidEOS.')):core.add(rva)
    direct_core={r[0] for r in db.execute('SELECT DISTINCT target_rva FROM code_refs WHERE kind IN ("direct_call","direct_jmp") AND source_begin IN (SELECT rva FROM native_labels WHERE kind="native_registration_candidate" AND name LIKE "GameSystemsPlugin.%")')}
    source_core={r[0] for r in db.execute('SELECT DISTINCT source_begin FROM source_path_refs WHERE path LIKE "%GameSystems%" OR path LIKE "%Intrepid%"')}
    source_any={r[0] for r in db.execute('SELECT DISTINCT source_begin FROM source_path_refs')}
    rows=[]
    for begin,(end,boundary) in ranges.items():
        priority=0 if begin in core else 1 if begin in direct_core else 2 if begin in source_core else 3 if begin in labels and begin not in accessors else 4 if begin in source_any else 6 if begin in accessors else 5
        label=' | '.join(labels.get(begin,[]))[:1500] or ('core direct callee' if begin in direct_core else 'anonymous native range')
        status='oversize_requires_review' if end-begin>65536 else 'pending'
        rows.append((begin,end,label,priority,boundary,status,None))
        if len(rows)==10000:
            db.executemany('INSERT INTO decompile_queue VALUES(?,?,?,?,?,?,?)',rows);rows.clear()
    db.executemany('INSERT INTO decompile_queue VALUES(?,?,?,?,?,?,?)',rows)
    db.commit()
# New supplemental blocks can be discovered after the initial queue was built.
missing=db.execute('SELECT e.begin,e.end FROM entry_blocks e LEFT JOIN decompile_queue q ON q.begin=e.begin WHERE q.begin IS NULL').fetchall()
if missing:
    for begin,end in missing:
        names=db.execute('SELECT name,kind FROM native_labels WHERE rva=?',(begin,)).fetchall()
        label=' | '.join(name+' ['+kind+']' for name,kind in names)[:1500] or 'core direct callee entry block'
        is_core=any(kind=='native_registration_candidate' and name.startswith(('GameSystemsPlugin.','Intrepid.','IntrepidNet.','IntrepidEOS.')) for name,kind in names)
        priority=0 if is_core else 3 if names else 1
        db.execute('INSERT INTO decompile_queue VALUES(?,?,?,?,?,?,?)',(begin,end,label,priority,'bounded_entry_block_only','pending',None))
    db.commit()
# Labels and inferred owners can improve without discarding completed work.
current_labels={}
for rva,name,kind in db.execute('SELECT rva,name,kind FROM native_labels'):
    current_labels.setdefault(rva,[]).append((name,kind))
for begin,names in current_labels.items():
    core=any(kind=='native_registration_candidate' and name.startswith(('GameSystemsPlugin.','Intrepid.','IntrepidNet.','IntrepidEOS.')) for name,kind in names)
    priority=0 if core else 6 if all(kind=='function_metadata_accessor' for _,kind in names) else 3
    label=' | '.join(name+' ['+kind+']' for name,kind in names)[:1500]
    db.execute('UPDATE decompile_queue SET label=?,priority=? WHERE begin=?',(label,priority,begin))
db.execute('''UPDATE decompile_queue SET priority=1 WHERE priority>1 AND begin IN (
 SELECT DISTINCT c.target_rva FROM code_refs c JOIN native_labels n ON n.rva=c.source_begin
 WHERE c.kind IN ("direct_call","direct_jmp") AND n.kind="native_registration_candidate"
 AND (n.name LIKE "GameSystemsPlugin.%" OR n.name LIKE "Intrepid.%" OR n.name LIKE "IntrepidNet.%" OR n.name LIKE "IntrepidEOS.%"))''')
db.commit()
expected_hash=json.loads(db.execute("SELECT value FROM metadata WHERE key='native'").fetchone()[0])['sha256']
for path in sorted((RESEARCH/'decompiled').glob('**/function_*.c')):
    begin=int(path.stem.split('_')[-1],16)
    text=path.read_text(encoding='utf-8',errors='replace')
    if expected_hash not in text:continue
    status='decompiler_failed' if 'Decompilation failed:' in text else 'decompiled_unreviewed'
    db.execute('UPDATE decompile_queue SET status=?,output=? WHERE begin=?',(status,str(path),begin))
for path in sorted((RESEARCH/'decompiled').glob('**/error_*.txt')):
    begin=int(path.stem.split('_')[-1],16)
    db.execute('UPDATE decompile_queue SET status="script_error",output=? WHERE begin=?',(str(path),begin))
if db.execute('SELECT 1 FROM sqlite_master WHERE type="table" AND name="native_unwind"').fetchone():
    db.execute('UPDATE decompile_queue SET boundary="PE_chained_exception_fragment" WHERE begin IN (SELECT begin FROM native_unwind WHERE depth>0 AND status="header_parsed")')
    db.execute('UPDATE decompile_queue SET status="chained_fragment_indexed" WHERE status="pending" AND boundary="PE_chained_exception_fragment"')
    db.execute('UPDATE decompile_queue SET status="decompiled_fragment_unreviewed" WHERE status="decompiled_unreviewed" AND boundary="PE_chained_exception_fragment"')
if db.execute('SELECT 1 FROM sqlite_master WHERE type="table" AND name="review_seeds"').fetchone():
    db.execute('UPDATE decompile_queue SET priority=-1 WHERE begin IN (SELECT begin FROM review_seeds) AND status="pending"')
db.commit()
selected=db.execute('SELECT begin,end,label,boundary FROM decompile_queue WHERE status="pending" ORDER BY priority,begin LIMIT ?',(args.size,)).fetchall()
batch=RESEARCH/'batches';batch.mkdir(exist_ok=True)
manifest=batch/'next.tsv'
manifest.write_text('\n'.join(f'{hex(b)}\t{hex(e)}\t{label}; {boundary}' for b,e,label,boundary in selected)+'\n',encoding='utf-8')
summary={'total':db.execute('SELECT count(*) FROM decompile_queue').fetchone()[0],'status':dict(db.execute('SELECT status,count(*) FROM decompile_queue GROUP BY status')),'pending_by_priority':dict(db.execute('SELECT priority,count(*) FROM decompile_queue WHERE status="pending" GROUP BY priority')),'batch_ranges':len(selected),'manifest':str(manifest),'limitation':'A successful decompiler result remains unreviewed; pseudocode and candidate names are not established behavior.'}
(RESEARCH/'index/decompile-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2));db.close()
