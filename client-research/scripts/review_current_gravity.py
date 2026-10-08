"""Review saved native gravity profile; no executable scan or live process access."""
import hashlib,json,math,struct
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sources=[]
def bind(path):
    data=path.read_bytes();sources.append(dict(path=str(path),sha256=hashlib.sha256(data).hexdigest()));return data
live=R/'proofs/jump-gravity-live-723352-134358967749612155-1791424144290339300.json';s=json.loads(bind(live))
assert s['client_proof']['pid']==723352 and s['client_proof']['process_created_filetime']==134358967749612155
sha=s['client_proof']['sha256'];assert sha==json.loads((R/'index/summary.json').read_bytes())['native']['sha256']
g=s['gravity_configuration'];assert g['record_id']=='0x636a8ad25678' and g['gravity_id']=='0x5429e5e8643f0018' and g['gravity_type']=='0x4a74ae5ed850dc97' and g['cached_type_byte']==0
assert len(g['stat_entries'])==1 and g['stat_entries'][0]['map']=='StatsInt32'
stat=g['stat_entries'][0];multiplier=struct.unpack_from('<f',bytes.fromhex(stat['raw']),12)[0];assert multiplier==stat['float_values'][1]==0.5
m=s['movement'];assert m['GravityScale']['value']==2.5 and m['JumpZVelocity']['value']==900
assert m['GravityDirection']['value']==[0,0,-1] and m['JumpZVelocity']['metadata']['offset_in_object']==0x1f8
defaults=s['physics_defaults'];assert defaults['class_identity']['name']=='PhysicsSettings' and defaults['cdo_identity']['name']=='Default__PhysicsSettings'
base=defaults['fields']['DefaultGravityZ']['value'];assert base==-980 and defaults['fields']['DefaultGravityZ']['metadata']['offset_in_object']==0x58
ws=s['world_settings'];assert ws['get_gravity_slot840_rva']=='0x47bad50' and ws['fields']['bGlobalGravitySet']['raw_byte']&3==0
assert ws['fields']['WorldGravityZ']['value']==base
volume=s['physics_volume'];assert volume['get_gravity_slot840_rva']=='0x441e300' and volume['source'].startswith('RootComponent.PhysicsVolume')
assert m['UpdatedComponent']['value']['address']==m['UpdatedPrimitive']['value']['address']
root=next(i for i in s['identities'] if i['address']==m['UpdatedComponent']['value']['address']);assert 'CapsuleComponent' in root['ancestors']
assert s['physics_volume_getter']['target_rva']=='0x3e46dd0'
assert s['animation']['count']==0 and s['slow_fall_fields']['bIsSlowFalling']['value'] is False
assert s['slow_fall_fields']['bIsSlowFalling']['metadata']['offset_in_object']==0x844
assert s['slow_fall_fields']['native_leaf']['bytes']=='0fb68144080000c3'
for slot,target in [('0x560','0x5ea4b00'),('0x770','0x5ea1480'),('0xcf0','0x6b411a0'),('0xcf8','0x6b4d430')]:assert next(b for b in s['bindings'] if b['slot']==slot)['target_rva']==target
for rel in ['loading-restart-reset/function_5ea4b00.c','jump-gravity-getters/function_3ddfcb0.c','jump-gravity-getters/function_6b411a0.c','jump-gravity-final-getters/function_3e43260.c','jump-gravity-final-getters/function_60accf0.c','falling-gravity-parity/function_441e300.c','falling-gravity-parity/function_60f2950.c','falling-gravity-parity/function_61286d0.c','falling-gravity-parity/function_5eb6250.c']:
    text=bind(R/'decompiled'/rel).decode();assert sha in text and 'Decompilation failed:' not in text
manifest=json.loads(bind(R/'proofs/falling-gravity-parity-targets.json'));assert manifest['exe_sha256']==sha and not manifest['missing']
fragments=0
for t in manifest['targets']:
    for rel in t['snapshots']:
        p=R/rel;f=json.loads(bind(p));raw=bind(p.with_suffix('.bin'));assert f['exe_sha256']==sha and hashlib.sha256(raw).hexdigest()==f['fragment_sha256'];fragments+=1
