"""Read exact accepted settlement actor, its items and matching streaming level; no game calls/input."""
import argparse,json,math,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R.parent/'tools'))
from inspect_movement_prerequisites import MovementProbe
from inspect_world_readiness import object_array
from dump_runtime_reflection import Reader,pointer
from protocol_proof import client_proof,EXPECTED_EXE
a=argparse.ArgumentParser();a.add_argument('--source',type=Path,default=R/'proofs/settlement-replication-live.json');args=a.parse_args()
s=json.loads(args.source.read_bytes());proof=client_proof(s['proof']['pid'])
for k in ('pid','exe','sha256','process_created_filetime'):assert proof[k]==s['proof'][k]
assert proof['sha256']==json.loads((R/'index/summary.json').read_bytes())['native']['sha256']
r=Reader(proof['pid'],EXPECTED_EXE,budget=64*1024*1024)
try:
 p=MovementProbe(r)
 def identity(address,expected=None):
  v=p.identity(address,expected);i=v['object_index'];assert 0<=i<p.reflection.count
  chunk=r.unpack(p.reflection.chunks+i//65536*8,'<Q')[0];actual,flags,cluster,serial=r.unpack(chunk+i%65536*24,'<Qiii')
  assert actual==address and serial>0 and not flags&0x10200000
  return {**v,'serial':serial,'flags':hex(flags)}
 actor=int(s['actor']['address'],16);ai=identity(actor,'NodeLayoutReplicator')
 assert (ai['object_index'],ai['serial'])==(s['network_guid_match']['weak_object_index'],s['network_guid_match']['weak_object_serial'])
 p.property(actor,'NodeGuid',0x500,8);p.property(actor,'LayoutAssetSetGuids',0x370,0x190)
 node=r.unpack(actor+0x500,'<Q')[0];data,count,cap=r.unpack(actor+0x478,'<Qii');assert 0<=count<=cap<=4096 and (not count or pointer(data))
 items=[]
 for i in range(count):
  at=data+i*0x90;rep_id,rep_key,most_recent=r.unpack(at,'<iii');owner,secondary,index,asset=r.unpack(at+0x10,'<QiiQ')
  quat=r.unpack(at+0x30,'<4d');translation=r.unpack(at+0x50,'<3d');scale=r.unpack(at+0x70,'<3d')
  assert all(math.isfinite(x) for x in (*quat,*translation,*scale))
  items.append({'replication_id':rep_id,'replication_key':rep_key,'most_recent_array_key':most_recent,
   'owner_guid':hex(owner),'owner_secondary_id':secondary,'owner_array_index':index,'assetset_record_guid':hex(asset),
   'quaternion':quat,'translation':translation,'scale':scale})
 level=identity(int(ai['outer_address'],16),'Level');world=p.fields(int(level['address'],16),['OwningWorld'])['OwningWorld']['value']
 wi=identity(int(world['address'],16),'World');assert wi['name']=='Verra_World_Master'
 streamed=object_array(p,int(wi['address'],16),'StreamingLevels');assert streamed['status']=='read'
 candidates=[];names=[]
 for obj in streamed['objects']:
  if obj is None:continue
  addr=int(obj['address'],16);fields=p.fields(addr,['PackageNameToLoad','LoadedLevel','bShouldBeLoaded','bShouldBeVisible','StreamingPriority'])
  package=fields.get('PackageNameToLoad',{}).get('value');props=p.properties_for(addr);soft=props.get('WorldAsset');path=None
  if soft and soft['type']=='SoftObjectProperty' and soft['element_size']==40:
   # Exact SDK TPersistentObjectPtr<FSoftObjectPath>: WeakPtr8, ObjectID+8; full property40.
   ni,nn,ai2,an=r.unpack(addr+soft['offset_in_object']+8,'<IIII')
   path={'package':p.reflection.names.get(ni,nn),'asset':p.reflection.names.get(ai2,an),
    'object_id_offset':8,'raw40':r.read(addr+soft['offset_in_object'],40).hex()}
  names.append({'identity':obj,'package_name_to_load':package,'world_asset':path})
  if 'Landscape_Flat_D_Master_01' not in str(package)+' '+str(path):continue
  ci=identity(addr,'LevelStreaming');tp=props.get('LevelTransform');assert tp and tp['type']=='StructProperty' and tp['referenced_type']=='Transform' and tp['element_size']==96
  at=addr+tp['offset_in_object'];transform={'quaternion':r.unpack(at,'<4d'),'translation':r.unpack(at+0x20,'<3d'),'scale':r.unpack(at+0x40,'<3d')}
  loaded=fields['LoadedLevel'].get('value');loaded_info=None
  if loaded:
   li=identity(int(loaded['address'],16),'Level');loaded_info={'identity':li,'fields':p.fields(int(li['address'],16),['bIsVisible','OwningWorld'])}
  candidates.append({'identity':ci,'fields':fields,'world_asset':path,'world_asset_metadata':soft,
   'level_transform_metadata':tp,'level_transform':transform,'loaded_level':loaded_info,
   'native_streaming_state_at_138':r.unpack(addr+0x138,'<B')[0]})
 end=client_proof(proof['pid'])
 for k in ('pid','exe','sha256','process_created_filetime'):assert proof[k]==end[k]
 assert identity(actor)['serial']==ai['serial'] and r.unpack(actor+0x478,'<Qii')==(data,count,cap)
 out={'proof':end,'access':'read-only; no calls/input/exports/process writes','accepted_guid':s['network_guid_match']['guid'],
  'actor':ai,'node_guid':hex(node),'initialized':r.unpack(actor+0x508,'<B')[0],
  'metadata':list(r.unpack(actor+0x488,'<BBB')),'cached_metadata':list(r.unpack(actor+0x50a,'<BBB')),
  'plot_change_version':r.unpack(actor+0x4b0,'<B')[0],'delta_flags':r.unpack(actor+0x470,'<B')[0],
  'items':items,'world':wi,'streaming_array_metadata':p.properties_for(int(wi['address'],16))['StreamingLevels'],
  'streaming_level_count':streamed['count'],'matching_streaming_levels':candidates,'streaming_names':names,
  'bytes_read':r.bytes_read,'limits':['Snapshot is not atomic; array address/count and object serial rechecked.',
   'Loaded/visible transformed level is not proof of capsule floor contact or successful server movement.']}
 stem=f'settlement-floor-observation-{proof["pid"]}-{proof["process_created_filetime"]}-{time.time_ns()}'
 (R/f'proofs/{stem}.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
 (R/'proofs/settlement-floor-observation.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
 print(json.dumps({k:out[k] for k in ('proof','node_guid','initialized','metadata','delta_flags','items','streaming_level_count','matching_streaming_levels','bytes_read')},indent=2))
finally:r.close()
