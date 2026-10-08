"""Read-only diagnostics for the running, identity-checked local client."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from inspect_movement_prerequisites import MovementProbe
from dump_runtime_reflection import Reader
from protocol_proof import client_proof, EXPECTED_EXE

root = Path(__file__).resolve().parents[1]
snapshot = json.loads((root / 'data/client-inspection.json').read_text())
proof = client_proof(snapshot['pid'])
for key in ('pid', 'exe', 'sha256', 'process_created_filetime'):
    assert proof[key] == snapshot['client_proof'][key], key
r = Reader(snapshot['pid'], EXPECTED_EXE)
try:
    p = MovementProbe(r)
    actor = next(x['actor'] for x in snapshot['network_guid_actor_matches'] if x['actor']['class'] == 'PlayerPawn_C')
    pawn = int(actor['address'], 16)
    p.identity(pawn, 'PlayerCharacter')
    result = {'proof': proof, 'access': 'read-only', 'pawn': p.fields(pawn, ['CustomTimeDilation', 'PlayerState', 'CharacterInformationComponent', 'CharacterMovement', 'StatsComponent'])}
    components = result['pawn']
    controller=int(next(x['actor']['address'] for x in snapshot['network_guid_actor_matches'] if x['actor']['class']=='AoCPlayerControllerBP_C'),16)
    result['controller'] = p.fields(controller,['PlayerState','Pawn','AcknowledgedPawn'])
    for key, names in [('CharacterMovement', ['MaxSimulationTimeStep', 'MaxSimulationIterations', 'MinTimeBetweenTimeStampResets', 'MaxAcceleration', 'GroundFriction', 'BrakingDecelerationWalking', 'BrakingFrictionFactor', 'BrakingSubStepTime', 'GravityScale', 'JumpZVelocity', 'AirControl', 'bMovementTimeDiscrepancyDetection', 'bMovementTimeDiscrepancyResolution', 'MovementMode']), ('CharacterInformationComponent', ['CharacterName', 'CharacterGuid'])]:
        address = int(components[key]['value']['address'], 16)
        fields = p.fields(address, names)
        if key == 'CharacterInformationComponent':
            prop = fields['CharacterName']['metadata']
            assert prop['type'] == 'StrProperty' and prop['element_size'] == 16
            data, count, capacity = r.unpack(address + prop['offset_in_object'], '<Qii')
            assert 0 <= count <= capacity <= 256
            fields['CharacterName']['value'] = r.read(data, count * 2).decode('utf-16-le').rstrip('\0') if count else ''
        result[key] = fields
    level = int(actor['outer_address'], 16)
    prop = p.properties_for(level)['WorldSettings']
    settings = r.unpack(level + prop['offset_in_object'], '<Q')[0]
    result['world_settings'] = p.fields(settings, ['TimeDilation', 'MatineeTimeDilation', 'DemoPlayTimeDilation', 'MinGlobalTimeDilation', 'MaxGlobalTimeDilation'])
    result['time_global_multiplier'] = r.unpack(r.base + 0xd26eedc, '<f')[0]
    managers = []
    for address, obj in p.reflection.objects():
        if 'GameNetworkManager' in obj['name'] and obj['name'].startswith('Default__'):
            managers.append({'identity': p.identity(address), 'fields': p.fields(address, ['bMovementTimeDiscrepancyDetection', 'bMovementTimeDiscrepancyResolution', 'MovementTimeDiscrepancyMaxTimeMargin', 'MovementTimeDiscrepancyMinTimeMargin', 'MovementTimeDiscrepancyResolutionRate', 'MovementTimeDiscrepancyDriftAllowance', 'MaxMoveDeltaTime'])})
    result['network_managers'] = managers
    dest = root / 'runs/character-movement-followup-20261007/native-character.json'
    dest.write_text(json.dumps(result, indent=2))
    summary={key: ({name: field.get('value', field.get('status')) for name, field in value.items()} if isinstance(value, dict) else value) for key, value in result.items() if key not in ('proof', 'access','network_managers')}
    summary['network_managers']=[{'name':v['identity']['name'],'fields':{k:x.get('value',x.get('status')) for k,x in v['fields'].items()}} for v in managers]
    print(json.dumps(summary))
finally:
    r.close()
