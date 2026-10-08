"""Verify six saved gate decompilations, exact leaves and historical RPC metadata."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]; ROOT=R.parent
gate=json.loads((R/'proofs/loading-controller-gate-targets.json').read_bytes())
runtime_path=ROOT/'evidence/runtime_reflection_world_49892.json'
cache_path=ROOT/'evidence/driver_net_cache_world_49892.json'
runtime=json.loads(runtime_path.read_bytes()); cache=json.loads(cache_path.read_bytes())
assert runtime['sha256']==gate['exe_sha256']
def walk(x):
    if isinstance(x,dict):
        yield x
        for v in x.values():yield from walk(v)
    elif isinstance(x,list):
        for v in x:yield from walk(v)
functions=[x for x in walk(runtime) if x.get('name')=='ClientIgnoreMoveInput' and 'exec_address' in x]
assert len(functions)==1
function=functions[0]
assert int(function['exec_address'],16)-int(runtime['module_base'],16)==0x4442390
assert function['flags']=='0x1020cc2' and function['struct_size']==1
assert len(function['parameters'])==1
param=function['parameters'][0]
assert param['name']=='bIgnore' and param['type']=='BoolProperty'
assert param['offset_in_object']==0 and param['element_size']==1
fields=[x for x in walk(cache) if x.get('name')=='ClientIgnoreMoveInput' and 'field_net_index' in x]
assert len(fields)==1 and fields[0]['field_net_index']==34 and fields[0]['checksum']==898884168
outputs=[]
for rva in (0x4442390,0x3f0b820,0x3ef5810,0x3ef23f0,0x3eea250,0x44119b0):
    p=R/f'decompiled/loading-input-gates/function_{rva:x}.c'
    text=p.read_text(encoding='utf-8')
    assert gate['exe_sha256'] in text and 'Decompilation failed:' not in text
    outputs.append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
for entry in gate['entries']:
    binary=R/f'proofs/loading-input-gate-{int(entry["target_rva"],16):x}.bin'
    assert binary.read_bytes().hex()==entry['complete_selected_linear_leaf_bytes']
    assert hashlib.sha256(binary.read_bytes()).hexdigest()==entry['fragment_sha256']
out={'status':'static_gates_verified','exe_sha256':gate['exe_sha256'],
     'sources':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in
                (runtime_path,cache_path,R/'proofs/loading-controller-gate-targets.json')],
     'rpc':{'name':function['name'],'flags':function['flags'],'native_exec_rva':'0x4442390',
            'historical_field_net_index':34,'historical_checksum':898884168,'parameter':param},
     'counter':{'offset':'0x3f9','type':'unreflected U8','true':'n+1, positive result truncated to U8',
                'false':'n-1, negative/zero result becomes0','overflow':'255+1 wraps0',
                'query':'counter>0','reset':'counter=0'},'decompiled_outputs':outputs,
     'limits':['Current controller vtable/class cache/lifetime and paired RPC receipt need live verification.',
               'One-byte parameter memory layout does not establish wire bit length.',
               'IgnoreMoveInput is an input stack gate; does not prove jumping, gravity or physics disabled.',
               'No RPCs or native functions invoked.']}
(R/'proofs/loading-gate-verification.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':out['status'],'outputs':len(outputs),'historical_rpc_field':34}))
