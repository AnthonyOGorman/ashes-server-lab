"""Refresh fixed read-only world proofs; performs no input or protocol dispatch."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from protocol_proof import client_proof
from inspect_class_net_arrays import inspect as class_arrays
from inspect_driver_net_cache import inspect as driver_cache
from inspect_rep_layout import inspect as rep_layout
from inspect_role_serialization import inspect as role_serializer
from inspect_player_state import inspect as actors
from inspect_movement_prerequisites import inspect as lifecycle
from inspect_begin_play_serialization import inspect as begin_play

ROOT = Path(__file__).resolve().parents[1]


def refresh(pid):
    exe = Path(json.loads((ROOT / 'evidence/client_inventory.json').read_text())['exe'])
    def path(stem):
        return ROOT / 'evidence' / f'{stem}_{pid}.json'
    def save(stem, report):
        report['client_proof'] = client_proof(pid)
        path(stem).write_text(json.dumps(report, indent=2), encoding='utf-8')
        return report
    reflection = path('runtime_reflection_world')
    args = [sys.executable, str(ROOT / 'tools/dump_runtime_reflection.py'), str(pid), '--output', str(reflection)]
    for name in ('AoCPlayerControllerBP_C', 'PlayerController', 'Controller', 'PlayerPawn_C',
                 'AoCPlayerStateBP_C', 'AoCGameStateBP_C', 'BP_AOCHUD_C', 'World', 'Level',
                 'WorldSettings', 'IntrepidNetDriver', 'CharacterInfo', 'PlayerInfo',
                 'CharacterAppearanceComponent', 'IntrepidRepKeyComponent', 'ActorComponent'):
        args.extend(('--class', name))
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    save('class_net_arrays_world', class_arrays(reflection))
    caches = save('driver_net_cache_world', driver_cache(path('class_net_arrays_world')))
    layouts = save('rep_layout_world', rep_layout(path('class_net_arrays_world'), path('driver_net_cache_world')))
    save('role_serialization', role_serializer(reflection))
    observed = save('player_state_world', actors(pid, exe))
    local = [row['player_controller']['address'] for row in observed['local_players'] if row.get('player_controller')]
    controllers = [row for row in observed['controllers'] if row['address'] in local and row.get('acknowledges_same_pawn') and row.get('pawn_points_back_to_controller')]
    if len(controllers) != 1 or observed['errors'] or layouts['errors']:
        raise ValueError('Fresh accepted mutual possession and clean actor/layout proof required')
    controller = controllers[0]
    life = save('world_lifecycle_prerequisites', lifecycle(pid, int(controller['address'], 16), int(controller['pawn']['address'], 16)))
    serial = save('begin_play_serialization', begin_play(reflection))
    return {'pid': pid, 'controller': controller['address'], 'pawn': controller['pawn']['address'],
            'driver': caches['drivers'], 'game_state': life['game_state']['identity'],
            'begun_play': serial['observed_bool_value'], 'predicate': serial.get('game_specific_predicate'),
            'movement_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', required=True, type=int)
    args = parser.parse_args()
    report = refresh(args.pid)
    print(json.dumps({key: value for key, value in report.items() if key != 'predicate'}, indent=2))
    print('predicate:', (report.get('predicate') or {}).get('status'))
