"""Review saved loading/W certificate provenance; no live reads or input."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
certificate=R.parent/'client-testing/runs/postready-w-accepted-2af3d06b217849d0be9e8007b1f9d071.json'
raw=certificate.read_bytes();c=json.loads(raw)
assert c['status']=='postready_w_positive_control_accepted_native_and_server_trace'
sources=[dict(path=str(certificate),sha256=hashlib.sha256(raw).hexdigest())]
loaded={}
for source in c['source_evidence']:
    path=Path(source['path']);data=path.read_bytes()
    assert hashlib.sha256(data).hexdigest()==source['sha256']
    loaded[path.name]=json.loads(data);sources.append(source)
trace=loaded['loading-third-postready-w-trace.json']
assert trace['connection']['id']==c['connection']==c['server_trace']['connection_id']
assert trace['summary']==c['server_trace']
assert c['native_samples']==15 and c['floor_samples_read']==14 and c['floor_samples_unavailable']==1
assert c['all_samples_role_two'] and c['all_samples_walking_one'] and c['all_read_floor_samples_blocking_walkable_nonpenetrating']
assert c['counter_observations']==18 and c['all_native_counter_observations_zero']
assert c['controls_released']['active']==0 and c['controls_released']['held']==0 and c['lease_mode']=='observation'
assert c['server_trace']['new_moves']==113 and c['server_trace']['moving_new_moves']==28
assert c['server_trace']['responses']['ack']==113 and c['server_trace']['responses']['correction']==0 and c['server_trace']['resolution_moves']==0
assert 1200<c['native_displacement']['horizontal_cm']<1201 and c['server_trace']['max_prediction_error_cm']<0.27
assert c['post_walk_closure']['saved_joined_at']<c['post_walk_closure']['client_channel_zero_close_at_reported_by_server_owner']
assert c['desktop_cursor_preservation_certified'] is False
result=dict(status='saved_loading_positive_control_sources_verified',sources=sources,
    client_proof=c['client_proof'],connection=c['connection'],native_samples=15,read_floor_samples=14,unavailable_floor_samples=1,
    horizontal_cm=c['native_displacement']['horizontal_cm'],server_trace=c['server_trace'],controls_released=True,
    limits=['Saved certificate/hash/trace review only; no live inspection or input.',
        'One post-unlock W control, not proof of jitter-free movement, platform seam, jumping, sprint or persistent connectivity.',
        'Later lobby travel invalidates old world pawn; cause of travel and desktop cursor change remains undetermined.'])
(R/'proofs/loading-positive-control-review.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(status=result['status'],sources=len(sources),horizontal_cm=result['horizontal_cm'],max_prediction_error_cm=c['server_trace']['max_prediction_error_cm'])))
