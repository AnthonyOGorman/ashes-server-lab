"""Export native terrain schemas from the exact client's reflection. Read-only.

This exports class definitions, not streamed terrain actors, and makes no game
calls or memory writes. It can run without traversing world cells.
"""
import sys, pathlib, json, struct, inspect, textwrap, types
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'tools'))
from dump_runtime_reflection import Reader, Reflection, ReadError, pointer, validate_sdk, SDK
from protocol_proof import EXPECTED_EXE, client_proof

root=pathlib.Path(__file__).resolve().parents[1]
pid=int(sys.argv[1]); proof=client_proof(pid); validate_sdk(SDK)
reader=Reader(pid,EXPECTED_EXE)
out=root/'data/terrain-offline/mappings'; out.mkdir(parents=True,exist_ok=True)
try:
    reflection=Reflection(reader,1_000_000)
    # Some loaded Blueprint classes exceed the diagnostic default member bound.
    source=textwrap.dedent(inspect.getsource(Reflection.properties)).replace('len(result)<512','len(result)<2048')
    namespace=dict(Reflection.properties.__globals__);exec(source,namespace)
    reflection.properties=types.MethodType(namespace['properties'],reflection)
    classes={}
    for address,obj in reflection.objects():
        if reflection.class_name(obj['class_address']) in ('Class','ScriptStruct','BlueprintGeneratedClass','WidgetBlueprintGeneratedClass','AnimBlueprintGeneratedClass'):
            classes[obj['name']]=address
    targets={n for n in classes if n.startswith('Landscape') or n.startswith('WorldPartition')}
    targets.update(n for n in ('Actor','SceneComponent','PrimitiveComponent','BodySetup','PhysicalMaterial','Level','World','Model','Brush','BrushComponent') if n in classes)
    schemas={}; enums={}; errors=[]
    def enum_mapping(address):
        obj=reflection.obj(address);name=obj['name']
        if name not in enums:
            data,count,capacity=reader.unpack(address+0x60,'<Qii')
            if not 0<=count<=capacity<=65536:raise ReadError('Enum array bounds')
            raw=reader.read(data,count*16) if count else b''
            values={}
            for i in range(count):
                index,number,value=struct.unpack_from('<IIq',raw,i*16)
                values[str(value)]=reflection.names.get(index,number)
            enums[name]=values
        return name
    def property_type(address,depth=0):
        if depth>=16 or not pointer(address):raise ReadError('Nested property bound')
        fieldclass=reader.unpack(address+8,'<Q')[0]
        kind=reflection.names.get(*reader.unpack(fieldclass,'<II'))
        result={'type':kind}
        if kind=='StructProperty':
            target=reader.unpack(address+0x70,'<Q')[0];name=reflection.obj(target)['name']
            result['structType']=name;targets.add(name);classes.setdefault(name,target)
        elif kind in ('ArrayProperty','SetProperty','OptionalProperty'):
            offset=0x78 if kind=='ArrayProperty' else 0x70
            result['innerType']=property_type(reader.unpack(address+offset,'<Q')[0],depth+1)
        elif kind=='MapProperty':
            result['innerType']=property_type(reader.unpack(address+0x70,'<Q')[0],depth+1)
            result['valueType']=property_type(reader.unpack(address+0x78,'<Q')[0],depth+1)
        elif kind=='EnumProperty':
            result['innerType']=property_type(reader.unpack(address+0x70,'<Q')[0],depth+1)
            result['enumName']=enum_mapping(reader.unpack(address+0x78,'<Q')[0])
        elif kind=='ByteProperty':
            target=reader.unpack(address+0x70,'<Q')[0]
            if target:
                result={'type':'EnumProperty','innerType':{'type':'ByteProperty'},'enumName':enum_mapping(target),'isEnumAsByte':True}
        return result
    processed=set()
    while targets-processed:
        name=sorted(targets-processed)[0];processed.add(name)
        try:
            address=classes[name];head=reader.unpack(address+0x70,'<Q')[0];size=reader.unpack(address+0x78,'<i')[0]
            parent=reader.unpack(address+0x60,'<Q')[0]
            super_name=reflection.obj(parent)['name'] if parent else None
            if super_name:targets.add(super_name);classes.setdefault(super_name,parent)
            properties=[];index=0
            for p in reflection.properties(head,size):
                if int(p['flags'],16)&0x800000000:continue # CPF_EditorOnly
                properties.append({'index':index,'name':p['name'],'arraySize':p['array_dim'],'mappingType':property_type(int(p['address'],16))})
                index+=p['array_dim']
            schemas[name]={'name':name,'superType':super_name,'propertyCount':index,'properties':properties}
        except (ReadError,UnicodeError,KeyError) as error:errors.append({'name':name,'error':str(error)})
    (out/'structs.json').write_text(json.dumps(list(schemas.values())),encoding='utf-8')
    (out/'enums.json').write_text(json.dumps(enums),encoding='utf-8')
    report={'proof':proof,'schemas':len(schemas),'enums':len(enums),'errors':errors,'validation':reflection.validation,'bytes_read':reader.bytes_read,'access':'PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION','scope':'native terrain and referenced schemas; no world cell traversal'}
    (out/'proof.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'schemas':len(schemas),'enums':len(enums),'errors':errors,'bytes_read':reader.bytes_read}))
finally:reader.close()
