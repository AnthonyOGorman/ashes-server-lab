"""Read-only current physics-volume and falling settings, bound to the accepted client lifetime."""
import json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root.parent/'tools'))
from inspect_movement_prerequisites import MovementProbe
from dump_runtime_reflection import Reader
from protocol_proof import client_proof,EXPECTED_EXE
snapshot=json.loads((root/'data/client-inspection.json').read_text());proof=client_proof(snapshot['pid'])
for key in ('pid','exe','sha256','process_created_filetime'):assert proof[key]==snapshot['client_proof'][key]
r=Reader(snapshot['pid'],EXPECTED_EXE)
try:
    p=MovementProbe(r)
    pawn=int(next(row['actor']['address'] for row in snapshot['network_guid_actor_matches'] if row['actor']['class']=='PlayerPawn_C'),16)
    components=p.fields(pawn,['CapsuleComponent','CharacterMovement'])
    capsule=int(components['CapsuleComponent']['value']['address'],16)
    movement=int(components['CharacterMovement']['value']['address'],16)
    prop=p.properties_for(capsule)['PhysicsVolume'];assert prop['type']=='WeakObjectProperty'
    index,serial=r.unpack(capsule+prop['offset_in_object'],'<ii');assert index>=0 and serial>0
    chunk=r.unpack(p.reflection.chunks+(index//65536)*8,'<Q')[0]
    volume=r.unpack(chunk+(index%65536)*24,'<Q')[0]
    assert r.unpack(chunk+(index%65536)*24+16,'<i')[0]==serial
    identity=p.identity(volume,'PhysicsVolume');assert identity['object_index']==index
    result={'proof':proof,'functions_invoked':False,'volume':identity,'volume_fields':p.fields(volume,['TerminalVelocity','FluidFriction']),
            'movement_fields':p.fields(movement,['BrakingDecelerationFalling','FallingLateralFriction','AirControl','AirControlBoostMultiplier','AirControlBoostVelocityThreshold'])}
    (root/'runs/character-movement-followup-20261007/native-falling.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({section:{name:field.get('value',field.get('status')) for name,field in result[section].items()} for section in ('volume_fields','movement_fields')}))
finally:r.close()
