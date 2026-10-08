"""Record decompiler quality warnings even when Ghidra reports completion."""
import json,re,sqlite3
from collections import Counter
from pathlib import Path
RESEARCH=Path(__file__).resolve().parents[1]
db=sqlite3.connect(RESEARCH/'index/client-index.sqlite',timeout=60)
expected=json.loads(db.execute("SELECT value FROM metadata WHERE key='native'").fetchone()[0])['sha256']
db.executescript('''
CREATE TABLE IF NOT EXISTS decompiler_diagnostics(begin INTEGER,path TEXT,hash_matches INTEGER,reported_failure INTEGER,bad_data_halt INTEGER,control_flow_warning INTEGER,warnings TEXT);
DELETE FROM decompiler_diagnostics;
''')
counts=Counter()
for path in (RESEARCH/'decompiled').glob('**/function_*.c'):
    text=path.read_text(encoding='utf-8',errors='replace');begin=int(path.stem.split('_')[-1],16)
    warnings=re.findall(r'/\* WARNING:.*?\*/',text,re.S)
    failed='Decompilation failed:' in text
    halt=bool(re.search(r'\bhalt_baddata\s*\(',text))
    flow=any(re.search(r'Bad instruction|Truncating control flow|unimplemented|Could not recover jumptable|Unable to resolve',w,re.I) for w in warnings)
    counts['outputs']+=1;counts['explicit_failures']+=failed;counts['bad_data_halt_outputs']+=halt;counts['control_flow_warning_outputs']+=flow;counts['outputs_with_any_warning']+=bool(warnings)
    db.execute('INSERT INTO decompiler_diagnostics VALUES(?,?,?,?,?,?,?)',(begin,str(path),int(expected in text),int(failed),int(halt),int(flow),json.dumps(warnings)))
db.commit()
summary={'counts':dict(counts),'limits':['Completed decompilation can contain truncated or unsupported control flow.','A bad-data halt can reflect a decoding boundary or real trap code and needs instruction-level review.','Warnings about overlapping globals or removed unreachable blocks do not alone prove incorrect behavior.','Every output still requires semantic/type validation.']}
(RESEARCH/'index/decompiler-quality-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary,indent=2));db.close()
