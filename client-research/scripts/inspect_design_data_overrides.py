"""Offline discovery of design-data override/loading mechanisms; no process access."""
import json, sqlite3
from pathlib import Path
R=Path(__file__).resolve().parents[1]
d=sqlite3.connect((R/'index/client-index.sqlite').as_uri()+'?mode=ro',uri=True)
rows=[]
for query in ['DesignData*','RecordEdit*','LoadingScreen*','"HideLoadingScreen"','"ShowLoadingScreen"','"Showing loading screen"','"Visible for"']:
    for sid,rva,value in d.execute('SELECT s.id,s.rva,s.value FROM string_search f JOIN strings s ON s.id=f.rowid WHERE string_search MATCH ? LIMIT 5000',(query,)):
        if query in ['DesignData*','RecordEdit*','LoadingScreen*'] and not any(k in value.lower() for k in ['override','patch','reload','cache','config','provider','file','directory','console','hold','force','request']): continue
        refs=[dict(source_begin=hex(b),instruction_rva=hex(i),kind=k,detail=desc) for b,i,k,desc in d.execute('SELECT source_begin,instruction_rva,kind,detail FROM code_refs WHERE target_rva=?',(rva,))]
        rows.append(dict(query=query,string_id=sid,rva=hex(rva),value=value,refs=refs))
out=dict(scope='Indexed strings beginning DesignData, RecordEdit or LoadingScreen; candidate references only',rows=rows,
    limits=['A filtered string search does not prove absence of another override path.', 'Reflected EditCache/provider names do not establish a supported shipping-client override.'])
(R/'proofs/design-data-override-leads.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(rows,indent=2));d.close()
