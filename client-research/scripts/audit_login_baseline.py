"""Preserve historical automatic-login events and audit elapsed gaps, offline only."""
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
R = Path(__file__).resolve().parents[1]
p = R.parent / 'CPP/runs/settlement-probe-20261008/automatic-world-verification.json'
raw = p.read_bytes()
d = json.loads(raw)
digest = hashlib.sha256(raw).hexdigest()
archived = R / f'proofs/login-readiness-baseline-source-{digest[:16]}.json'
if archived.exists():
    assert archived.read_bytes() == raw
else:
    archived.write_bytes(raw)
events = sorted(({'event': k, 'observed_at': v['observed_at']} for k, v in d['events'].items()),
                key=lambda x: x['observed_at'])
for a, b in zip(events, events[1:]):
    b['seconds_since_previous_event'] = b['observed_at'] - a['observed_at']
times = {x['event']: x['observed_at'] for x in events}
intervals = {}
for a, b in [('character_name_verified', 'world_initialized'),
             ('settlement_metadata_probe_authored', 'winstead_floor_authored'),
             ('winstead_floor_authored', 'winstead_collision_admitted')]:
    if a in times and b in times:
        intervals[f'{a}_to_{b}_s'] = times[b]-times[a]
source_hashes = {}
for name in ('initialization.cpp','settlement_collision.cpp','inspection.cpp','speed_sync.cpp'):
    source = R.parent / 'CPP/src' / name
    source_raw = source.read_bytes()
    sha = hashlib.sha256(source_raw).hexdigest()
    source_hashes[name] = {'sha256': sha,
        'matches_historical_verification': d['source_sha256'].get('src\\'+name) == sha,
        'verification_has_hash': 'src\\'+name in d['source_sha256']}
    saved = R/f'proofs/login-readiness-source-{name}-{sha[:16]}.txt'
    if saved.exists():
        assert saved.read_bytes() == source_raw
    else:
        saved.write_bytes(source_raw)
out = {'audited_at': datetime.now(timezone.utc).isoformat(),
    'source': {'path': str(p), 'sha256': digest, 'immutable_copy': str(archived)},
    'historical_client_proof': d['client_proof'], 'historical_connection_id': d['connection_id'],
    'release_sha256': d['release_sha256'], 'events': events, 'intervals': intervals,
    'source_snapshots': source_hashes,
    'limits': ['Historical recorded event intervals, not full login/Play-to-ready timing.',
        'Time between authored probe and floor includes prerequisites, inspections and scheduler time; not solely asset IO.',
        'Source may have changed while CPP owner works; match booleans distinguish historical and current snapshots.',
        'No live client reads, input, server changes or database scans.']}
(R/'proofs/login-readiness-baseline.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'intervals': intervals, 'source_snapshots': source_hashes},indent=2))
