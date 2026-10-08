"""Prepare a fixed, proof-bound staged HUD/possession experiment; --write opts in.

Default prints the concrete JSON for review without creating the command file.
Run --write only when the owning operator wants this exact one-shot dispatched
on the current joined connection's next incoming packet.
"""
import argparse
import json
from pathlib import Path
import secrets
import time
from protocol_proof import validate_current_client_proofs


def command(peer, port, pid, operation="ClientRestart"):
    root = Path(__file__).resolve().parents[1]
    actor_name = f"evidence/player_state_world_{pid}.json"
    cache_name = f"evidence/driver_net_cache_world_{pid}.json"
    actor_path = root/actor_name
    actors = json.loads(actor_path.read_text(encoding="utf-8"))
    cache = json.loads((root/cache_name).read_text(encoding="utf-8"))
    validate_current_client_proofs(pid, cache, actors)
    if actors["errors"]:
        raise ValueError("Exact verified actor snapshot required")
    matches = actors["network_guid_actor_matches"]
    local_addresses = {p["player_controller"]["address"] for p in actors["local_players"] if p.get("player_controller")}
    controller = [m for m in matches if m["actor"]["class"] == "AoCPlayerControllerBP_C" and m["actor"]["address"] in local_addresses]
    pawn = [m for m in matches if m["actor"]["class"] == "PlayerPawn_C"]
    if len(controller) != 1 or len(pawn) != 1:
        raise ValueError("One accepted local controller and one accepted gameplay pawn required")
    if operation not in ("ClientSetHUD", "ClientRestart", "PawnAutonomous", "GameStateBeginPlay", "ControllerPlayerState", "PawnPlayerState", "CharacterInfoExport", "CharacterInfoName", "CharacterInfoGuid", "StatsComponentExport", "StatsGravity", "StatsSpeed"):
        raise ValueError("Only fixed HUD, possession, autonomy or GameState BeginPlay commands are supported")
    result = {"command": operation, "peer": [peer, port],
            "controller_guid": controller[0]["guid"], "pawn_guid": pawn[0]["guid"],
            "cache_snapshot": cache_name,
            "actor_snapshot": actor_name,
            "id": secrets.token_hex(16), "expires_at": time.time()+25}
    if operation in ('StatsGravity', 'StatsSpeed'):
        import sys
        sys.path.insert(0, str(root))
        from lab.stats_component import validate_gravity_update, validate_speed_update
        result.update(mapping_snapshot=f'evidence/stats_mapping_{pid}.json',
                      stats_cache_snapshot=f'evidence/stats_driver_net_cache_{pid}.json')
        mapping, stats_cache = [json.loads((root/result[k]).read_text()) for k in ('mapping_snapshot','stats_cache_snapshot')]
        validate_current_client_proofs(pid, mapping, stats_cache)
        if len(mapping['accepted_component_guids']) != 1:
            raise ValueError('One independently accepted stats GUID required')
        result['component_guid'] = mapping['accepted_component_guids'][0]
        (validate_gravity_update if operation == 'StatsGravity' else validate_speed_update)(mapping, stats_cache, result['component_guid'])
    if operation == 'StatsComponentExport':
        import sys
        sys.path.insert(0, str(root))
        from lab.stats_component import validate_stats_export
        from lab.world_bootstrap import fresh_actor_guid
        result.update(component_guid=fresh_actor_guid().as_dict(),
                      receiver_snapshot=f'evidence/stats_receiver_{pid}.json')
        receiver = json.loads((root/result['receiver_snapshot']).read_text())
        validate_current_client_proofs(pid, actors, receiver)
        validate_stats_export(actors, receiver, pawn[0]['guid'], result['component_guid'])
    if operation == 'CharacterInfoExport':
        import sys
        sys.path.insert(0,str(root))
        from lab.character_info_component import validate_character_info_export
        from lab.world_bootstrap import fresh_actor_guid
        result.update(component_guid=fresh_actor_guid().as_dict(),
            appearance_snapshot=f'evidence/character_info_before_export_{pid}.json',
            receiver_snapshot=f'evidence/character_info_receiver_{pid}.json')
        appearance,receiver=[json.loads((root/result[k]).read_text()) for k in ('appearance_snapshot','receiver_snapshot')]
        validate_current_client_proofs(pid,appearance,receiver)
        validate_character_info_export(actors,appearance,receiver,pawn[0]['guid'],result['component_guid'])
    if operation == 'CharacterInfoName':
        import sys,sqlite3
        sys.path.insert(0,str(root))
        from lab.character_info_component import validate_character_info_name
        result.update(layout_snapshot=f'evidence/rep_layout_world_{pid}.json',
            appearance_snapshot=f'evidence/character_info_after_export_{pid}.json',
            mapping_snapshot=f'evidence/character_info_mapping_{pid}.json')
        appearance,mapping,layouts=[json.loads((root/result[k]).read_text()) for k in ('appearance_snapshot','mapping_snapshot','layout_snapshot')]
        validate_current_client_proofs(pid,appearance,mapping)
        validate_current_client_proofs(pid,layouts,actors)
        rows=sqlite3.connect(root/'data/lab.sqlite').execute('SELECT name FROM characters').fetchall()
        if len(rows)!=1:
            raise ValueError('One unambiguous own-server character required')
        result.update(character_name=rows[0][0],component_guid=mapping['network_guid_component_matches'][0]['guid'])
        validate_character_info_name(actors,appearance,mapping,layouts,pawn[0]['guid'],result['component_guid'])
    if operation == 'CharacterInfoGuid':
        import sys,sqlite3
        sys.path.insert(0,str(root))
        from lab.character_info_component import validate_character_info_guid,character_guid_words
        result.update(layout_snapshot=f'evidence/rep_layout_world_{pid}.json',
            appearance_snapshot=f'evidence/character_info_before_identity_{pid}.json',
            mapping_snapshot=f'evidence/character_info_mapping_{pid}.json')
        appearance,mapping,layouts=[json.loads((root/result[k]).read_text()) for k in ('appearance_snapshot','mapping_snapshot','layout_snapshot')]
        validate_current_client_proofs(pid,appearance,mapping)
        validate_current_client_proofs(pid,layouts,actors)
        with sqlite3.connect(root/'data/lab.sqlite') as db:
            rows=db.execute('SELECT id FROM characters').fetchall()
        if len(rows)!=1:
            raise ValueError('One unambiguous own-server character required')
        character_guid_words(rows[0][0])
        result.update(character_id=rows[0][0],component_guid=mapping['network_guid_component_matches'][0]['guid'])
        validate_character_info_guid(actors,appearance,mapping,layouts,pawn[0]['guid'],result['component_guid'])
    if operation == "PawnAutonomous":
        result.update(layout_snapshot=f"evidence/rep_layout_world_{pid}.json", role_snapshot=f"evidence/role_serialization_{pid}.json")
        layouts = json.loads((root/result["layout_snapshot"]).read_text(encoding="utf-8"))
        roles = json.loads((root/result["role_snapshot"]).read_text(encoding="utf-8"))
        validate_current_client_proofs(pid, layouts, roles)
    if operation == "GameStateBeginPlay":
        gs = [m for m in matches if m["actor"]["class"] == "AoCGameStateBP_C"]
        if len(gs) != 1:
            raise ValueError("One accepted gameplay GameState required")
        result.update(game_state_guid=gs[0]["guid"], layout_snapshot=f"evidence/rep_layout_world_{pid}.json",
            begin_play_snapshot=f"evidence/begin_play_serialization_{pid}.json",
            lifecycle_snapshot=f"evidence/world_lifecycle_prerequisites_{pid}.json")
        layouts, serializer, lifecycle = [json.loads((root/result[key]).read_text(encoding="utf-8"))
            for key in ("layout_snapshot", "begin_play_snapshot", "lifecycle_snapshot")]
        validate_current_client_proofs(pid, layouts, serializer)
        validate_current_client_proofs(pid, lifecycle, actors)
        import sys
        sys.path.insert(0, str(root))
        from lab.game_state_begin_play import validate_game_state_begin_play
        validate_game_state_begin_play(layouts, serializer, lifecycle, gs[0]["actor"], actors=actors)
    if operation in ('ControllerPlayerState', 'PawnPlayerState'):
        ps = [m for m in matches if m['actor']['class'] == 'AoCPlayerStateBP_C']
        if len(ps) != 1:
            raise ValueError('One accepted current PlayerState required')
        result.update(player_state_guid=ps[0]['guid'], layout_snapshot=f'evidence/rep_layout_world_{pid}.json',
            receiver_snapshot=f'evidence/{"controller" if operation == "ControllerPlayerState" else "pawn"}_player_state_receiver_{pid}.json')
        layouts, receiver = [json.loads((root/result[key]).read_text()) for key in ('layout_snapshot', 'receiver_snapshot')]
        validate_current_client_proofs(pid, layouts, receiver)
        import sys
        sys.path.insert(0, str(root))
        if operation == 'ControllerPlayerState':
            from lab.controller_player_state import validate_controller_player_state
            controller_cache = next(c for c in cache['candidate_caches'] if c['class'] == 'AoCPlayerControllerBP_C')
            validate_controller_player_state(layouts, receiver, actors, controller_cache,
                controller[0]['guid'], ps[0]['guid'], receiver=receiver)
        else:
            from lab.pawn_player_state import validate_pawn_player_state
            pawn_cache = next(c for c in cache['candidate_caches'] if c['class'] == 'PlayerPawn_C')
            validate_pawn_player_state(layouts, receiver, actors, pawn_cache, pawn[0]['guid'], ps[0]['guid'])
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--peer", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--pid", type=int, required=True, help="Exact live client PID with freshly generated proof snapshots")
    parser.add_argument("--command", choices=("ClientSetHUD", "ClientRestart", "PawnAutonomous", "GameStateBeginPlay", "ControllerPlayerState", "PawnPlayerState", "CharacterInfoExport", "CharacterInfoName", "CharacterInfoGuid", "StatsComponentExport", "StatsGravity", "StatsSpeed"), default="ClientRestart")
    parser.add_argument("--write", action="store_true", help="Explicitly enable this concrete one-shot test")
    args = parser.parse_args()
    if not 0 < args.port <= 65535:
        parser.error("Valid UDP peer port required")
    value = command(args.peer, args.port, args.pid, args.command)
    encoded = json.dumps(value, indent=2)
    if args.write:
        path = Path(__file__).resolve().parents[1]/"data/client-restart-experiment.json"
        # Replace a sibling temporary file atomically to avoid partial polling.
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(encoded, encoding="utf-8")
        temporary.replace(path)
    print(encoded)