effective=base*m['GravityScale']['value']*multiplier;assert effective==-1225
definition=json.loads(bind(R/'proofs/gravity-definition-live-723352-134358967749612155-1791424907151261000.json'))
for k in ['pid','sha256','process_created_filetime']:assert definition['client_proof'][k]==s['client_proof'][k]
dd=definition['definition'];assert dd['record_id']==g['gravity_id'] and dd['type_id']==g['gravity_type'] and dd['stat_type']==0
assert dd['replication']==7 and dd['base_equipment_buckets']==0 and dd['raw246_248']=='0700' and definition['profile']['cached_definition_agrees']
air_manifest=json.loads(bind(R/'proofs/falling-air-control-targets.json'));assert air_manifest['exe_sha256']==sha
assert set(air_manifest['missing'])=={'0x3de2380','0x5ea51d0'}
air_fragments=0
for t in air_manifest['targets']:
    output=bind(R/'decompiled/falling-air-control'/('function_'+t['rva'][2:]+'.c')).decode();assert sha in output and 'Decompilation failed:' not in output
    for rel in t['snapshots']:
        p=R/rel;f=json.loads(bind(p));raw=bind(p.with_suffix('.bin'));assert f['exe_sha256']==sha and hashlib.sha256(raw).hexdigest()==f['fragment_sha256'];air_fragments+=1
assert len(air_manifest['targets'])==4 and air_fragments==11
coefficient=json.loads(bind(R/'proofs/falling-air-coefficient-targets.json'));assert coefficient['exe_sha256']==sha and not coefficient['missing'] and len(coefficient['targets'])==1
ct=coefficient['targets'][0];assert ct['rva']=='0x3ddc2f0'
for rel in ct['snapshots']:
    p=R/rel;f=json.loads(bind(p));raw=bind(p.with_suffix('.bin'));assert f['exe_sha256']==sha and hashlib.sha256(raw).hexdigest()==f['fragment_sha256']
assert sha in bind(R/'decompiled/falling-air-coefficient/function_3ddc2f0.c').decode()
leaves=json.loads(bind(R/'proofs/falling-helper-leaves.json'));assert leaves['exe_sha256']==sha
for prefix in leaves['prefixes']:
    stem='falling-helper-prefix-'+prefix['rva'][2:];f=json.loads(bind(R/'proofs'/(stem+'.json')));raw=bind(R/'proofs'/(stem+'.bin'));assert f['exe_sha256']==sha and hashlib.sha256(raw).hexdigest()==f['fragment_sha256']==prefix['fragment_sha256']
assert leaves['braking_switch']['falling_field_offset']=='0x2f4' and leaves['braking_switch']['mode_targets']['3']=='0x5ea51f9'
assert m['BrakingDecelerationFalling']['metadata']['offset_in_object']==0x2f4
out=dict(status='saved_current_gravity_profile_and_native_sources_verified',client_proof=s['client_proof'],sources=sources,saved_exception_fragments=fragments,
    gravity_definition=dict(replication=7,base_equipment_buckets=0,raw246_248='0700',limits='Definition/cache receipt only; does not revalidate expired world pawn after lobby travel'),
    falling_helpers=dict(outputs=5,exception_fragments=air_fragments+len(ct['snapshots']),selected_discovery_prefixes=3,unresolved_root_ranges=air_manifest['missing'],terminal_clamp='Along normalized gravity only, preserving perpendicular velocity',air_control='Slot888 GetAirControl delegates nonzero coefficient to slot898 boost helper, then scales lateral acceleration; slot898 implementation unresolved',apex_enable='On-disk default1 only; runtime not read'),
    gravity=dict(base_cm_s2=base,movement_scale=2.5,character_multiplier=multiplier,animation_entries=0,slow_fall=False,effective_cm_s2=effective,
        evidence='Native getter/config-derived ordinary current-profile value; no native getter invocation or falling trajectory measurement'),
    jump=dict(velocity_cm_s=900,max_hold_s=s['pawn']['JumpMaxHoldTime']['value'],max_count=s['pawn']['JumpMaxCount']['value']),
    terminal_velocity_cm_s=volume['fields']['TerminalVelocity']['value'],
    falling_profile={k:m[k]['value'] for k in ['AirControl','AirControlBoostMultiplier','AirControlBoostVelocityThreshold','FallingLateralFriction','BrakingDecelerationFalling','BrakingFrictionFactor','MaxSimulationTimeStep','MaxSimulationIterations','MaxJumpApexAttemptsPerSimulation']},
    minimal_recommendation=['Keep jump900; constructor600 is overridden on this current pawn.', 'Synchronize server gravity to the same validated base/movement/stat profile; current ordinary derived value-1225.', 'Corroborate baseline/changed ascent/apex/descent/landing against native samples and server corrections.', 'Apply native falling lateral air-control/braking and apex/landing rules separately; gravity parity does not prove slope parity.'],
    limits=['Saved proof review only; no executable scan or live process access in this review.', 'Captured native ranges were build-hash checked by target-preparation scripts; this review rechecks saved fragment consistency.', 'SceneComponent volume tail and general WorldSettings dependencies are separate call-chain leads; sampled volume/world/settings associations are preserved.', 'Future stat/animation/slow-fall/volume changes and process lifetimes require fresh binding.'])
(R/'proofs/current-jump-gravity-review.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:out[k] for k in ['status','gravity','jump','saved_exception_fragments']},indent=2))
