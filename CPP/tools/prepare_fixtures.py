"""Offline migration/parity fixture generation from the frozen Python snapshot."""
import hashlib,json,pathlib,sys,shutil,struct,time
cpp=pathlib.Path(__file__).resolve().parents[1];baseline=cpp/'baseline';original=cpp.parent
sys.path.insert(0,str(baseline))
# Finish freezing referenced native heightfield buffers, excluded from the initial text inventory.
manifest=json.loads((baseline/'manifest.json').read_text());known={v['path'] for v in manifest['files']}
for p in (original/'evidence').rglob('*'):
    if p.is_file() and p.suffix in ('.heights','.materials'):
        rel=p.relative_to(original);out=baseline/rel
        if rel.as_posix() not in known:
            out.parent.mkdir(parents=True,exist_ok=True);b=p.read_bytes();out.write_bytes(b)
            manifest['files'].append({'path':rel.as_posix(),'size':len(b),'sha256':hashlib.sha256(b).hexdigest()})
(baseline/'manifest.json').write_text(json.dumps(manifest,indent=2))
from lab.unreal import BitWriter,encode_packet,encode_handshake,encode_control,decode_packet
from lab.world_bootstrap import NetGUID,encode_actor_rpc_content,experimental_controller_bunches,experimental_scene_bunches
from lab.movement_response import encode_move_ack_content,encode_move_correction_content
from lab.pawn_role import encode_pawn_autonomous_content
from lab.game_state_begin_play import encode_game_state_begin_play_content
from lab.controller_player_state import encode_controller_player_state_content
from lab.pawn_player_state import encode_pawn_player_state_content
from lab.stats_component import encode_gravity_content,encode_speed_content,encode_stats_export
from lab.character_info_component import encode_character_info_name_content,encode_character_info_guid_content,encode_character_info_export
fixture={'bits':[],'packets':[],'movement':[]}
for name,value in [('ack',encode_move_ack_content(12.25)),('correction',encode_move_correction_content(12.25,[-680500,406500,12503.39],[220,0,900],3)),('role',encode_pawn_autonomous_content()),('begin',encode_game_state_begin_play_content())]:
    fixture['bits'].append({'name':name,'hex':value[0].hex(),'bits':value[1]})
g={'object_id':'0x1234567890abcdef','server_id':1,'randomizer':123}
# Dynamic references must have an even object ID.
g['object_id']='0x1234567890abcdee'
p={'object_id':'0x0234567890abcdee','server_id':1,'randomizer':456}
fixture['guid']=g;fixture['pawn']=p
for name,value in [('controller_state',encode_controller_player_state_content(g)),('pawn_state',encode_pawn_player_state_content(g)),('gravity',encode_gravity_content(g)),('speed',encode_speed_content(g)),('stats_export',encode_stats_export(p,g)),('info_export',encode_character_info_export(p,g)),('name',encode_character_info_name_content(g,'LabExplorer')),('character_id',encode_character_info_guid_content(g,'00000037000000370000003700000000'))]:
    fixture['bits'].append({'name':name,'hex':value[0].hex(),'bits':value[1]})
for seq in (0,1,16383):
    payload=encode_control(1,map='/Game/Levels/Verra_World_Master/Verra_World_Master',game_mode='/Game/GameBlueprints/AoCGameModeBaseBP.AoCGameModeBaseBP_C')
    b=encode_packet(1,2,seq,51,[1,0x12345678],payload,123,True)
    fixture['packets'].append({'hex':b.hex(),'decoded':decode_packet(b,direction='server')})
profile=json.loads((baseline/'data/terrain-movement-experiment.json').read_text())
terrain=baseline/profile['terrain_manifest'];collision=baseline/profile['static_collision_snapshot']
from lab.static_collision import from_export
print('Preparing frozen collision cache',flush=True)
report=json.loads(collision.read_text());meshes,errors=from_export(report)
sources={};instances=[]
for mesh in meshes:
    source=getattr(mesh,'source',mesh);key=str(id(source))
    if key not in sources:
        sources[key]={'kind':getattr(source,'_geometry_kind','convex'),'closed':getattr(source,'closed',True),'triangles':[[list(v) for v in tri] for tri,normal in source.faces]}
    instances.append({'source':key,'matrix':list(getattr(mesh,'matrix',[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]))})
cache={'schema':'ashes-frozen-collision-v1','source_sha256':hashlib.sha256(collision.read_bytes()).hexdigest(),'client_proof':report.get('client_proof'),'sources':sources,'instances':instances,'unsupported':errors}
(cpp/'config/frozen-collision.json').write_text(json.dumps(cache,separators=(',',':')))
(cpp/'config/backend.json').write_text(json.dumps({'dashboard_port':8865,'lobby_port':16051,'world_port':18089,'tether_port':18090,'terrain_manifest':'baseline/'+profile['terrain_manifest'],'collision_cache':'config/frozen-collision.json','spawn':profile['spawn'],'client_exe':r'E:\Games\Steam Library\steamapps\common\Ashes of Creation\Game\AOC\Binaries\Win64\AOCClient-Win64-Shipping.exe','client_sha256':'4f1cd43ceeb89190f048734efd4d63152b9f8e11fa31fc41093b0d90f4a1cd43','sdk_path':r'E:\Games\Steam Library\steamapps\common\Ashes of Creation\Game\AOC\Binaries\Win64\EOSSDK-Win64-Shipping.dll','sdk_sha256':json.loads((baseline/'data/eos-local-compat.json').read_text())['sdk_sha256'],'auto_bootstrap':False},indent=2))
from lab.terrain import Heightfield
from lab.terrain_movement import TerrainMovement
tiles=[]
for t in json.loads(terrain.read_text())['tiles']:
    tiles.append(Heightfield(t['rows'],t['cols'],t['origin'],t['scale'],t['minimum'],t['quantization'],(terrain.parent/t['heights']).read_bytes(),(terrain.parent/t['materials']).read_bytes()))
state=TerrainMovement(tiles,profile['spawn'],static_meshes=meshes,floor_clearance=.02)
state.position[2]=state.floor(*state.position[:2])
fixture['movement_spawn']=state.position.copy()
for i in range(101):
    t=i*.02;move={'timestamp':t,'acceleration':[8192 if i<20 else 0,0,0],'compressed_flags':1 if 20<=i<23 else 0,'kind':'new'}
    result=state.advance(move,100+t)
    fixture['movement'].append({'move':move,'now':100+t,'result':result})
(cpp/'tests/fixtures/parity.json').write_text(json.dumps(fixture,indent=2))
print(json.dumps({'colliders':len(meshes),'sources':len(sources),'stored_faces':sum(len(s['triangles']) for s in sources.values()),'instance_faces':sum(len(sources[i['source']]['triangles']) for i in instances),'unsupported':len(errors)}),flush=True)
