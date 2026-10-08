"""Activate continuous landscape authority for one initialized local world.

All proofs and heightfields are refreshed from the exact client. Does not
launch the game, select a character, initialize stats, or send movement input.
"""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import sys
import time
import urllib.request

from protocol_proof import client_proof, EXPECTED_EXE
from inspect_player_state import inspect as actors
from inspect_stats_receiver import inspect as receiver
from inspect_stats_mapping import inspect as mapping
from inspect_driver_net_cache import inspect as cache
from inspect_world_collision import inspect as collision
from export_landscape_heightfields import export

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def activate(pid, port, connection_id, epoch, static_collision=None):
    with urllib.request.urlopen('http://127.0.0.1:8765/api/state',timeout=30) as response:
        state=json.load(response)
    entry=state['world_entry']
    if (not entry['active'] or entry['connection_id']!=connection_id
            or entry['epoch']!=epoch or state['client']['pid']!=pid):
        raise ValueError('matching active world and live client required')
    with sqlite3.connect(f'file:{ROOT / "data/lab.sqlite"}?mode=ro',uri=True) as db:
        handshakes=db.execute("select detail from events where kind='udp_handshake' order by id desc limit 10")
        accepted=[json.loads(row[0]) for row in handshakes]
        match=next((row for row in accepted if row.get('accepted') and row.get('connection_id')==connection_id),None)
        if not match or match['detail']['peer']!=str(('127.0.0.1',port)):
            raise ValueError('matching accepted loopback peer required')
    def save(name,value):
        value['pid']=pid;value['client_proof']=client_proof(pid)
        path=ROOT/'evidence'/f'{name}_{pid}.json'
        path.write_text(json.dumps(value,indent=2));return path
    ap=save('player_state_world',actors(pid,EXPECTED_EXE))
    rp=save('stats_receiver',receiver(pid,ap));sp=save('stats_mapping',mapping(pid,ap,rp))
    cp=save('driver_net_cache_world',cache(ROOT/'evidence'/f'class_net_arrays_world_{pid}.json'))
    report=json.loads(ap.read_text())
    local_controllers={row['player_controller']['address'] for row in report['local_players'] if row.get('player_controller')}
    controllers=[row for row in report['controllers'] if row['address'] in local_controllers
                 and row.get('acknowledges_same_pawn') and row.get('pawn_points_back_to_controller')]
    if len(controllers)!=1 or report['errors']:raise ValueError('exact mutual possession required')
    pawn=controllers[0]['pawn']
    if pawn['class']!='PlayerPawn_C' or pawn['network_roles']['Role']!=2:
        raise ValueError('autonomous gameplay pawn required')
    spawn=pawn['root_component']['unattached_location']
    match=next(row for row in report['network_guid_actor_matches'] if row['actor']['address']==pawn['address'])
    source=save(f'world_collision_epoch{epoch}',collision(pid))
    output=ROOT/'evidence'/f'terrain_epoch{epoch}_{pid}'
    export(pid,source,output,*spawn[:2]);manifest=output/'manifest.json'
    def relative(path):return path.relative_to(ROOT).as_posix()
    profile={'mode':'connection-landscape-locomotion-v1','id':secrets.token_hex(16),
        'peer':['127.0.0.1',port],'connection_id':connection_id,'pawn_guid':match['guid'],
        'pid':pid,'expires_at':time.time()+115.,'cache_snapshot':relative(cp),
        'actor_snapshot':relative(ap),'terrain_manifest':relative(manifest),
        'terrain_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),
        'spawn':spawn,'stats_mapping_snapshot':relative(sp)}
    if static_collision is not None:
        from protocol_proof import validate_current_client_proofs
        from lab.static_collision import from_export
        path=static_collision.resolve()
        if path.parent!=(ROOT/'evidence').resolve() or not path.name.endswith(f'_{pid}.json'):
            raise ValueError('local current-client static collision export required')
        raw=path.read_bytes();geometry=json.loads(raw)
        validate_current_client_proofs(pid,report,geometry)
        if geometry['pawn']['address']!=pawn['address']:
            raise ValueError('collision export must belong to the current pawn world')
        from_export(geometry)
        profile.update(static_collision_snapshot=relative(path),
                       static_collision_sha256=hashlib.sha256(raw).hexdigest())
    # Connection/pawn/profile validation is repeated by the server before it
    # initializes authority. No movement acceptance is claimed by this tool.
    (ROOT/'evidence'/f'terrain_profile_continuous_epoch{epoch}.json').write_text(json.dumps(profile,indent=2))
    path=ROOT/'data/terrain-movement-experiment.json';tmp=path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(profile,indent=2));tmp.replace(path)
    return {'pawn':pawn['address'],'spawn':spawn,'profile':profile['id'],'movement_verified':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid',type=int,required=True)
    parser.add_argument('--port',type=int,required=True)
    parser.add_argument('--connection',required=True)
    parser.add_argument('--epoch',type=int,required=True)
    parser.add_argument('--static-collision',type=Path)
    args=parser.parse_args()
    if not 0<args.port<=65535 or args.epoch<=0:parser.error('valid peer port and epoch required')
    print(json.dumps(activate(args.pid,args.port,args.connection,args.epoch,args.static_collision)))
