"""Index explicit serialized default-object values with consumption and failure evidence."""
import json,re,sqlite3
from collections import Counter
from pathlib import Path
R=Path(__file__).resolve().parents[1]
db=sqlite3.connect(R/'index/client-index.sqlite',timeout=60)
db.executescript('CREATE TABLE IF NOT EXISTS blueprint_default_candidates(package TEXT,name TEXT,cls TEXT,status TEXT,schema_hash TEXT,expected_bytes INTEGER,consumed_bytes INTEGER,body TEXT); CREATE TABLE IF NOT EXISTS blueprint_default_properties(package TEXT,cls TEXT,name TEXT,value TEXT); DELETE FROM blueprint_default_candidates; DELETE FROM blueprint_default_properties;')
counts,consumption,failures=Counter(),Counter(),Counter();nvalues=0
for line in (R/'index/blueprint-defaults-v2.jsonl').open(encoding='utf-8-sig'):
    row=json.loads(line);status=row['status'];body=row.get('class_json',row.get('error'))
    expected,consumed=row.get('expectedSerialBytes'),row.get('consumedSerialBytes')
    if status=='inferred_schema_default_candidate':
        state='exact_consumption' if expected==consumed and expected is not None else 'under_consumed' if expected is not None and consumed is not None and consumed<expected else 'over_consumed_or_unmeasured'
        consumption[state]+=1
        if state!='exact_consumption':status='default_requires_consumption_review'
        doc=json.loads(body)
        if doc.get('Name')!=row['name']:raise ValueError('Default-object name mismatch')
        for name,value in doc.get('Properties',{}).items():
            db.execute('INSERT INTO blueprint_default_properties VALUES(?,?,?,?)',(row['package'],row['cls'],name,json.dumps(value)));nvalues+=1
    else:
        matches=re.findall(r'([^\r\n]+: Unknown property with value \d+[^\r\n]*|[^\r\n]+: Missing schema[^\r\n]*)',body or '')
        failures[matches[-1].strip() if matches else (body or '').splitlines()[0] if body else 'unspecified']+=1
    counts[status]+=1
    db.execute('INSERT INTO blueprint_default_candidates VALUES(?,?,?,?,?,?,?,?)',(row['package'],row.get('name'),row.get('cls'),status,row.get('schemaHash'),expected,consumed,body))
db.commit();db.close()
warnings=Counter()
for path in (R/'logs').glob('blueprint-defaults-v2-*.log'):
    for line in path.open(encoding='utf-8-sig',errors='replace'):
        if 'Unknown property with value' in line and "it's zero" in line:warnings['unmapped_zero_property_warning_lines']+=1
summary={'source':'blueprint-defaults-v2.jsonl','confidence':'inferred_schema_default_candidate','status':dict(counts),'consumption':dict(consumption),'serialized_property_entries':nvalues,'warning_counts':dict(warnings),'failure_groups':dict(failures),'limits':['Only selected Blueprint-package class default objects were attempted.','Values are serialized overrides; omitted/inherited/default-zero values require separate resolution.','Schemas are inferred from saved SDK declarations; semantic correctness remains unverified.','The parser can skip unknown zero-valued fields. Fatal exception mode does not eliminate these warnings. Warning lines can repeat during visible-cursor replay.','Failed and under-consumed objects remain explicit gaps.','Component-instance exports and referenced assets are not established as parsed by a successful class/default parse.']}
(R/'index/default-candidate-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k!='failure_groups'},indent=2))
