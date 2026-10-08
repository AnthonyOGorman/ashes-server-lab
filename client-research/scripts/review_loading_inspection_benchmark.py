"""Preserve same-lifetime inspector A/B evidence without invoking the server."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1];B=R.parent/'CPP/runs/loading-readiness-20261008'
names=['inspection-original-live.json','inspection-optimized-release-live.json',
       'inspection-comparison.json','inspection-comparison-timing.json','inspection-optimized-release-timing.json']
sources=[];ds={}
for name in names:
    p=B/name;raw=p.read_bytes();sha=hashlib.sha256(raw).hexdigest();ds[name]=json.loads(raw)
    dest=R/f'proofs/inspection-benchmark-source-{Path(name).stem}-{sha[:16]}.json';dest.write_bytes(raw)
    sources.append(dict(path=str(p),sha256=sha,preserved_path=str(dest)))
old=ds[names[0]];new=ds[names[1]]
for k in ['pid','process_created_filetime','exe','sha256']:assert old['client_proof'][k]==new['client_proof'][k]
assert old['network_guid_actor_matches']==new['network_guid_actor_matches']
assert not old['errors'] and not new['errors']
old_players=[p for p in old['pawns'] if p['class']=='PlayerPawn_C'];assert len(old_players)==len(new['pawns'])==1
for k in ['address','object_index','serial']:assert old_players[0][k]==new['pawns'][0][k]
ms_old=ds[names[3]]['old_release_ms'];ms_new=ds[names[4]]['optimized_release_ms']
out=dict(status='same_lifetime_inspector_benchmark_reviewed',sources=sources,client_proof=new['client_proof'],
    original_release_ms=ms_old,optimized_release_ms=ms_new,ratio=ms_old/ms_new,reduction_percent=(1-ms_new/ms_old)*100,
    excluded_old_pawns=[{k:p[k] for k in ['name','class','object_index','serial']} for p in old['pawns'] if p['class']!='PlayerPawn_C'],
    accepted_guids_equal=True,owned_pawn_identity_equal=True,
    limits=['Single same-idle-lifetime sequential A/B; not fresh-login readiness or broad performance statistics.',
      'Optimized Debug timing is separate and not used to claim Release improvement.',
      'Original broadly classified an unrelated zero-serial Arcana actor as Pawn; stage-owned PlayerPawn identity is equal.',
      'No runtime calls, inputs, process reads, server source changes or service actions.'])
(R/'proofs/loading-inspection-benchmark-review.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:out[k] for k in ['status','original_release_ms','optimized_release_ms','ratio','reduction_percent']},indent=2))
