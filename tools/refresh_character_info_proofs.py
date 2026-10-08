"""Refresh bounded CharacterInfo proofs for the currently accepted local pawn."""
import argparse
import json
from pathlib import Path
from inspect_character_appearance import inspect as appearance
from inspect_character_info_mapping import inspect as mapping
from inspect_character_info_receiver import inspect as receiver
from protocol_proof import validate_current_client_proofs

ROOT=Path(__file__).resolve().parents[1]
def refresh(pid,stage):
    actors_path=ROOT/'evidence'/f'player_state_world_{pid}.json'
    actors=json.loads(actors_path.read_text())
    validate_current_client_proofs(pid,actors,actors)
    if actors.get('errors'):
        raise ValueError('Clean actor proof required')
    local={p['player_controller']['address'] for p in actors['local_players'] if p.get('player_controller')}
    pcs=[m['actor'] for m in actors['network_guid_actor_matches'] if m['actor']['class']=='AoCPlayerControllerBP_C' and m['actor']['address'] in local]
    pawns=[m['actor'] for m in actors['network_guid_actor_matches'] if m['actor']['class']=='PlayerPawn_C']
    if len(pcs)!=1 or len(pawns)!=1:
        raise ValueError('One accepted local controller and pawn required')
    stem={'export':'character_info_before_export','name':'character_info_after_export','identity':'character_info_before_identity'}[stage]
    path=ROOT/'evidence'/f'{stem}_{pid}.json'
    saved=appearance(pid,int(pcs[0]['address'],16),int(pawns[0]['address'],16),require_possession=False)
    path.write_text(json.dumps(saved,indent=2))
    if stage=='export':
        report=receiver(pid,path)
        target=ROOT/'evidence'/f'character_info_receiver_{pid}.json'
    else:
        report=mapping(pid,path,actors_path)
        target=ROOT/'evidence'/f'character_info_mapping_{pid}.json'
    target.write_text(json.dumps(report,indent=2))
    return {'appearance':str(path),'receiver_or_mapping':str(target),'pawn':pawns[0]['address'],
        'component':saved['character_information']['identity']['address'],
        'character_name':saved['character_information']['fields']['CharacterName'].get('value'),
        'mapping_count':len(report.get('network_guid_component_matches',[]))}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid',required=True,type=int)
    p.add_argument('--stage',required=True,choices=('export','name','identity'))
    a=p.parse_args()
    print(json.dumps(refresh(a.pid,a.stage),indent=2))
