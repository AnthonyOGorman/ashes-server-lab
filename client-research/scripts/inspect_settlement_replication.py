"""Read an already received NodeLayoutReplicator and its initialized driver layout."""
import json,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R.parent/'tools'))
from inspect_movement_prerequisites import MovementProbe
from dump_runtime_reflection import Reader,pointer
from protocol_proof import client_proof,EXPECTED_EXE
s=json.loads((R.parent/'CPP/data/client-inspection.json').read_bytes());proof=client_proof(s['pid'])
for key in ('pid','exe','sha256','process_created_filetime'):assert proof[key]==s['client_proof'][key]
r=Reader(s['pid'],EXPECTED_EXE)
try:
 p=MovementProbe(r)
 def identity(address,expected=None):
  v=p.identity(address,expected);i=v['object_index'];assert 0<=i<p.reflection.count
  chunk=r.unpack(p.reflection.chunks+i//65536*8,'<Q')[0]
  actual,flags,cluster,serial=r.unpack(chunk+i%65536*24,'<Qiii')
  permanent=v['class']=='Class' and flags==0x42000000 and serial==0
  assert actual==address and (serial>0 or permanent)
  return {**v,'serial':serial,'gobject_flags':hex(flags)}
 rows=[x for x in s['network_guid_actor_matches'] if x['actor']['class']=='NodeLayoutReplicator'];assert len(rows)==1, len(rows)
 row=rows[0];actor=int(row['actor']['address'],16);ai=identity(actor,'NodeLayoutReplicator')
 assert (ai['object_index'],ai['serial'])==(row['weak_object_index'],row['weak_object_serial'])
 cls=identity(p.reflection.obj(actor)['class_address']);props=p.properties_for(actor)
 layout_prop=p.property(actor,'LayoutAssetSetGuids',0x370,0x190);node_prop=p.property(actor,'NodeGuid',0x500,8)
 assert layout_prop['type']=='StructProperty' and node_prop['type']=='Int64Property'
 ds=[x for x in s['net_drivers'] if x['guid_cache']==row['guid_cache']];assert len(ds)==1
 driver=int(ds[0]['address'],16);di=identity(driver,'NetDriver')
 entries,n,ncap=r.unpack(driver+0x5c0,'<Qii');assert 0<=n<=ncap<=8192 and (not n or pointer(entries))
 matches=[r.unpack(entries+i*32+8,'<Q')[0] for i in range(n)
  if r.unpack(entries+i*32,'<ii')==(cls['object_index'],cls['serial'])];assert len(matches)<=1
 manager,manager_shared=r.unpack(driver+0x210,'<QQ');assert pointer(manager) and pointer(manager_shared)
 cache_entries,cache_count,cache_cap=r.unpack(manager+8,'<Qii');assert pointer(cache_entries) and 0<cache_count<=cache_cap<=256
 caches=[r.unpack(cache_entries+i*24+8,'<Q')[0] for i in range(cache_count)
  if r.unpack(cache_entries+i*24,'<ii')==(cls['object_index'],cls['serial'])];assert len(caches)==1
 cache=caches[0];assert r.unpack(cache+0x10,'<ii')==(cls['object_index'],cls['serial'])
 fields,nf,cf=r.unpack(cache+0x20,'<Qii');assert pointer(fields) and 0<nf<=cf<=4096
 fieldbase=r.unpack(cache,'<i')[0];netcache={'address':hex(cache),'manager':hex(manager),
  'header_hex':r.read(cache,0x50).hex(),'fields_base':fieldbase,'field_count':nf,
  'field_maximum':fieldbase+nf+1,'fields':[]}
 for i in range(nf):
  raw=r.read(fields+i*24,24);addr,index,crc=r.unpack(fields+i*24,'<QiI')
  meta=next((x for x in props.values() if int(x['address'],16)==addr),None)
  assert meta and index==fieldbase+i and raw[16] in (0,1)
  netcache['fields'].append({'name':meta['name'],'property':meta,'field_net_index':index,
   'checksum':crc,'incompatible':bool(raw[16]),'raw':raw.hex()})
 info=None
 if matches:
  layout=matches[0];parents,np,cp=r.unpack(layout+0x28,'<Qii');cmds,nc,cc=r.unpack(layout+0x38,'<Qii')
  assert 0<np<=cp<=4096 and 0<nc<=cc<=32768
  info={'address':hex(layout),'header_hex':r.read(layout,0x80).hex(),'parents':[],'commands':[]}
  def property_metadata(address):
   known=next((x for x in props.values() if int(x['address'],16)==address),None)
   if known:return known
   if not address:return None
   assert pointer(address)
   # Read actual FProperty identity/type at command pointer; no declaration-order handle assumption.
   fields=p.reflection.properties(address);assert fields and int(fields[0]['address'],16)==address
   return fields[0]
  for i in range(np):
   raw=r.read(parents+i*48,48);a=int.from_bytes(raw[:8],'little')
   info['parents'].append({'index':i,'raw':raw.hex(),'property':property_metadata(a)})
  for i in range(nc):
   raw=r.read(cmds+i*32,32);a=int.from_bytes(raw[:8],'little')
   info['commands'].append({'index':i,'raw':raw.hex(),'property':property_metadata(a),
    'offset':int.from_bytes(raw[12:16],'little'),'end_cmd_candidate':int.from_bytes(raw[16:20],'little'),
    'handle_candidate':int.from_bytes(raw[20:22],'little'),'parent_index':int.from_bytes(raw[22:24],'little'),'type':raw[28]})
 data,count,cap=r.unpack(actor+0x478,'<Qii');assert 0<=count<=cap<=8192
 out={'proof':proof,'access':'read-only; no game calls/input/exports/process writes','actor':ai,
  'network_guid_match':row,'class':cls,'driver':di,'properties':list(props.values()),
  'node_guid':hex(r.unpack(actor+0x500,'<Q')[0]),'initialized':r.unpack(actor+0x508,'<B')[0],
  'items_count':count,'items_capacity':cap,'layout_struct_bytes':r.read(actor+0x370,0x190).hex(),
  'replicated_metadata':list(r.unpack(actor+0x488,'<BBB')),
  'cached_metadata':list(r.unpack(actor+0x50a,'<BBB')),
  'rep_layout_status':'present' if info else 'uninitialized','rep_layout':info,'class_net_cache':netcache,
  'limits':['Command handles/offsets are native snapshot metadata; wire grammar still requires validation.',
   'Zero NodeGuid/empty layout must not establish settlement level load/collision acceptance.']}
 end=client_proof(s['pid'])
 for key in ('pid','exe','sha256','process_created_filetime'):assert proof[key]==end[key]
 out['proof']=end;encoded=json.dumps(out,indent=2)
 (R/f'proofs/settlement-replication-live-{s["pid"]}-{end["process_created_filetime"]}.json').write_text(encoded,encoding='utf-8')
 (R/'proofs/settlement-replication-live.json').write_text(encoded,encoding='utf-8')
 print(json.dumps({k:out[k] for k in ('proof','actor','node_guid','initialized','items_count','replicated_metadata','rep_layout_status')},indent=2))
finally:r.close()
