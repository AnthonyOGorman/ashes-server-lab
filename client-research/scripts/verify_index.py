"""Check evidence consistency against the input PE and independent metadata counts."""
import hashlib,json,sqlite3,struct
from datetime import datetime,timezone
from pathlib import Path
import pefile
RESEARCH=Path(__file__).resolve().parents[1]
db=sqlite3.connect((RESEARCH/'index/client-index.sqlite').as_uri()+'?mode=ro',uri=True,timeout=60)
checks={}
def check(name,ok,details):
    checks[name]={'passed':bool(ok),'details':details}
native=json.loads(db.execute("SELECT value FROM metadata WHERE key='native'").fetchone()[0])
with open(native['path'],'rb') as file:digest=hashlib.sha256(file.read()).hexdigest()
check('input_executable_hash',digest==native['sha256'],digest)
integrity=[r[0] for r in db.execute('PRAGMA integrity_check')]
check('sqlite_integrity',integrity==['ok'],integrity)
pe=pefile.PE(native['path'],fast_load=True);pe.parse_data_directories(directories=[3])
records={(e.struct.BeginAddress,e.struct.EndAddress,e.struct.UnwindData) for e in pe.DIRECTORY_ENTRY_EXCEPTION}
indexed=set(db.execute('SELECT begin,end,unwind FROM native_ranges'))
check('exception_directory_matches_pe',records==indexed,{'pe_records':len(records),'indexed':len(indexed)})
wrong_pairs=0
base=pe.OPTIONAL_HEADER.ImageBase
for table,name,target,kind in db.execute('SELECT table_rva,name,target_rva,orientation FROM native_registration_pairs'):
    a,b=struct.unpack('<QQ',pe.get_data(table,16))
    name_ptr,code_ptr=(a,b) if kind=='native_registration_candidate' else (b,a)
    actual=pe.get_data(name_ptr-base,len(name)+1)
    if actual!=name.encode('ascii')+b'\0' or code_ptr-base!=target:wrong_pairs+=1
check('registration_table_bytes',wrong_pairs==0,{'wrong_pairs':wrong_pairs})
headers=db.execute('SELECT count(*) FROM package_exports WHERE cls="Function"').fetchone()[0]
scripts=db.execute('SELECT count(*) FROM blueprint_scripts').fetchone()[0]
check('selected_header_functions_have_scripts',headers==scripts,{'headers':headers,'scripts':scripts})
bad_flow=db.execute('SELECT count(*) FROM blueprint_flow WHERE target IS NOT NULL AND target_status!="statement_boundary"').fetchone()[0]
check('static_blueprint_branch_boundaries',bad_flow==0,{'non_statement_targets':bad_flow})
bad_class_functions=db.execute('SELECT count(*) FROM blueprint_class_functions c LEFT JOIN package_exports e ON e.package=c.package AND e.name=c.name AND e.cls="Function" WHERE e.name IS NULL').fetchone()[0]
check('class_function_map_matches_headers',bad_class_functions==0,{'unmatched_function_names':bad_class_functions})
bad_class_terminals=0
for name,body in db.execute('SELECT name,body FROM blueprint_classes WHERE status="class_metadata_candidate"'):
    doc=json.loads(body)
    if doc.get('Name')!=name or doc.get('bCooked') is not True or 'ClassDefaultObject' not in doc or 'ClassWithin' not in doc:bad_class_terminals+=1
