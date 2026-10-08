"""Build explicitly inferred serialization schemas from saved SDK declarations.

Layout/declaration ordering is a hypothesis, not a recovered usmap. Unknown types
and ambiguous names remain explicit. These candidates require independent checks.
"""
import argparse,hashlib,json,re,sqlite3
from collections import Counter,defaultdict
from pathlib import Path
RESEARCH=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--version',default='v2')
args=parser.parse_args()
if not re.fullmatch(r'v\d+',args.version):parser.error('version must have the form v2')
db=sqlite3.connect((RESEARCH/'index/client-index.sqlite').as_uri()+'?mode=ro',uri=True)
types=db.execute('SELECT full_name,cpp_name,parent FROM sdk_types').fetchall()
cpp=defaultdict(list);names=defaultdict(list)
for full,cname,parent in types:cpp[cname].append(full);names[full.split('.',1)[1]].append(full)
enum_cpp={c:(full,underlying) for full,c,underlying in db.execute('SELECT full_name,cpp_name,underlying_type FROM sdk_enums')}
primitive={'bool':'BoolProperty','uint8':'ByteProperty','uint16':'UInt16Property','uint32':'UInt32Property','uint64':'UInt64Property','int8':'Int8Property','int16':'Int16Property','int32':'IntProperty','int64':'Int64Property','float':'FloatProperty','double':'DoubleProperty','FName':'NameProperty','FString':'StrProperty','FText':'TextProperty','FUtf8String':'Utf8StrProperty','FAnsiString':'AnsiStrProperty'}
unknown=Counter();source_lines={}
def split_template(body):
    depth=0;start=0;parts=[]
    for i,ch in enumerate(body):
        depth+=ch=='<';depth-=ch=='>'
        if ch==',' and depth==0:parts.append(body[start:i].strip());start=i+1
    parts.append(body[start:].strip());return parts
def prop_type(value,flags=''):
    value=re.sub(r'\b(?:class|struct|enum class|const)\s+','',value).strip()
    if 'BitIndex:' in flags:return {'type':'BoolProperty'}
    if value in primitive:return {'type':primitive[value]}
    match=re.fullmatch(r'(\w+)<(.*)>',value)
    if match:
        wrapper,body=match.groups();inner=split_template(body)
        if wrapper in ('TArray','TSet','TOptional') and len(inner)==1:return {'type':{'TArray':'ArrayProperty','TSet':'SetProperty','TOptional':'OptionalProperty'}[wrapper],'innerType':prop_type(inner[0])}
        if wrapper=='TMap' and len(inner)==2:return {'type':'MapProperty','innerType':prop_type(inner[0]),'valueType':prop_type(inner[1])}
        if wrapper in ('TSubclassOf','TObjectPtr'):return {'type':'ObjectProperty'}
        if wrapper in ('TSoftObjectPtr','TSoftClassPtr'):return {'type':'SoftObjectProperty'}
        if wrapper=='TWeakObjectPtr':return {'type':'WeakObjectProperty'}
        if wrapper=='TLazyObjectPtr':return {'type':'LazyObjectProperty'}
        if wrapper=='TScriptInterface':return {'type':'InterfaceProperty'}
        if wrapper=='TEnumAsByte':return {'type':'ByteProperty','enumName':inner[0]}
        if wrapper.startswith('TMulticast'):return {'type':'MulticastDelegateProperty'}
        if wrapper=='TDelegate':return {'type':'DelegateProperty'}
    if value.endswith('*') and value.rstrip('*').strip().startswith(('U','A')):return {'type':'ObjectProperty'}
    if value in enum_cpp:
        full,underlying=enum_cpp[value]
        return {'type':'EnumProperty','enumName':full.split('.',1)[1],'innerType':{'type':primitive.get(underlying,'UnknownProperty')}}
    candidates=cpp.get(value,[])
    if len(candidates)==1:return {'type':'StructProperty','structType':candidates[0].split('.',1)[1]}
    unknown[value]+=1;return {'type':'UnknownProperty'}
schemas=[];excluded=Counter();ambiguous=[]
for full,cname,parent in types:
    raw_name=full.split('.',1)[1]
    if len(names[raw_name])!=1:ambiguous.append(full);continue
    properties=[];index=0
    for name,ctype,offset,flags,source,line in db.execute('SELECT name,cpp_type,offset,flags,source,line FROM sdk_properties WHERE owner=? ORDER BY offset,line',(full,)):
        if 'NOT AUTO-GENERATED PROPERTY' in flags:excluded['synthetic_sdk_member']+=1;continue
        if 'EditorOnly' in flags:excluded['editor_only']+=1;continue
        if ctype.startswith('static '):excluded['static']+=1;continue
        if source not in source_lines:source_lines[source]=Path(source).read_text(encoding='utf-8-sig',errors='replace').splitlines()
        declaration=source_lines[source][line-1];array_match=re.search(r'\b'+re.escape(name)+r'\[(0x[0-9A-Fa-f]+|\d+)\]',declaration)
        dim=int(array_match[1],0) if array_match else 1
        properties.append({'index':index,'name':name,'arraySize':dim,'mappingType':prop_type(ctype,flags)})
        index+=dim
    item={'name':raw_name,'propertyCount':index,'properties':properties}
    if parent:
        candidates=cpp.get(parent,[]);same=[n for n in candidates if n.split('.',1)[0]==full.split('.',1)[0]]
        match=same[0] if len(same)==1 else candidates[0] if len(candidates)==1 else None
        if match:item['superType']=match.split('.',1)[1]
        else:excluded['unresolved_super']+=1
    schemas.append(item)
enums=[]
for full,cname,underlying in db.execute('SELECT full_name,cpp_name,underlying_type FROM sdk_enums'):
    values=[(n,int(v)) for n,v in db.execute('SELECT name,value FROM sdk_enum_values WHERE owner=? AND value IS NOT NULL',(full,))]
    if not values or min(v for _,v in values)<0 or max(v for _,v in values)>4096:continue
    dense=[f'__unresolved_value_{i}' for i in range(max(v for _,v in values)+1)]
    for name,value in values:dense[value]=name
    enums.append({'name':full.split('.',1)[1],'values':dense})
out=RESEARCH/'schemas';out.mkdir(exist_ok=True)
struct_path=out/f'sdk-offset-order-{args.version}-structs.json';enum_path=out/f'sdk-offset-order-{args.version}-enums.json'
struct_path.write_text(json.dumps(schemas,separators=(',',':')),encoding='utf-8');enum_path.write_text(json.dumps(enums,separators=(',',':')),encoding='utf-8')
summary={'candidate_schemas':len(schemas),'candidate_enums':len(enums),'ambiguous_short_names':ambiguous,'unsupported_cpp_types':dict(unknown),'excluded':dict(excluded),'structs_sha256':hashlib.sha256(struct_path.read_bytes()).hexdigest(),'enums_sha256':hashlib.sha256(enum_path.read_bytes()).hexdigest(),'source':'Saved generated SDK and indexed enum declarations','confidence':'inferred_schema_candidate','limits':['Memory offset/declaration order has not yet been proven to equal serialized property order.','SDK dump complete build provenance is unverified.','EditorOnly and synthetic/static SDK fields were excluded; array dimensions were re-read from declarations.','Unknown property types and ambiguous type names are not guessed.','A successful parse still needs independent terminal, reference, value and consumption checks.']}
(out/f'sdk-offset-order-{args.version}-provenance.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in summary.items() if k not in ('ambiguous_short_names','unsupported_cpp_types')},indent=2));db.close()
