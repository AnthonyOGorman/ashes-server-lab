"""Search indexed native loading strings/references, without a live client scan."""
import json,sqlite3
from pathlib import Path
R=Path(__file__).resolve().parents[1]
d=sqlite3.connect((R/'index/client-index.sqlite').as_uri()+'?mode=ro',uri=True)
tables=d.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND (name LIKE '%string%' OR name LIKE '%ref%')").fetchall()
rows=[]
for query in ['"Holding loading screen"','"HoldLoadingScreenAdditionalSecs"','LoadingScreen*']:
    for sid,rva,value in d.execute('SELECT s.id,s.rva,s.value FROM string_search f JOIN strings s ON s.id=f.rowid WHERE string_search MATCH ? LIMIT 2000',(query,)):
        if query=='LoadingScreen*' and not any(term in value.lower() for term in ['hold','override','skip','force','seconds']):continue
        refs=[dict(source_begin=hex(b),instruction_rva=hex(i),kind=k,detail=desc) for b,i,k,desc in d.execute('SELECT source_begin,instruction_rva,kind,detail FROM code_refs WHERE target_rva=?',(rva,))]
        rows.append(dict(query=query,string_id=sid,rva=hex(rva),value=value,refs=refs))
(R/'proofs/loading-screen-string-leads.json').write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps(rows,indent=2));d.close()
