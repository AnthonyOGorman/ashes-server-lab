"""Export reviewable CSV catalogs and machine-readable coverage from the evidence DB."""
import argparse
import csv
import json
import sqlite3
from datetime import datetime,timezone
from pathlib import Path
RESEARCH=Path(__file__).resolve().parents[1]
db=sqlite3.connect((RESEARCH/'index/client-index.sqlite').as_uri()+'?mode=ro',uri=True)
db.execute('BEGIN')  # One consistent read snapshot while native batches continue.
out=RESEARCH/'catalogs';out.mkdir(exist_ok=True)
queries={
 'reflected-functions': 'SELECT f.full_name,f.flags,f.signature,CASE WHEN n.rva IS NOT NULL THEN printf("0x%x",n.rva) END AS native_candidate_rva,n.kind,q.status,q.boundary,f.source,f.line FROM sdk_functions f LEFT JOIN native_labels n ON n.name=f.full_name AND n.kind="native_registration_candidate" LEFT JOIN decompile_queue q ON q.begin=n.rva ORDER BY f.full_name',
 'types': 'SELECT * FROM sdk_types ORDER BY full_name',
 'properties': 'SELECT owner,name,cpp_type,printf("0x%x",offset) AS offset,size,flags,source,line FROM sdk_properties ORDER BY owner,offset',
 'enums': 'SELECT * FROM sdk_enums ORDER BY full_name',
 'enum-values': 'SELECT * FROM sdk_enum_values ORDER BY owner,CAST(value AS INTEGER),name',
 'modules': 'SELECT * FROM modules ORDER BY path',
 'module-dependencies': 'SELECT * FROM module_dependencies ORDER BY path,dll',
 'assets': 'SELECT package,name,cls,path,chunks FROM assets ORDER BY package,name',
 'blueprint-functions': 'SELECT package,export_index,name,size,serial_offset,flags FROM package_exports WHERE cls="Function" ORDER BY package,name',
 'managed-methods': 'SELECT * FROM managed_methods ORDER BY assembly,token',
 'all-managed-methods': 'SELECT * FROM all_managed_methods ORDER BY path,owner,token',
 'all-managed-modules': 'SELECT * FROM all_managed_modules ORDER BY path',
 'native-module-exports': 'SELECT path,name,ordinal,printf("0x%x",rva) AS rva,forwarder FROM module_native_exports ORDER BY path,rva',
 'native-module-ranges': 'SELECT path,printf("0x%x",begin) AS begin,printf("0x%x",end) AS end,status FROM module_native_ranges ORDER BY path,begin',
 'native-unwind': 'SELECT * FROM native_unwind ORDER BY begin',
 'decompiler-diagnostics': 'SELECT printf("0x%x",begin) AS begin,path,hash_matches,reported_failure,bad_data_halt,control_flow_warning,warnings FROM decompiler_diagnostics ORDER BY begin',
 'blueprint-fields': 'SELECT package,function,name,type,element_size,flags,details FROM blueprint_fields ORDER BY package,function,name',
 'blueprint-flow': 'SELECT * FROM blueprint_flow ORDER BY package,function,source',
 'blueprint-classes': 'SELECT package,name,cls,status,parent_name,parent_path,default_object,flags FROM blueprint_classes ORDER BY package,name',
 'blueprint-class-fields': 'SELECT * FROM blueprint_class_fields ORDER BY package,cls,name',
 'blueprint-class-functions': 'SELECT * FROM blueprint_class_functions ORDER BY package,cls,name',
 'blueprint-class-interfaces': 'SELECT * FROM blueprint_class_interfaces ORDER BY package,cls',
 'blueprint-schema-candidates': 'SELECT package,name,cls,status,schema_hash,property_count FROM blueprint_schema_candidates ORDER BY package,name',
 'blueprint-schema-fields': 'SELECT * FROM blueprint_schema_fields ORDER BY package,cls,name',
 'blueprint-schema-functions': 'SELECT * FROM blueprint_schema_functions ORDER BY package,cls,name',
 'blueprint-schema-properties': 'SELECT * FROM blueprint_schema_properties ORDER BY package,cls,name',
 'blueprint-default-candidates': 'SELECT package,name,cls,status,schema_hash,expected_bytes,consumed_bytes FROM blueprint_default_candidates ORDER BY package,name',
 'blueprint-default-properties': 'SELECT p.package,p.cls,p.name,p.value,c.status FROM blueprint_default_properties p JOIN blueprint_default_candidates c ON c.package=p.package AND c.cls=p.cls ORDER BY p.package,p.cls,p.name',
 'native-virtual-slots': 'SELECT owner,printf("0x%x",table_rva) AS table_rva,printf("0x%x",slot) AS slot,printf("0x%x",target_rva) AS target_rva,printf("0x%x",constructor_rva) AS constructor_rva,status FROM native_virtual_slots ORDER BY owner,table_rva,slot',
 'native-dispatch-links': 'SELECT owner,method,printf("0x%x",thunk_rva) AS thunk_rva,printf("0x%x",slot) AS slot,printf("0x%x",table_rva) AS table_rva,printf("0x%x",target_rva) AS target_rva,printf("0x%x",constructor_rva) AS constructor_rva,evidence FROM native_dispatch_links ORDER BY owner,method',
 'asset-value-candidates': 'SELECT package,name,cls,status,schema_hash,expected_bytes,consumed_bytes,parser_warning_count FROM asset_value_candidates ORDER BY package,name',
 'asset-value-properties': 'SELECT p.*,c.status FROM asset_value_properties p JOIN asset_value_candidates c ON c.package=p.package AND c.name=p.asset ORDER BY p.package,p.asset,p.name',
 'asset-table-rows': 'SELECT r.*,c.status FROM asset_table_rows r JOIN asset_value_candidates c ON c.package=r.package AND c.name=r.asset ORDER BY r.package,r.asset,r.name',
 'asset-value-references': 'SELECT * FROM asset_value_references ORDER BY package,asset,field_path',
 'input-bindings': 'SELECT package,binding_index,action,action_path,key,triggers,modifiers,status FROM input_bindings ORDER BY package,binding_index',
 'blueprint-calls': 'SELECT package,function,token,target_name,target_path,CASE WHEN native_candidate_rva IS NOT NULL THEN printf("0x%x",native_candidate_rva) END AS native_candidate_rva FROM blueprint_calls ORDER BY package,function',
 'source-references': 'SELECT printf("0x%x",source_begin) AS source_begin,printf("0x%x",instruction_rva) AS instruction,printf("0x%x",string_rva) AS string,path FROM source_path_refs ORDER BY path,source_begin',
 'decompile-gaps': 'SELECT printf("0x%x",q.begin) AS begin,printf("0x%x",q.end) AS end,q.label,q.boundary,q.status,q.output,CASE WHEN u.root_begin IS NOT NULL THEN printf("0x%x",u.root_begin) END AS unwind_root FROM decompile_queue q LEFT JOIN native_unwind u ON u.begin=q.begin WHERE q.status NOT IN ("pending","decompiled_unreviewed","decompiled_fragment_unreviewed","chained_fragment_indexed") ORDER BY q.begin',
}
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--only',choices=sorted(queries))
args=parser.parse_args()
if args.only:queries={args.only:queries[args.only]}
for name,sql in queries.items():
    cursor=db.execute(sql)
    with (out/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.writer(file);writer.writerow([c[0] for c in cursor.description]);writer.writerows(cursor)
if args.only:
    db.close();print(json.dumps({'catalog':args.only}));raise SystemExit(0)
counts={t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['native_ranges','strings','sdk_types','sdk_functions','sdk_properties','sdk_enums','sdk_enum_values','assets','archive_files','package_headers','package_exports','managed_methods','entry_blocks','source_path_refs','all_managed_methods','all_managed_modules','module_native_ranges','module_native_exports','native_unwind','blueprint_fields','blueprint_flow']}
coverage={'updated_at':datetime.now(timezone.utc).isoformat(),'counts':counts,
 'decompile_status':dict(db.execute('SELECT status,count(*) FROM decompile_queue GROUP BY status')),
 'mapped_sdk_methods':db.execute('SELECT count(DISTINCT f.full_name) FROM sdk_functions f JOIN native_labels n ON n.name=f.full_name AND n.kind="native_registration_candidate"').fetchone()[0],
 'blueprint_function_exports':db.execute('SELECT count(*) FROM package_exports WHERE cls="Function"').fetchone()[0],
 'blueprint_scripts':json.loads((RESEARCH/'index/bytecode-summary.json').read_text()),
 'native_decode':json.loads((RESEARCH/'index/code-summary.json').read_text()),
 'native_unwind':json.loads((RESEARCH/'index/unwind-summary.json').read_text()),
 'decompiler_quality':json.loads((RESEARCH/'index/decompiler-quality-summary.json').read_text()),
 'all_modules':json.loads((RESEARCH/'index/module-definitions-summary.json').read_text()),
 'blueprint_flow':json.loads((RESEARCH/'index/blueprint-flow-summary.json').read_text()),
 'blueprint_classes':json.loads((RESEARCH/'index/class-metadata-summary.json').read_text()),
 'blueprint_schema_candidates':json.loads((RESEARCH/'index/schema-candidate-summary.json').read_text()),
 'blueprint_default_candidates':json.loads((RESEARCH/'index/default-candidate-summary.json').read_text()),
 'native_virtual_dispatch':json.loads((RESEARCH/'proofs/cooldown-dispatch.json').read_text()),
 'asset_values':json.loads((RESEARCH/'index/asset-values-summary.json').read_text()),
 'atlas':json.loads((RESEARCH/'index/atlas-summary.json').read_text()),
 'module_kinds':dict(db.execute('SELECT kind,count(*) FROM modules GROUP BY kind')),
 'packages':[dict(package=r[0],types=r[1],functions=db.execute('SELECT count(*) FROM sdk_functions WHERE package=?',(r[0],)).fetchone()[0]) for r in db.execute('SELECT package,count(*) FROM sdk_types GROUP BY package ORDER BY count(*) DESC').fetchall()],
 'limits':['Inventory and decompilation are not semantic verification.','No original PDB found in installed file inventory; PE retains an expected PDB name and GUID.','Native indirect dispatch, omitted leaf code, inlining, stripped identities and type reconstruction remain incomplete.','Blueprint instruction decoding passed structural checks for the selected function exports; gameplay behavior and other asset properties remain unverified.','The installed EOS DLL is a local replacement.','Historical runtime labels are bound to their saved executable hash and capture time.']}
(RESEARCH/'coverage.json').write_text(json.dumps(coverage,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in coverage.items() if k!='packages'},indent=2));db.close()
