"""Repair aligned SDK declarations in-place without rebuilding derived indexes."""
import hashlib,json,re,sqlite3
from datetime import datetime,timezone
from pathlib import Path
R=Path(__file__).resolve().parents[1]
db=sqlite3.connect(R/'index/client-index.sqlite',timeout=60)
cache={};repairs=[]
for full,old_cpp,old_parent,source,line in db.execute('SELECT full_name,cpp_name,parent,source,line FROM sdk_types').fetchall():
    if source not in cache:
        raw=Path(source).read_bytes()
        expected=db.execute('SELECT sha256 FROM sdk_sources WHERE path=?',(source,)).fetchone()[0]
        if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('SDK source changed: '+source)
        cache[source]=raw.decode('utf-8-sig',errors='replace').splitlines()
    declaration='\n'.join(cache[source][line:line+6])
    match=re.search(r'^(?:class|struct)\s+(?:alignas\([^)]*\)\s+)?(\w+)(?: final)?(?:\s*:\s*public (\w+))?',declaration,re.M)
    if not match:raise ValueError('Unparsed declaration: '+full)
    cpp,parent=match.groups()
    if (cpp,parent)!=(old_cpp,old_parent):
        repairs.append(dict(name=full,old_cpp=old_cpp,cpp=cpp,old_parent=old_parent,parent=parent,source=source,line=line))
        db.execute('UPDATE sdk_types SET cpp_name=?,parent=? WHERE full_name=?',(cpp,parent,full))
db.commit();db.close()
report={'time':datetime.now(timezone.utc).isoformat(),'reason':'Original declaration regex treated alignas as a C++ type name and lost its parent.','repaired':len(repairs),'repairs':repairs}
# A second run gets a fresh checkpoint; preserve the first repair evidence.
out=R/'index/sdk-declaration-repairs.json'
if repairs or not out.exists():out.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='repairs'},indent=2))
