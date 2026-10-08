"""Independently join saved client contact and CPP trace windows for Winstead."""
import hashlib, json
from pathlib import Path
R = Path(__file__).resolve().parents[1]
ROOT = R.parent
proof = R / 'proofs/settlement-floor-observation-115896-134358667522731418-1791393516491248000.json'
observed = json.loads(proof.read_bytes())
level = observed['matching_streaming_levels'][0]['loaded_level']['identity']
assert observed['matching_streaming_levels'][0]['loaded_level']['fields']['bIsVisible']['value']
paths = []
results = []
for ordinal, token in enumerate(('083c6ff6b8fb4b82ac174695d74153c9',
        'beefbe55dd964580b893339dade32dc4', '53b2e045d4aa4a34a6d65cb05e081dd3'), 1):
    p = ROOT / f'client-testing/runs/traversal-{token}.json'
    t = ROOT / f'CPP/runs/character-movement-followup-20261007/winstead-floor-pulse{ordinal}-window.json'
    paths.extend((p, t))
    client, trace = (json.loads(x.read_bytes()) for x in (p, t))
    end = client['final_native']
    lifetime = end['client_proof']
    assert lifetime['pid'] == 115896 and lifetime['process_created_filetime'] == 134358667522731418
    assert lifetime['sha256'] == observed['proof']['sha256']
    assert client['released']['active'] == client['released']['held'] == 0
    assert client['key'] == 'w' and client['duration'] == 2.0
    assert all(x['movement']['MovementMode'] == 1 for x in client['samples'])
    assert end['movement']['MovementMode'] == 1
    assert end['movement']['Velocity'] == end['movement']['Acceleration'] == [0., 0., 0.]
    floor = end['floor']
    assert floor['fields']['bBlockingHit'] and floor['fields']['bWalkableFloor']
    assert floor['hit']['bBlockingHit'] and not floor['hit']['bStartPenetrating']
    if ordinal >= 2:
        linked = next(x for x in floor['outer_chain'] if x['class'] == 'Level')
        assert all(linked[k] == level[k] for k in ('address', 'object_index', 'serial'))
        assert floor['outer_chain'][-1]['name'].startswith('/Game/ENV/Nodes/Nodes_Master/Node_Sublevels/Landscape_Platforms/Layout_Flat_D/Landscape_Flat_D_Master_01_')
    summary = trace['summary']
    assert summary['connection_id'] == '932b04cfcb0bb267473947c3'
    new = [x for x in trace['moves'] if x['kind'] == 'new']
    assert len(new) == summary['new_moves']
    assert all(x['response'] == 'ack' and not x['time_resolution_active'] for x in new)
    maximum = max(x['prediction_error_cm'] for x in new)
    assert abs(maximum-summary['max_prediction_error_cm']) < 1e-9
    player = next(x for x in client['final_world']['server']['data']['players'] if x['id'] == summary['connection_id'])
    assert player['grounded'] and player['tiles'] == 2925
    delta = [a-b for a, b in zip(end['position_cm'], player['position'])]
    assert max(abs(x) for x in delta) < 0.3
    results.append({'pulse': ordinal, 'native_samples': len(client['samples']),
        'horizontal_cm': client['comparison']['horizontal_cm'], 'endpoint_cm': end['position_cm'],
        'native_floor_component': floor['component'], 'native_floor_package': floor['outer_chain'][-1]['name'],
        'native_floor_distance_cm': floor['fields']['FloorDist'],
        'new_ack': len(new), 'corrections': 0, 'max_prediction_error_cm': maximum,
        'endpoint_client_minus_server_cm': delta, 'key_edges': client['key_edges']})
assert results[1]['endpoint_cm'][0] < -677940 < results[2]['endpoint_cm'][0]
out = {'status': 'bounded_winstead_seam_accepted',
    'sources': [{'path': str(x), 'sha256': hashlib.sha256(x.read_bytes()).hexdigest()} for x in [proof, *paths]],
    'client_lifetime': lifetime, 'pulses': results,
    'total_native_grounded_samples': sum(x['native_samples'] for x in results),
    'total_new_ack': sum(x['new_ack'] for x in results),
    'total_horizontal_cm': sum(x['horizontal_cm'] for x in results),
    'max_prediction_error_cm': max(x['max_prediction_error_cm'] for x in results),
    'limits': ['Three bounded W-only pulses on one accepted client lifetime and route.',
        'Read-only native snapshots are not atomic and do not prove every unsampled instant.',
        'No all-locations, buildings, sprint, reverse walking or complete movement parity claim.',
        'Does not prove automatic setup on later login; CPP owns that implementation and fresh-lifetime test.']}
(R/'proofs/settlement-traversal-review.json').write_text(json.dumps(out, indent=2)+'\n', encoding='utf-8')
print(json.dumps({k:out[k] for k in ('status','total_native_grounded_samples','total_new_ack','total_horizontal_cm','max_prediction_error_cm')}))
