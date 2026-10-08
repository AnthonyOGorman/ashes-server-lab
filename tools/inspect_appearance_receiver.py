"""Read actual appearance virtual targets; never invokes client functions."""
import argparse
import json
from pathlib import Path
from inspect_character_appearance import AppearanceProbe
from dump_runtime_reflection import Reader, ReadError
from protocol_proof import EXPECTED_EXE, client_proof, validate_current_client_proofs

def inspect(pid, source):
    saved = json.loads(Path(source).read_text())
    validate_current_client_proofs(pid, saved, saved)
    identity = saved['components']['CharacterAppearance']['identity']
    reader = Reader(pid, EXPECTED_EXE)
    try:
        probe = AppearanceProbe(reader)
        address = int(identity['address'],16)
        if probe.identity(address) != identity:
            raise ReadError('Appearance component identity changed')
        vt = reader.unpack(address,'<Q')[0]
        targets = {}
        for offset in (0x2a8,0x2b0,0x560,0x570,0x680,0x688,0x690):
            target = reader.unpack(vt+offset,'<Q')[0]
            if not reader.base <= target < reader.base+reader.image_size:
                raise ReadError('Appearance target outside exact image')
            targets[hex(offset)] = {'rva':hex(target-reader.base),'bytes':reader.read(target,32).hex()}
        table=reader.read(vt,0x700)
        import struct
        initialization_slots={hex(index*8):hex(value-reader.base) for index,(value,) in enumerate(struct.iter_unpack('<Q',table))
            if value-reader.base in (0x5fd8c80,0x5fd8f00,0x3dc4fe0)}
        # Exact native base initializer dispatches this FName and sets bit 0x20.
        # Reading the name identifies the lifecycle event without invoking it.
        event_index,event_number=reader.unpack(reader.base+0xd8336a8,'<II')
        lifecycle_event=probe.reflection.names.get(event_index,event_number)
        lifecycle_byte=reader.unpack(address+0xbe,'<B')[0]
        return {'pid':pid,'client_proof':client_proof(pid),'functions_invoked':False,
            'identity':identity,'virtual_targets':targets,'initialization_slots':initialization_slots,
            'base_initializer':{'rva':'0x3dc4fe0','event_name':lifecycle_event,
                'component_state_byte_offset':'0xbe','state_byte':lifecycle_byte,
                'bit_0x20_set':bool(lifecycle_byte & 0x20)}}
    finally:reader.close()

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid',required=True,type=int)
    p.add_argument('--source',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    report=inspect(a.pid,a.source)
    a.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report['virtual_targets']))
