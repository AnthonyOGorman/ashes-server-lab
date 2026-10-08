"""Extract original settlement channels from the complete offline capture; never replay."""
import collections,hashlib,json,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R.parent))
from tools.import_capture import iter_capture
from lab.unreal import decode_packet,DecodeError
from lab.world_bootstrap import decode_exports
capture=Path(json.loads((R.parent/'evidence/world_bootstrap_capture.json').read_bytes())['source_capture'])
counts=collections.Counter();channels={};all_bunches=[];exports=[]
for row in iter_capture(capture,None,()):
 if row['kind']!='game_96760c50' or row['source']['port']!=7436:continue
 counts['server_packets']+=1
 try:
  d=decode_packet(bytes.fromhex(row['hex']),'server')
  for b in d.get('bunches',[]):
   all_bunches.append({'frame':row['frame'],'bunch':b})
   if b.get('exports'):
    try:e=decode_exports(bytes.fromhex(b['payload_hex']),b['payload_bits'])
    except (DecodeError,ValueError,KeyError):counts['export_decode_errors']+=1;continue
    if any(o.get('path')=='Default__NodeLayoutReplicator' for o in e['objects']):
     exports.append({'frame':row['frame'],'channel':b['channel'],'exports':e})
     channels.setdefault(b['channel'],{'first_export_frame':row['frame'],'bunches':[]})
 except (DecodeError,ValueError,KeyError):counts['packet_decode_errors']+=1
for row in all_bunches:
 c=channels.get(row['bunch']['channel'])
 if c and row['frame']>=c['first_export_frame']:c['bunches'].append(row)
out={'capture':str(capture),'capture_sha256':hashlib.sha256(capture.read_bytes()).hexdigest(),
 'counts':dict(counts),'exports':exports,'channels':channels,'replayed':False,
 'limits':['Offline decoded bunch extraction; partial bunches need verified assembly/property grammar.',
 'Channel reuse after close must be considered; no property-handle inference from raw ID scanning.']}
(R/'proofs/settlement-full-capture-channels.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps({'counts':dict(counts),'exports':len(exports),'channels':{k:len(v['bunches']) for k,v in channels.items()}},indent=2))
