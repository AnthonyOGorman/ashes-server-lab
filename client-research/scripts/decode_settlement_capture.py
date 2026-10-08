"""Offline, bounded Winstead settlement traversal; never constructs or replays packets."""
import hashlib,json,math,struct,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R.parent))
from lab.unreal import BitReader,BitWriter
from lab.world_bootstrap import decode_actor_location

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
source=R/'proofs/settlement-full-capture-channels.json'
s=json.loads(source.read_bytes());assert sha(Path(s['capture']))==s['capture_sha256']
selected=[x for x in s['channels']['29']['bunches'] if 3876<=x['frame']<=3883]
assert len(selected)==8 and [x['frame'] for x in selected]==list(range(3876,3884))
w=BitWriter()
for i,x in enumerate(selected):
 b=x['bunch'];assert b['reliable'] and b['partial'] and not b['exports']
 assert b['reliable_sequence']==534+i and b['partial_flags']==[0,0,int(i==7)]
 assert b['payload_bits']==(3957 if i==7 else 7616)
 w.raw(bytes.fromhex(b['payload_hex']),b['payload_bits'])
assert w.bits==57269
body=R/'proofs/settlement-winstead-captured-body.bin';body.write_bytes(w.data)
binding_file=R/'proofs/settlement-replication-live.json';bindings=json.loads(binding_file.read_bytes())
cache=bindings['class_net_cache'];assert cache['field_maximum']==16
assert next(x for x in cache['fields'] if x['name']=='LayoutAssetSetGuids')['field_net_index']==13
node_cmd=next(x for x in bindings['rep_layout']['commands'] if x['property'] and x['property']['name']=='NodeGuid')
assert node_cmd['handle_candidate']==25 and node_cmd['offset']==0x500
prefix=decode_actor_location(bytes(w.data),w.bits);assert prefix['consumed_bits']==465
r=BitReader(bytes(w.data),w.bits);r.pos=465
assert r.read(1)==1
angles=[]
for _ in range(3):angles.append(r.read(16) if r.read(1) else 0)
assert angles==[0,58110,0] and [r.read(1),r.read(1)]==[0,0] and r.pos==487
assert [r.read(1),r.read(1)]==[1,1] and r.packed()==56756 and r.pos==513
assert r.read(1)==0 and r.packed()==1 and r.read(32)==0
assert r.packed()==7 and r.pos==562
opaque_start=r.pos;opaque_movement=r.raw(96).hex();assert r.pos==658
assert r.packed()==8 and r.read(3)==1 and r.packed()==16 and r.read(3)==4
assert r.pos==680 and r.packed()==node_cmd['handle_candidate']
node_guid=r.read(64);assert node_guid==0x62d024b45678 and r.packed()==0 and r.pos==760
field_index=r.uint(cache['field_maximum']);assert field_index==13
field_bits=r.packed();field_start=r.pos;assert field_start==788 and field_bits==56481
assert r.read(1)==1 # wrapper observed independently; native meaning needs receive dispatcher
metadata=[r.read(8) for _ in range(3)];assert metadata==[3,0,0]
assert r.read(1)==0 and r.read(7)==1
tag=r.string();tag_number=r.read(32)
assert tag=='War.Siege.States.SiegeInactive' and tag_number==0 and r.pos==1133
version=r.read(8);assert version==1 and r.pos==1141
array_key,base_key,deleted,changed=[r.read(32) for _ in range(4)]
assert [array_key,base_key,deleted,changed]==[140,0,0,70] and r.pos==1269
defs_file=R/'proofs/settlement-records-live.json';defs=json.loads(defs_file.read_bytes())
lookup={k:{int(x['record_id'],0):x for x in v['records']} for k,v in defs['records'].items()}
node=lookup['CityNode'][node_guid];layout=lookup['Layout'][int(node['fields']['LayoutId']['record_id'],0)]
props=layout['fields']['Props']['items'];items=[];matched_props=0
for ordinal in range(changed):
 start=r.pos;item_id=r.read(32);owner=r.read(64);secondary=r.read(32);index=r.read(32);assetset=r.read(64)
 v=struct.unpack('<9d',r.raw(576));assert r.pos-start==800 and all(math.isfinite(x) for x in v)
 assert item_id==71+ordinal
 name=lookup['NodeAssetSet'].get(assetset,{}).get('name')
 prop_match=owner==node_guid and secondary==0
 if prop_match:
  assert index<len(props)
  assert assetset==int(props[index]['AssetSet']['record_id'],0)
  matched_props+=1
 q=v[:3];norm=sum(x*x for x in q)
 item={'ordinal':ordinal,'start_bit':start,'bits':800,'replication_id':item_id,
  'owner_guid':hex(owner),'owner_secondary_id':secondary,'owner_array_index':index,
  'assetset_record_guid':hex(assetset),'assetset_name':name,'quat_xyz':q,
  'quat_w_positive_sqrt':math.sqrt(max(0.,1.-norm)),
  'translation_cm':v[3:6],'scale3d':v[6:9],
  'matched_layout_prop':prop_match}
 if prop_match:
  t=props[index]['Transform'];qr=[*q,item['quat_w_positive_sqrt']]
  errors={'translation':max(abs(a-b) for a,b in zip(v[3:6],t['translation'])),
   'scale':max(abs(a-b) for a,b in zip(v[6:9],t['scale'])),
   'quat_sign_equivalent':min(max(abs(a-b) for a,b in zip(qr,t['quaternion'])),max(abs(a+b) for a,b in zip(qr,t['quaternion'])))}
  item['layout_transform_max_errors']=errors
  assert errors['translation']<1e-5 and errors['scale']<1e-9 and errors['quat_sign_equivalent']<1e-6, (ordinal,errors)
 items.append(item)
