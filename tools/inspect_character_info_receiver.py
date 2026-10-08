"""Read exact existing CharacterInfo pre/post receive targets without invocation."""
import argparse
import json
import struct
from pathlib import Path
from inspect_character_appearance import AppearanceProbe
from dump_runtime_reflection import Reader, ReadError
from protocol_proof import EXPECTED_EXE, client_proof, validate_current_client_proofs

def inspect(pid, source):
    saved=json.loads(Path(source).read_text())
    validate_current_client_proofs(pid,saved,saved)
    identity=saved['character_information']['identity']
    reader=Reader(pid,EXPECTED_EXE)
    try:
        probe=AppearanceProbe(reader)
        address=int(identity['address'],16)
        if probe.identity(address)!=identity or identity['name']!='BaseCharacterInfo' or identity['class']!='PlayerInfo':
            raise ReadError('Exact existing PlayerInfo component identity required')
        vt=reader.unpack(address,'<Q')[0]
        targets={}
        for offset in (0x2a8,0x2b0):
            target=reader.unpack(vt+offset,'<Q')[0]
            if not reader.base<=target<reader.base+reader.image_size:
                raise ReadError('Receive target outside exact image')
            targets[hex(offset)]={'rva':hex(target-reader.base),'bytes':reader.read(target,32).hex()}
            raw=reader.read(target,5)
            if raw[0]==0xe9:
                dest=target+5+struct.unpack_from('<i',raw,1)[0]
                if not reader.base<=dest<reader.base+reader.image_size:
                    raise ReadError('Receive thunk outside exact image')
                targets[hex(offset)]['jump_target_rva']=hex(dest-reader.base)
                targets[hex(offset)]['jump_target_bytes']=reader.read(dest,3).hex()
        return {'pid':pid,'client_proof':client_proof(pid),'functions_invoked':False,
            'component':identity,'virtual_targets':targets,'completed_client_proof':client_proof(pid)}
    finally:reader.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid',required=True,type=int)
    p.add_argument('--source',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    d=inspect(a.pid,a.source)
    a.output.write_text(json.dumps(d,indent=2),encoding='utf-8')
    print(json.dumps(d['virtual_targets']))