check('class_terminal_metadata',bad_class_terminals==0,{'incomplete_counted_candidates':bad_class_terminals})
schema_summary=json.loads((RESEARCH/'index/schema-candidate-summary.json').read_text())
schema_checks=schema_summary['structural_checks']
schema_bad={k:v for k,v in schema_checks.items() if k in ('invalid_reference_shape','invalid_export_index','reference_name_mismatch','reference_class_mismatch','function_map_label_mismatch','terminal_class_metadata_missing') and v}
schema_functions=db.execute('SELECT count(*) FROM blueprint_schema_functions').fetchone()[0]
check('inferred_schema_structural_references',not schema_bad and schema_functions==headers,{'mismatches':schema_bad,'functions':schema_functions,'header_functions':headers,'unindexed_references':schema_checks.get('external_or_unindexed_reference',0),'confidence':'inferred schemas; payload consumption and semantics remain unverified'})
provenance=json.loads((RESEARCH/'schemas/sdk-offset-order-v1-provenance.json').read_text())
schema_hashes={kind:hashlib.sha256((RESEARCH/'schemas'/('sdk-offset-order-v1-'+kind+'.json')).read_bytes()).hexdigest() for kind in ('structs','enums')}
check('inferred_schema_file_hashes',all(schema_hashes[k]==provenance[k+'_sha256'] for k in schema_hashes),schema_hashes)
v2_provenance=json.loads((RESEARCH/'schemas/sdk-offset-order-v2-provenance.json').read_text())
v2_hashes={kind:hashlib.sha256((RESEARCH/'schemas'/('sdk-offset-order-v2-'+kind+'.json')).read_bytes()).hexdigest() for kind in ('structs','enums')}
check('configuration_schema_file_hashes',all(v2_hashes[k]==v2_provenance[k+'_sha256'] for k in v2_hashes),v2_hashes)
class_total=sum(schema_summary['status'].values())
check('inferred_class_payload_consumption',schema_summary['consumption']=={'exact_consumption':class_total},{'classes':class_total,'consumption':schema_summary['consumption']})
bad_defaults=db.execute('SELECT count(*) FROM blueprint_default_candidates WHERE status="inferred_schema_default_candidate" AND (expected_bytes IS NULL OR consumed_bytes IS NULL OR expected_bytes!=consumed_bytes)').fetchone()[0]
check('default_candidate_consumption_gate',bad_defaults==0,{'counted_candidates_with_wrong_consumption':bad_defaults,'limits':'Explicit failures and consumption gaps are preserved; these checks do not verify property meanings.'})
bad_assets=db.execute('SELECT count(*) FROM asset_value_candidates WHERE status="inferred_schema_asset_candidate" AND (expected_bytes IS NULL OR consumed_bytes IS NULL OR expected_bytes!=consumed_bytes OR parser_warning_count!=0)').fetchone()[0]
asset_summary=json.loads((RESEARCH/'index/asset-values-summary.json').read_text())
check('asset_value_structural_gates',bad_assets==0 and not asset_summary['structural_checks'].get('asset_identity_mismatch') and not asset_summary['structural_checks'].get('local_header_name_mismatch'),{'miscounted_candidates':bad_assets,'structural_checks':asset_summary['structural_checks'],'limits':'External/unindexed references and separately recorded consumption gaps remain unresolved.'})
wrong_virtual_slots=0;slot_count=0
for table,slot,target in db.execute('SELECT table_rva,slot,target_rva FROM native_virtual_slots'):
    slot_count+=1
    if struct.unpack('<Q',pe.get_data(table+slot,8))[0]-base!=target:wrong_virtual_slots+=1
check('constructor_virtual_table_bytes',wrong_virtual_slots==0,{'inspected_slots':slot_count,'mismatches':wrong_virtual_slots,'limits':'Constructor-table ownership follows saved static evidence; subclasses may override dispatch.'})
wrong_dispatch=0
for thunk,slot,table,target,ctor in db.execute('SELECT thunk_rva,slot,table_rva,target_rva,constructor_rva FROM native_dispatch_links'):
    if struct.unpack('<Q',pe.get_data(table+slot,8))[0]-base!=target or ctor!=0x6b8cd00 or table!=0xb6873d0:wrong_dispatch+=1
check('cooldown_dispatch_links',wrong_dispatch==0 and pe.get_data(0x6b8cd1d,10)==bytes.fromhex('488d05aca6af04488907'),{'mismatches':wrong_dispatch,'constructor':'0x6b8cd00','table':'0xb6873d0'})
expected=db.execute('SELECT sum(methods),sum(bodies) FROM all_managed_modules WHERE status="metadata_parsed"').fetchone()
actual=(db.execute('SELECT count(*) FROM all_managed_methods').fetchone()[0],db.execute('SELECT count(*) FROM all_managed_methods WHERE il_bytes IS NOT NULL').fetchone()[0])
check('managed_module_method_totals',tuple(expected)==actual,{'module_totals':expected,'method_rows':actual})
body_errors=db.execute('SELECT count(*) FROM all_managed_methods WHERE body_error IS NOT NULL').fetchone()[0]
check('managed_il_body_readability',body_errors==0,{'errors':body_errors})
bad_unwind=db.execute('SELECT count(*) FROM native_unwind WHERE status!="header_parsed"').fetchone()[0]
check('unwind_chains',bad_unwind==0,{'review_required':bad_unwind})
fragment=pe.get_data(0x5ec4de0,7)
check('sprint_setter_instruction_bytes',fragment==bytes.fromhex('8891d0110000c3'),fragment.hex())
missing_hash=0;failures=0;outputs=0
for path in (RESEARCH/'decompiled').glob('**/function_*.c'):
    text=path.read_text(encoding='utf-8',errors='replace');outputs+=1
    if native['sha256'] not in text:missing_hash+=1
    if 'Decompilation failed:' in text:failures+=1
check('native_output_hash_binding',missing_hash==0,{'outputs':outputs,'missing_hash':missing_hash,'explicit_decompiler_failures':failures})
result={'verified_at':datetime.now(timezone.utc).isoformat(),'passed':all(row['passed'] for row in checks.values()),'checks':checks,'limitation':'These checks validate evidence consistency and selected byte interpretations, not complete semantic correctness or gameplay behavior.'}
(RESEARCH/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));pe.close();db.close()
if not result['passed']:raise SystemExit(1)