assert r.pos==w.bits==field_start+field_bits and r.remaining==0
floor=items[14];assert floor['assetset_record_guid']=='0x5429e761b0070000'
assert floor['quat_xyz']==(0.,0.,0.) and floor['translation_cm']==(0.,0.,0.) and floor['scale3d']==(1.,1.,1.)
out={'capture':s['capture'],'capture_sha256':s['capture_sha256'],
 'source':str(source),'source_sha256':sha(source),'body_sha256':sha(body),'body_bits':w.bits,
 'frames':[{'frame':x['frame'],'reliable_sequence':x['bunch']['reliable_sequence'],'bits':x['bunch']['payload_bits']} for x in selected],
 'native_binding_source':str(binding_file),'native_binding_sha256':sha(binding_file),
 'native_binding_lifetime':bindings['proof'],'definition_source_sha256':sha(defs_file),
 'actor_prefix':prefix,'rotation_shorts':angles,'actor_content_start_bit':513,'actor_content_bits':56756,
 'ordinary_properties':{'auth_server_id':0,'replicated_movement':{'start_bit':opaque_start,'bits':96,'opaque_hex':opaque_movement},
  'remote_role_raw':1,'role_raw':4,'node_guid_handle':25,'node_guid':hex(node_guid),'terminator_end_bit':760},
 'custom_delta':{'field_index':13,'field_maximum':16,'start_bit':field_start,'bits':field_bits,
  'wrapper_prefix':1,'node_level':3,'node_culture':0,'node_season':0,'gameplay_tags':[tag],
  'plot_change_version':version,'array_key':array_key,'base_key':base_key,'deleted_count':deleted,'changed_count':changed,
  'first_item_start_bit':1269,'items':items},'floor':floor,'consumed_bits':r.pos,'remaining_bits':r.remaining,
 'replayed':False,'limits':['Historical Village3 metadata and dynamic network GUID must not be replayed as Crossroads1.',
 'ReplicatedMovement remains explicitly opaque at a capture-bounded interval; not a general Actor decoder.',
 '48layout-prop items are matched by actual OwnerArrayIndex, not filtered-item ordinal; 22service-owner lifecycle items remain a separate research task.',
 'Fresh native cache binds handle/field; native serializer version branches and live acceptance still matter.']}
(R/'proofs/settlement-winstead-capture-decoded.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps({'body_bits':w.bits,'changed_items':changed,'matched_layout_props':matched_props,'floor':floor,'remaining_bits':r.remaining},indent=2))
