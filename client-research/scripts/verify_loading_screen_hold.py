"""Verify saved loading decompilation bytes, record identity and separate UI endpoints."""
import datetime,hashlib,json,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'vendor'))
import pefile
m=json.loads((R/'index/summary.json').read_bytes())['native'];raw=Path(m['path']).read_bytes()
assert hashlib.sha256(raw).hexdigest()==m['sha256'];pe=pefile.PE(data=raw,fast_load=True)
sources=[];fragments=0;outputs=0
def bind(p):
    sources.append(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    return p
for batch in ['loading-screen-hold','loading-screen-config','loading-screen-state','loading-screen-show-hide']:
    manifest=json.loads(bind(R/f'proofs/{batch}-targets.json').read_bytes());assert manifest['exe_sha256']==m['sha256'] and not manifest['missing']
    for t in manifest['targets']:
        p=bind(R/f'decompiled/{batch}/function_{int(t["rva"],16):x}.c');s=p.read_text()
        assert m['sha256'] in s and 'Decompilation failed:' not in s;outputs+=1
        for rel in t['snapshots']:
            f=json.loads(bind(R/rel).read_bytes());assert f['exe_sha256']==m['sha256']
            dat=pe.get_data(int(f['rva'],16),f['bytes']);assert hashlib.sha256(dat).hexdigest()==f['fragment_sha256'];fragments+=1
live=json.loads(bind(R/'proofs/loading-hold-live-579760-134358951827478205-1791422307694740200.json').read_bytes())
assert live['proof']['sha256']==m['sha256'] and live['settings_class']['name']=='AoCRecordConstants'
assert live['selected_loading_record']['record_id']=='0x5429e6b0c6c00000' and live['selected_loading_record']['hold_seconds']==22
assert len(live['loaded_alternatives'])==1
timing=json.loads(bind(R.parent/'CPP/runs/loading-readiness-20261008/native-readiness-second.json').read_bytes())
stages={s['stage']:s for s in timing['stages']};native=stages['WorldReady']['ts']
assert stages['NativeMovementReady']['ts']<stages['LoadingInputRelease']['ts']<native
play=1791421711.4448907
original_log=R.parent/'CPP/runs/1be8151402a6ff76/game.log';log_bytes=original_log.read_bytes();log_hash=hashlib.sha256(log_bytes).hexdigest()
log=R/f'proofs/loading-screen-game-log-{log_hash}.jsonl'
if not log.exists():log.write_bytes(log_bytes)
assert log.read_bytes()==log_bytes;bind(log);events=[];malformed=[]
for number,line in enumerate(log_bytes.decode('utf-8-sig').splitlines(),1):
    if not line.strip():continue
    try:e=json.loads(line)
    except json.JSONDecodeError:
        assert 'LogLoadingScreen' not in line
        malformed.append(number);continue
    if e.get('category')!='LogLoadingScreen':continue
    stamp=datetime.datetime.fromisoformat(e['timestamp'].replace('Z','+00:00')).timestamp()
    if stamp<play:continue
    if any(s in e.get('message','') for s in ['Holding loading screen','HideLoadingScreen','Visible for','LoadingScreen: Created','bCurrentlyInLoadMap','World Partition']):
        events.append(dict(ts=stamp,**e))
hide=next(e for e in events if e['message']=='HideLoadingScreen while IsShowingInitialLoadingScreen is false.')
visible=next(e for e in events if e['message'].startswith('Visible for') and e['ts']>=hide['ts'])
assert hide['ts']>native and visible['ts']>=hide['ts']
out=dict(status='static_loading_hold_and_saved_second_trial_endpoints_verified',exe_sha256=m['sha256'],sources=sources,
    decompiled_outputs=outputs,exception_fragments=fragments,client_lifetime=live['proof'],
    record=live['selected_loading_record'],selected_available_records=live['loaded_alternatives'],
    showing_byte='manager+0xE9 (not0xEA)',widget_pointer='manager+0x70',hold_timer_start='manager+0x130 double QPC seconds',
    native=dict(bootstrap_ts=stages['bootstrap_authored']['ts'],world_ready_ts=native,
        bootstrap_to_world_ready_s=stages['WorldReady']['elapsed_s'],bootstrap_to_world_initialized_s=timing['recorded_initialization_s']),
    log_snapshot=dict(original_path=str(original_log),immutable_path=str(log),sha256=log_hash,malformed_non_loading_lines=malformed),
    presentation=dict(play_request_ts=play,hide_logged_ts=hide['ts'],post_hide_visible_logged_ts=visible['ts'],
        play_to_post_hide_s=visible['ts']-play,native_world_ready_to_post_hide_s=visible['ts']-native),events=events,
    limits=['Saved second-trial endpoints; not third-trial/UI-gated acceptance.',
      'Client hold timer can overlap server initialization; do not add22s to every native interval.',
      'VisibleFor log lies after hideGC/widget removal/visibility broadcast/E9clear in reviewed normal path; initial movie-player hold returns earlier.',
      'LoadingScreenHoldSeconds Edit-only; no supported timerINI/CVar/record override established.',
      'Static/current-record proof does not authorize invalidating real native loading prerequisites.'])
(R/'proofs/loading-screen-hold-review.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:out[k] for k in ['status','decompiled_outputs','exception_fragments','native','presentation']},indent=2));pe.close()
