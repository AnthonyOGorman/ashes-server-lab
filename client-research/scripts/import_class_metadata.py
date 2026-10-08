"""Validate terminal class records, rejecting partial exports returned by the loader."""
import json,sqlite3
from collections import Counter
from pathlib import Path
RESEARCH=Path(__file__).resolve().parents[1]
db=sqlite3.connect(RESEARCH/'index/client-index.sqlite',timeout=60)
db.executescript('''
CREATE TABLE IF NOT EXISTS blueprint_classes(package TEXT,name TEXT,cls TEXT,status TEXT,parent_name TEXT,parent_path TEXT,default_object TEXT,flags TEXT,body TEXT);
CREATE TABLE IF NOT EXISTS blueprint_class_fields(package TEXT,cls TEXT,name TEXT,type TEXT,element_size INTEGER,flags TEXT,details TEXT);
CREATE TABLE IF NOT EXISTS blueprint_class_functions(package TEXT,cls TEXT,name TEXT,target_name TEXT,target_path TEXT);
CREATE TABLE IF NOT EXISTS blueprint_class_interfaces(package TEXT,cls TEXT,target_name TEXT,target_path TEXT,pointer_offset INTEGER,implemented_by_k2 INTEGER);
DELETE FROM blueprint_classes; DELETE FROM blueprint_class_fields; DELETE FROM blueprint_class_functions; DELETE FROM blueprint_class_interfaces;
''')
statuses=Counter();class_kinds=Counter()
for line in (RESEARCH/'index/blueprint-class-metadata.jsonl').open(encoding='utf-8-sig'):
    row=json.loads(line);doc=json.loads(row.get('class_json','{}'));name=row.get('name','<package>');status=row['status']
    if doc.get('Name')!=name:status='name_mismatch_or_failed'
    elif doc.get('bCooked') is not True or 'ClassDefaultObject' not in doc or 'ClassWithin' not in doc:status='partial_class_requires_schema'
    else:status='class_metadata_candidate'
    parent=doc.get('SuperStruct',{});statuses[status]+=1;class_kinds[(row.get('cls'),status)]+=1
    db.execute('INSERT INTO blueprint_classes VALUES(?,?,?,?,?,?,?,?,?)',(row['package'],name,row.get('cls'),status,parent.get('ObjectName'),parent.get('ObjectPath'),json.dumps(doc.get('ClassDefaultObject')) if 'ClassDefaultObject' in doc else None,doc.get('ClassFlags'),row.get('class_json',row.get('error'))))
    if status!='class_metadata_candidate':continue
    for field in doc.get('ChildProperties',[]):
        db.execute('INSERT INTO blueprint_class_fields VALUES(?,?,?,?,?,?,?)',(row['package'],name,field['Name'],field['Type'],field.get('ElementSize'),field.get('PropertyFlags'),json.dumps(field)))
    for label,target in doc.get('FuncMap',{}).items():
        db.execute('INSERT INTO blueprint_class_functions VALUES(?,?,?,?,?)',(row['package'],name,label,target.get('ObjectName'),target.get('ObjectPath')))
    for interface in doc.get('Interfaces',[]):
        target=interface.get('Class',{})
        db.execute('INSERT INTO blueprint_class_interfaces VALUES(?,?,?,?,?,?)',(row['package'],name,target.get('ObjectName'),target.get('ObjectPath'),interface.get('PointerOffset'),int(interface.get('bImplementedByK2',False))))
db.commit()
summary={'class_exports':sum(statuses.values()),'class_status':dict(statuses),'class_kinds':{str(k):v for k,v in class_kinds.items()},'validated_candidate_fields':db.execute('SELECT count(*) FROM blueprint_class_fields').fetchone()[0],'validated_candidate_functions':db.execute('SELECT count(*) FROM blueprint_class_functions').fetchone()[0],'validated_candidate_interfaces':db.execute('SELECT count(*) FROM blueprint_class_interfaces').fetchone()[0],'limitations':['IoPackage can return a partial export after swallowing a parser exception; terminal UClass records are required for candidate coverage.','Empty metaclass schemas only suffice for exports without serialized property values.','General class defaults, component templates and incomplete classes still require correct type schemas.','Terminal records establish structural candidates, not complete payload/operand or runtime verification.']}
(RESEARCH/'index/class-metadata-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary,indent=2));db.close()
