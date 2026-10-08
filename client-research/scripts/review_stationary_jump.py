"""Join immutable stationary-jump/native review and CPP trace, with sampling limits."""
import argparse,hashlib,json,math,statistics
from pathlib import Path
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--native-review',type=Path,required=True);p.add_argument('--trace',type=Path,required=True)
p.add_argument('--output',type=Path,required=True);a=p.parse_args();sources=[]
def read(path):
    raw=path.read_bytes();sources.append(dict(path=str(path.resolve()),sha256=hashlib.sha256(raw).hexdigest()));return json.loads(raw)
n=read(a.native_review);j=read(Path(n['source']));assert sources[-1]['sha256']==n['source_sha256']
t=read(a.trace);assert n['connection']==j['connection']==t['connection']['id']==t['summary']['connection_id']
assert n['client_proof']['pid']==j['client_proof']['pid'] and n['client_proof']['process_created_filetime']==j['client_proof']['process_created_filetime']
assert len(j['samples'])==n['native_samples'] and n['native_falling_samples']>0
air=[s['native'] for s in j['samples'] if s['native']['movement']['MovementMode']==3]
assert len(air)==n['native_falling_samples']
initial=n.get('native_initial_position',j['before']['position_cm']);landed=n.get('native_landed_position',n['native_final']['position_cm'])
intervals=n.get('sample_interval_seconds_range',n.get('sampling_interval_range'));assert intervals and intervals[0]>0
max_sampled=max(s['native']['position_cm'][2]-initial[2] for s in j['samples'])
assert math.isclose(max_sampled,n['observed_apex']['rise_cm'],abs_tol=1e-7)
assert n['controls_released']['active']==j['released']['active']==0 and n['controls_released']['held']==j['released']['held']==0
assert len(j['key_edges'])==2 and j['key_edges'][0]['vk']==32 and j['key_edges'][0]['down'] and not j['key_edges'][1]['down']
assert 0<n['acknowledged_hold_seconds']<=.15
assert n['native_final']['pawn_state']['Role']==2 and n['native_final']['movement']['MovementMode']==1
assert j['final_counter']['counter']==0 and j['final_counter']['controller']['serial']==n['native_final']['controller']['serial']
assert n['native_final']['movement']['Velocity']==[0,0,0]
floor=n['native_final']['floor'];assert floor['status']=='read' and floor['fields']['bBlockingHit'] and floor['fields']['bWalkableFloor'] and not floor['hit']['bStartPenetrating']
new=[m for m in t['moves'] if m.get('kind')=='new'];assert len(new)==t['summary']['new_moves']
responses={k:sum(m.get('response')==k for m in new) for k in ['ack','correction','deferred']};assert responses==t['summary']['responses']
gravity=[]
for m in t['moves']:
    dt=m.get('simulation_dt',0)
    if m.get('kind')=='new' and dt>0 and m.get('movement_mode')==3 and not m.get('jump_started') and m.get('collision_hits')==[]:
        gravity.append(dict(move_id=m['id'],derived_acceleration_cm_s2=(m['server_velocity'][2]-m['velocity_before'][2])/dt))
assert gravity
assert max(m['prediction_error_cm'] for m in new)==t['summary']['max_prediction_error_cm']
result=dict(status='saved_stationary_jump_sources_and_runtime_trace_reviewed',sources=sources,
    client_proof=n['client_proof'],backend_proof=n['backend_proof'],backend_sha256=n['backend_sha256'],connection=n['connection'],
    native_samples=n['native_samples'],native_falling_samples=n['native_falling_samples'],acknowledged_hold_seconds=n['acknowledged_hold_seconds'],
    sampled_apex=n['observed_apex'],sample_interval_seconds_range=intervals,
    first_falling_at=min(s['observed_at'] for s in air),first_landed_after_air_at=n.get('first_landed_sample_after_air'),
    landed_position_delta_cm=[b-a for a,b in zip(initial,landed)],
    server_summary=t['summary'],server_gravity_from_unobstructed_steps=gravity,
    median_server_gravity_cm_s2=statistics.median(x['derived_acceleration_cm_s2'] for x in gravity),controls_released=True,
    limits=['Saved-only review, no live process access/input.', 'Sampled rise is not exact continuous apex; corrections alter the native trajectory.',
        'Native/client HTTP samples are non-atomic; server gravity is derived separately from unobstructed server move rows.',
        'One stationary jump on this route; no moving-jump, slopes, long fall, sprint or settlement-transition acceptance.'])
a.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ['status','native_samples','sampled_apex','server_summary','median_server_gravity_cm_s2']},indent=2))
