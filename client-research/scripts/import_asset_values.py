"""Index selected configuration assets; preserve incomplete consumption and warning gates."""
import json,re,sqlite3
from collections import Counter
from pathlib import Path
R=Path(__file__).resolve().parents[1]
db=sqlite3.connect(R/'index/client-index.sqlite',timeout=60)
db.executescript('''
CREATE TABLE IF NOT EXISTS asset_value_candidates(package TEXT,name TEXT,cls TEXT,status TEXT,schema_hash TEXT,expected_bytes INTEGER,consumed_bytes INTEGER,parser_warning_count INTEGER,body TEXT);
CREATE TABLE IF NOT EXISTS asset_value_properties(package TEXT,asset TEXT,name TEXT,value TEXT);
CREATE TABLE IF NOT EXISTS asset_table_rows(package TEXT,asset TEXT,name TEXT,value TEXT);
CREATE TABLE IF NOT EXISTS asset_value_references(package TEXT,asset TEXT,field_path TEXT,target_name TEXT,target_path TEXT,target_status TEXT);
DELETE FROM asset_value_candidates; DELETE FROM asset_value_properties; DELETE FROM asset_table_rows; DELETE FROM asset_value_references;
''')
headers={}
for package,index,name,cls in db.execute('SELECT package,export_index,name,cls FROM package_exports'):
    headers[(package.casefold(),index)]=(name,cls)
status_counts,kinds,consumption,checks,warning_counts=Counter(),Counter(),Counter(),Counter(),Counter()
nproperties,nrows,nrefs=0,0,0
def references(value,path='$'):
    if isinstance(value,dict):
        if 'ObjectName' in value and 'ObjectPath' in value:yield path,value
        for key,child in value.items():yield from references(child,path+'.'+key)
    elif isinstance(value,list):
        for idx,child in enumerate(value):yield from references(child,path+'['+str(idx)+']')
for line in (R/'index/asset-values-v2.jsonl').open(encoding='utf-8-sig'):
    row=json.loads(line);status=row['status'];kind=row.get('cls');kinds[kind]+=1
    warnings=row.get('parserWarnings',[])
    for warning in warnings:warning_counts[warning]+=1
    expected,consumed=row.get('expectedSerialBytes'),row.get('consumedSerialBytes')
    if status=='inferred_schema_asset_candidate':
        state='exact_consumption' if expected==consumed and expected is not None else 'under_consumed' if consumed is not None and expected is not None and consumed<expected else 'over_consumed_or_unmeasured'
        consumption[state]+=1
        if state!='exact_consumption':status='asset_requires_consumption_review'
        elif warnings:status='asset_warning_requires_review'
        doc=json.loads(row['class_json'])
        if doc.get('Name')!=row['name']:raise ValueError('Asset export name mismatch')
        matches=db.execute('SELECT count(*) FROM package_exports WHERE package=? AND name=? AND cls=?',(row['package'],row['name'],kind)).fetchone()[0]
        checks['asset_identity_matches_header' if matches==1 else 'asset_identity_mismatch']+=1
        for name,value in doc.get('Properties',{}).items():
            db.execute('INSERT INTO asset_value_properties VALUES(?,?,?,?)',(row['package'],row['name'],name,json.dumps(value)));nproperties+=1
        for name,value in (doc.get('Rows') or {}).items():
            db.execute('INSERT INTO asset_table_rows VALUES(?,?,?,?)',(row['package'],row['name'],name,json.dumps(value)));nrows+=1
        for path,ref in references(doc):
            match=re.match(r'^(.*)\.(\d+)$',ref['ObjectPath']);target_status='external_or_unindexed'
            if match and (match[1].casefold(),int(match[2])) in headers:
                name,cls=headers[(match[1].casefold(),int(match[2]))]
                target_status='local_header_match' if any(ref['ObjectName'].endswith(prefix+name+"'") for prefix in ("'",':','.')) else 'local_header_name_mismatch'
            checks[target_status]+=1
            db.execute('INSERT INTO asset_value_references VALUES(?,?,?,?,?,?)',(row['package'],row['name'],path,ref['ObjectName'],ref['ObjectPath'],target_status));nrefs+=1
    status_counts[status]+=1
    db.execute('INSERT INTO asset_value_candidates VALUES(?,?,?,?,?,?,?,?,?)',(row['package'],row.get('name'),kind,status,row.get('schemaHash'),expected,consumed,len(warnings),row.get('class_json',row.get('error'))))
db.commit();db.close()
summary={'source':'asset-values-v2.jsonl','confidence':'inferred_schema_asset_candidate','status':dict(status_counts),'classes':dict(kinds),'consumption':dict(consumption),'structural_checks':dict(checks),'serialized_properties':nproperties,'table_rows':nrows,'object_references':nrefs,'parser_warning_lines':sum(warning_counts.values()),'parser_warning_groups':dict(warning_counts),'limits':['Only selected configuration export classes in the existing header inventory were attempted.','Exact consumption and matching references are structural evidence; schemas and property interpretations remain inferred.','Nested component/AI-node/input-modifier export payloads are not decoded merely because a reference was decoded.','Serialized properties can omit inherited/default-zero values.','Warning and consumption gaps remain distinct statuses; catalog rows include their source candidate status.','References outside the indexed header set are explicitly unresolved.']}
(R/'index/asset-values-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k!='parser_warning_groups'},indent=2))
