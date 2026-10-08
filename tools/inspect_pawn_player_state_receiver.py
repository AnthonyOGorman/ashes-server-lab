"""Read-only serializer and exact notification targets for the accepted pawn."""
import argparse
import json
from pathlib import Path
from inspect_character_appearance import AppearanceProbe
from dump_runtime_reflection import Reader, ReadError
from protocol_proof import EXPECTED_EXE, client_proof, validate_current_client_proofs

def inspect(pid, source):
    actors = json.loads(Path(source).read_text())
    validate_current_client_proofs(pid, actors, actors)
    matches = actors['network_guid_actor_matches']
    pawn = next(m for m in matches if m['actor']['class'] == 'PlayerPawn_C')
    ps = next(m for m in matches if m['actor']['class'] == 'AoCPlayerStateBP_C')
    reader = Reader(pid, EXPECTED_EXE)
    try:
        probe = AppearanceProbe(reader)
        address = int(pawn['actor']['address'], 16)
        if probe.identity(address)['object_index'] != pawn['actor']['object_index']:
            raise ReadError('Accepted pawn identity changed')
        if probe.identity(int(ps['actor']['address'], 16))['object_index'] != ps['actor']['object_index']:
            raise ReadError('Accepted PlayerState identity changed')
        vt = reader.unpack(address, '<Q')[0]
        prop = probe.properties_for(address)['PlayerState']
        pvt = reader.unpack(int(prop['address'], 16), '<Q')[0]
        return {'pid': pid, 'client_proof': client_proof(pid), 'functions_invoked': False,
            'actor_address': pawn['actor']['address'], 'player_state_address': ps['actor']['address'],
            'pawn_guid': pawn['guid'], 'player_state_guid': ps['guid'], 'property': prop,
            'notify_rva': hex(reader.unpack(vt+0x870, '<Q')[0]-reader.base),
            'changed_callback_rva': hex(reader.unpack(vt+0x830, '<Q')[0]-reader.base),
            'notify_bytes': reader.read(reader.base+0x433c720, 12).hex(),
            'changed_callback_bytes': reader.read(reader.base+0x131c2f0, 3).hex(),
            'net_serialize_rva': hex(reader.unpack(pvt+0xc8, '<Q')[0]-reader.base),
            'completed_client_proof': client_proof(pid)}
    finally:
        reader.close()

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid', type=int, required=True)
    p.add_argument('--actors', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    report = inspect(a.pid, a.actors)
    a.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k.endswith('_rva')}))
