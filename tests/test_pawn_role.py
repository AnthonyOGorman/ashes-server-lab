import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from lab.unreal import BitReader, WorldProtocol, Connection, decode_packet
from lab.world_bootstrap import NetGUID
from lab.pawn_role import validate_pawn_role_layout, encode_pawn_autonomous_content

ROOT = Path(__file__).resolve().parents[1]


class PawnRoleTests(unittest.TestCase):
    def test_captured_prefix_independently_proves_handle_and_three_bit_enum(self):
        capture = json.loads((ROOT/"evidence/world_bootstrap_capture.json").read_text())
        row = next(item for item in capture["evidence"] if item["frame"] == 3710)
        bunch = decode_packet(bytes.fromhex(row["udp_hex"]), "server")["bunches"][1]
        reader = BitReader(bytes.fromhex(bunch["payload_hex"]), bunch["payload_bits"])
        reader.read(508)
        self.assertEqual([reader.read(1), reader.read(1)], [1, 1])
        self.assertEqual(reader.packed(), 519)
        self.assertEqual(reader.pos, 526)
        self.assertEqual(reader.read(1), 0)
        self.assertEqual(reader.packed(), 1)
        self.assertEqual(reader.read(32), 0)
        self.assertEqual(reader.packed(), 8)
        self.assertEqual(reader.read(3), 2)
        self.assertEqual(reader.packed(), 16)
        self.assertEqual(reader.read(3), 4)
        self.assertEqual(reader.packed(), 19)
        guid = NetGUID.read(reader)
        self.assertEqual(guid.as_dict(), {"object_id": "0x000000000009259e", "server_id": 33, "randomizer": 2650652073})
        self.assertEqual(reader.pos, 725)

    def test_fixed_role_block_has_only_handle8_value2_and_zero_terminator(self):
        payload, bits = encode_pawn_autonomous_content()
        reader = BitReader(payload, bits)
        self.assertEqual([reader.read(1), reader.read(1)], [1, 1])
        count = reader.packed()
        self.assertEqual(count, reader.remaining)
        self.assertEqual(reader.read(1), 0)
        self.assertEqual(reader.packed(), 8)
        self.assertEqual(reader.read(3), 2)
        self.assertEqual(reader.packed(), 0)
        self.assertEqual(reader.remaining, 0)

    def test_exact_live_layout_and_enum_are_required(self):
        layouts = json.loads((ROOT/"evidence/rep_layout_world_56352.json").read_text())
        roles = json.loads((ROOT/"evidence/role_serialization_56352.json").read_text())
        cache = json.loads((ROOT/"evidence/driver_net_cache_world_56352.json").read_text())
        pawn_cache = next(item for item in cache["candidate_caches"] if item["class"] == "PlayerPawn_C")
        self.assertEqual(validate_pawn_role_layout(layouts, roles, pawn_cache)["serialized_bits"], 3)
        wrong = copy.deepcopy(roles)
        wrong["properties"][0]["enum_names"][4]["value"] = 3
        with self.assertRaises(ValueError):
            validate_pawn_role_layout(layouts, wrong, pawn_cache)
        bad_layout = copy.deepcopy(layouts)
        layout = next(item for item in bad_layout["layouts"] if item["class"] == "PlayerPawn_C")
        layout["commands"][0]["command_type_byte"] = 0
        with self.assertRaises(ValueError):
            validate_pawn_role_layout(bad_layout, roles, pawn_cache)
        for key, index_key, target in (("parents", "parent_index", 7), ("commands", "command_index", 7)):
            incomplete = copy.deepcopy(layouts)
            pawn = next(item for item in incomplete["layouts"] if item["class"] == "PlayerPawn_C")
            pawn[key] = [item for item in pawn[key] if item[index_key] != target]
            with self.assertRaises(ValueError):
                validate_pawn_role_layout(incomplete, roles, pawn_cache)

    def test_proof_bound_command_targets_retained_pawn_once_and_refuses_missing_possession(self):
        actors = json.loads((ROOT/"evidence/player_state_possession_56352.json").read_text())
        controller = next(m["guid"] for m in actors["network_guid_actor_matches"] if m["actor"]["class"] == "AoCPlayerControllerBP_C")
        pawn = next(m["guid"] for m in actors["network_guid_actor_matches"] if m["actor"]["class"] == "PlayerPawn_C")
        events = []
        server = WorldProtocol(lambda kind, detail: events.append(kind))
        c = Connection(b"\0"*20, 0, 1, 0, 0, 0, 0, phase="joined")
        c.actor_guids, c.channel_reliable = {"controller": controller, "pawn": pawn}, {3: 15, 9: 1023}
        peer = ("127.0.0.1", 9999)
        command = {"command": "PawnAutonomous", "peer": list(peer), "controller_guid": controller, "pawn_guid": pawn,
            "cache_snapshot": "evidence/driver_net_cache_world_56352.json", "actor_snapshot": "evidence/player_state_world_56352.json",
            "layout_snapshot": "evidence/rep_layout_world_56352.json", "role_snapshot": "evidence/role_serialization_56352.json",
            "id": "missing-possession", "expires_at": time.time()+25}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/"data").mkdir()
            (root/"evidence").mkdir()
            for key in ("cache_snapshot", "actor_snapshot", "layout_snapshot", "role_snapshot"):
                (root/command[key]).write_bytes((ROOT/command[key]).read_bytes())
            (root/command["actor_snapshot"]).write_text(json.dumps(actors))
            path = root/"data/client-restart-experiment.json"
            with patch("lab.unreal.__file__", str(root/"lab/unreal.py")), patch("tools.protocol_proof.validate_current_client_proofs"):
                path.write_text(json.dumps(command))
                self.assertEqual(server._poll_client_restart_experiment(c, peer), [])
                c.possession_acknowledged = True
                command["id"] = "verified-autonomy"
                path.write_text(json.dumps(command))
                packets = server._poll_client_restart_experiment(c, peer)
                self.assertEqual(len(packets), 1)
                bunch = decode_packet(packets[0], "server")["bunches"][0]
                self.assertEqual((bunch["channel"], bunch["reliable_sequence"], bunch["payload_bits"]), (9, 0, 30))
                self.assertEqual(server._poll_client_restart_experiment(c, peer), [])
                command["id"] = "repeat-autonomy"
                path.write_text(json.dumps(command))
                self.assertEqual(server._poll_client_restart_experiment(c, peer), [])
        self.assertEqual(events.count("pawn_autonomous_experiment"), 1)
        self.assertNotIn("movement", events)
