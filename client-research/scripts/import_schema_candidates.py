"""Keep inferred SDK-schema results separate and check local references against headers."""
import json, re, sqlite3
from collections import Counter
from pathlib import Path
R = Path(__file__).resolve().parents[1]
headers = {}
for line in (R/'index/package-headers-v2.jsonl').open(encoding='utf-8-sig'):
    row = json.loads(line)
    headers[row['package'].casefold()] = row.get('exports', [])
counts, kinds, checks, properties, consumption = Counter(), Counter(), Counter(), Counter(), Counter()
records, fields, functions, values, unresolved = [], [], [], [], []
def check_reference(target, expected=None):
    if not isinstance(target, dict):
        checks['invalid_reference_shape'] += 1
        return
    path = target.get('ObjectPath', '')
    match = re.match(r'^(.*)\.(\d+)$', path)
    if not match or match[1].casefold() not in headers:
        checks['external_or_unindexed_reference'] += 1
        unresolved.append(target)
        return
    exports = headers[match[1].casefold()]
    idx = int(match[2])
    if idx >= len(exports):
        checks['invalid_export_index'] += 1
        return
    export = exports[idx]
    object_name = target.get('ObjectName', '')
    name_match = any(object_name.endswith(prefix+export['name']+"'") for prefix in ("'", '.', ':'))
    if not name_match:
        checks['reference_name_mismatch'] += 1
    elif expected and export.get('cls') != expected:
        checks['reference_class_mismatch'] += 1
    else:
        checks['local_reference_matches_header'] += 1
source='blueprint-class-schema-v3-consumption.jsonl'
for line in (R/'index'/source).open(encoding='utf-8-sig'):
    row = json.loads(line); counts[row['status']] += 1
    kinds[row.get('cls', '<package>')] += 1
    if row['status'] == 'failed' or row['status'] == 'package_failed':
        records.append((row['package'],row.get('name'),row.get('cls'),row['status'],row.get('schemaHash'),None,row.get('error')))
        continue
    doc = json.loads(row['class_json'])
    consumed=row.get('consumedSerialBytes');expected=row.get('expectedSerialBytes')
    consumption['exact_consumption' if consumed==expected and expected is not None else 'unmeasured' if expected is None else 'under_consumed' if consumed<expected else 'over_consumed']+=1
    if doc.get('Name') == row['name'] and doc.get('bCooked') is True and 'ClassWithin' in doc and 'ClassDefaultObject' in doc:
        checks['terminal_class_metadata_present'] += 1
    else:
        checks['terminal_class_metadata_missing'] += 1
    check_reference(doc.get('ClassDefaultObject'))
    for name, target in doc.get('FuncMap', {}).items():
        functions.append((row['package'],row['name'],name,target.get('ObjectName'),target.get('ObjectPath')))
        check_reference(target, 'Function')
        if any(target.get('ObjectName','').endswith(prefix+name+"'") for prefix in ("'", '.', ':')):
            checks['function_map_label_matches_target'] += 1
        else:
            checks['function_map_label_mismatch'] += 1
    for field in doc.get('ChildProperties', []):
        fields.append((row['package'],row['name'],field['Name'],field['Type'],field.get('ElementSize'),field.get('PropertyFlags'),json.dumps(field)))
    for name, value in doc.get('Properties', {}).items():
        properties[name] += 1
        values.append((row['package'],row['name'],name,json.dumps(value)))
    records.append((row['package'],row['name'],row['cls'],row['status'],row.get('schemaHash'),row.get('properties'),row['class_json']))
db = sqlite3.connect(R/'index/client-index.sqlite', timeout=60)
db.execute('CREATE TABLE IF NOT EXISTS blueprint_schema_candidates(package TEXT,name TEXT,cls TEXT,status TEXT,schema_hash TEXT,property_count INTEGER,body TEXT)')
db.execute('DELETE FROM blueprint_schema_candidates')
db.executemany('INSERT INTO blueprint_schema_candidates VALUES(?,?,?,?,?,?,?)',records)
for table, declaration, rows in (
    ('blueprint_schema_fields','package TEXT,cls TEXT,name TEXT,type TEXT,element_size INTEGER,flags TEXT,details TEXT',fields),
    ('blueprint_schema_functions','package TEXT,cls TEXT,name TEXT,target_name TEXT,target_path TEXT',functions),
    ('blueprint_schema_properties','package TEXT,cls TEXT,name TEXT,value TEXT',values),
):
    db.execute('CREATE TABLE IF NOT EXISTS '+table+'('+declaration+')')
    db.execute('DELETE FROM '+table)
    db.executemany('INSERT INTO '+table+' VALUES('+','.join('?' for _ in declaration.split(','))+')', rows)
db.commit(); db.close()
summary = {'source':source,'confidence':'inferred_schema_candidate','status':dict(counts),'class_kinds':dict(kinds),'structural_checks':dict(checks),'consumption':dict(consumption),'fields':len(fields),'functions':len(functions),'serialized_property_entries':len(values),'serialized_property_names':dict(properties),'unresolved_references':unresolved,'limitations':['Saved SDK build provenance remains unverified.','SDK memory offsets/declaration order are an inferred serialization order.','Fatal serialization exceptions and independently visible replay cursors establish stronger structural checks, not semantic correctness of every property.','Replay uses the inspected UE5.3+ IoStore export-offset formula and the same parser; it is not an independent parser implementation.','These candidates do not replace the original empty-schema results.']}
(R/'index/schema-candidate-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2))
